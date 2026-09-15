from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import redis
from dotenv import load_dotenv

try:
    from web3 import Web3
except ImportError:  # pragma: no cover - optional dependency
    Web3 = None  # type: ignore[assignment]


load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')


# ABI v2 — AgentProofLedger with marketPowerScore
AGENT_PROOF_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "commitSignal",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "signalHash", "type": "bytes32"},
            {"name": "agentId", "type": "string"},
            {"name": "symbol", "type": "string"},
            {"name": "decision", "type": "uint8"},
            {"name": "rrRatio", "type": "uint16"},
            {"name": "entryType", "type": "string"},
            {"name": "signalTimestamp", "type": "uint64"},
            {"name": "marketPowerScore", "type": "int16"},  # v2: market strength score
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "commitOutcome",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "signalHash", "type": "bytes32"},
            {"name": "outcomeHash", "type": "bytes32"},
            {"name": "pnlBps", "type": "int32"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "getAgentStats",
        "stateMutability": "view",
        "inputs": [
            {"name": "agentId", "type": "string"},
        ],
        "outputs": [
            {"name": "totalSignals", "type": "uint256"},
            {"name": "winCount", "type": "uint256"},
            {"name": "totalPnlBps", "type": "int256"},
        ],
    },
]


def build_redis() -> redis.Redis:
    return redis.Redis.from_url(
        os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def stable_hash(payload: dict[str, Any]) -> str:
    hash_payload = {
        key: value
        for key, value in payload.items()
        if key not in {'signal_hash', 'decision_hash', 'tx_hash', 'proof_tx_hash'}
    }
    encoded = json.dumps(hash_payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def outcome_hash(record: dict[str, Any]) -> str | None:
    outcome = record.get('outcome')
    if not outcome:
        return None
    payload = {
        'signal_hash': record.get('decision_hash') or record.get('signal_hash'),
        'outcome': outcome,
        'detail': record.get('detail'),
        'stored_at': record.get('stored_at'),
    }
    return stable_hash(payload)


def decision_code(record: dict[str, Any]) -> int:
    decision = str(record.get('decision') or ('TRADE' if record.get('should_trade') else record.get('action', 'WATCH'))).upper()
    if decision == 'TRADE':
        return 1 if str(record.get('side', '')).lower() == 'buy' else 2
    return 0


def build_web3() -> tuple[Any, Any, str]:
    if Web3 is None:
        raise RuntimeError('web3 is not installed. Run: pip install -r executor/requirements.txt')

    rpc_url = os.getenv('MANTLE_RPC_URL')
    contract_address = os.getenv('AGENT_PROOF_CONTRACT')
    private_key = os.getenv('MANTLE_PRIVATE_KEY')
    if not rpc_url or not contract_address or not private_key:
        raise RuntimeError('MANTLE_RPC_URL, AGENT_PROOF_CONTRACT, and MANTLE_PRIVATE_KEY are required')

    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 30}))
    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=AGENT_PROOF_ABI)
    return web3, contract, account.address


def send_transaction(web3: Any, account_address: str, private_key: str, tx: dict[str, Any], nonce: int | None = None) -> str:
    tx.setdefault('from', account_address)
    tx.setdefault('chainId', int(os.getenv('MANTLE_CHAIN_ID', '5003')))
    tx.setdefault('nonce', nonce if nonce is not None else web3.eth.get_transaction_count(account_address, 'pending'))
    if 'maxFeePerGas' not in tx and 'maxPriorityFeePerGas' not in tx:
        tx.setdefault('gasPrice', web3.eth.gas_price)
    else:
        tx.pop('gasPrice', None)
    if 'gas' not in tx:
        tx['gas'] = int(web3.eth.estimate_gas(tx) * 1.2)

    signed = web3.eth.account.sign_transaction(tx, private_key)
    raw_tx = getattr(signed, 'rawTransaction', None) or getattr(signed, 'raw_transaction')
    try:
        tx_hash = web3.eth.send_raw_transaction(raw_tx)
    except ValueError as exc:
        message = str(exc)
        if 'replacement transaction underpriced' not in message:
            raise
        tx.pop('gasPrice', None)
        base_fee = int(web3.eth.gas_price * 1.2)
        tx['maxFeePerGas'] = max(int(tx.get('maxFeePerGas') or 0), base_fee)
        tx['maxPriorityFeePerGas'] = max(int(tx.get('maxPriorityFeePerGas') or 0), int(base_fee * 0.1), 1)
        signed = web3.eth.account.sign_transaction(tx, private_key)
        raw_tx = getattr(signed, 'rawTransaction', None) or getattr(signed, 'raw_transaction')
        tx_hash = web3.eth.send_raw_transaction(raw_tx)
    return web3.to_hex(tx_hash)


def commit_once(limit: int = 25, dry_run: bool = False) -> dict[str, Any]:
    redis_client = build_redis()
    raw_records = redis_client.lrange('agent_decision_journal', 0, max(limit - 1, 0))
    outcomes = redis_client.hgetall('agent_decision_outcomes') or {}

    web3 = contract = account_address = None
    private_key = os.getenv('MANTLE_PRIVATE_KEY', '')
    if not dry_run:
        web3, contract, account_address = build_web3()
        next_nonce = web3.eth.get_transaction_count(account_address, 'pending')
    else:
        next_nonce = 0

    committed: list[dict[str, str]] = []
    skipped = 0
    for raw_record in reversed(raw_records):
        record = json.loads(raw_record)
        signal_hash = str(record.get('decision_hash') or record.get('signal_hash') or stable_hash(record))

        # Check if signal is already committed
        signal_tx = redis_client.hget('agent_proof_txs', signal_hash)
        if signal_tx:
            # Signal is committed. Now check if outcome needs to be committed.
            outcome_val = record.get('outcome')
            pnl_bps_val = record.get('pnl_bps') or record.get('pnlBps')
            out_data = None

            if outcomes and signal_hash in outcomes:
                try:
                    out_data = json.loads(outcomes[signal_hash])
                    outcome_val = out_data.get('outcome')
                    pnl_bps_val = out_data.get('pnl_bps')
                except Exception:
                    pass

            if outcome_val and not redis_client.hget('agent_outcome_txs', signal_hash):
                if dry_run:
                    committed.append({'signal_hash': signal_hash, 'outcome_tx_hash': 'dry_run'})
                    continue

                mock_record = {
                    'decision_hash': signal_hash,
                    'outcome': outcome_val,
                    'detail': out_data.get('detail') if out_data else record.get('detail'),
                    'stored_at': out_data.get('stored_at') if out_data else record.get('stored_at'),
                }
                out_hash_str = outcome_hash(mock_record)
                if not out_hash_str:
                    skipped += 1
                    continue

                try:
                    pnl_bps = max(-2147483648, min(2147483647, int(float(pnl_bps_val or 0))))
                except (TypeError, ValueError):
                    pnl_bps = 0

                outcome_tx = contract.functions.commitOutcome(
                    bytes.fromhex(signal_hash),
                    bytes.fromhex(out_hash_str),
                    pnl_bps,
                ).build_transaction({'from': account_address, 'chainId': int(os.getenv('MANTLE_CHAIN_ID', '5003'))})
                outcome_tx_hash = send_transaction(web3, account_address, private_key, outcome_tx, nonce=next_nonce)
                next_nonce += 1
                redis_client.hset('agent_outcome_txs', signal_hash, outcome_tx_hash)
                committed.append({'signal_hash': signal_hash, 'outcome_tx_hash': outcome_tx_hash})
            else:
                skipped += 1
            continue

        symbol = str(record.get('symbol') or os.getenv('AUTO_TRADE_SYMBOL', 'BTC/USDT'))
        timestamp = int(record.get('signal_candle_timestamp') or record.get('timestamp') or record.get('stored_at') or time.time())
        agent_id = str(record.get('agent_id') or os.getenv('AGENT_ID', 'vibe-agent'))
        decision = decision_code(record)

        if dry_run:
            committed.append({'signal_hash': signal_hash, 'tx_hash': 'dry_run'})
            continue

        # Compute Risk:Reward ratio * 100 for uint16 (e.g. 2.85:1 → 285)
        rr_ratio_raw = record.get('rr_ratio') or record.get('rrRatio') or 0
        try:
            rr_ratio = max(0, min(65535, int(float(rr_ratio_raw) * 100)))
        except (TypeError, ValueError):
            rr_ratio = 0
        entry_type = str(record.get('entry_type') or record.get('entryType') or 'Market')

        # Market power score: scale float (e.g. +7.0) → int16 * 10 (→ +70), clamp to [-100, +100]
        mps_raw = record.get('market_power_score') or record.get('onchain_score') or record.get('news_score') or 0.0
        try:
            market_power_score = max(-100, min(100, int(float(mps_raw) * 10)))
        except (TypeError, ValueError):
            market_power_score = 0

        tx = contract.functions.commitSignal(  # type: ignore[union-attr]
            bytes.fromhex(signal_hash),
            agent_id,
            symbol,
            decision,
            rr_ratio,
            entry_type,
            timestamp,
            market_power_score,
        ).build_transaction({'from': account_address, 'chainId': int(os.getenv('MANTLE_CHAIN_ID', '5003'))})
        tx_hash = send_transaction(web3, account_address, private_key, tx, nonce=next_nonce)
        next_nonce += 1
        redis_client.hset('agent_proof_txs', signal_hash, tx_hash)
        redis_client.hset('agent_proof_status', signal_hash, 'onchain')
        committed.append({'signal_hash': signal_hash, 'tx_hash': tx_hash})

        # Check for outcome immediately
        outcome_val = record.get('outcome')
        pnl_bps_val = record.get('pnl_bps') or record.get('pnlBps')
        out_data = None

        if outcomes and signal_hash in outcomes:
            try:
                out_data = json.loads(outcomes[signal_hash])
                outcome_val = out_data.get('outcome')
                pnl_bps_val = out_data.get('pnl_bps')
            except Exception:
                pass

        if outcome_val:
            mock_record = {
                'decision_hash': signal_hash,
                'outcome': outcome_val,
                'detail': out_data.get('detail') if out_data else record.get('detail'),
                'stored_at': out_data.get('stored_at') if out_data else record.get('stored_at'),
            }
            out_hash_str = outcome_hash(mock_record)
            if out_hash_str:
                try:
                    pnl_bps = max(-2147483648, min(2147483647, int(float(pnl_bps_val or 0))))
                except (TypeError, ValueError):
                    pnl_bps = 0
                outcome_tx = contract.functions.commitOutcome(  # type: ignore[union-attr]
                    bytes.fromhex(signal_hash),
                    bytes.fromhex(out_hash_str),
                    pnl_bps,
                ).build_transaction({'from': account_address, 'chainId': int(os.getenv('MANTLE_CHAIN_ID', '5003'))})
                outcome_tx_hash = send_transaction(web3, account_address, private_key, outcome_tx, nonce=next_nonce)
                next_nonce += 1
                redis_client.hset('agent_outcome_txs', signal_hash, outcome_tx_hash)

    return {
        'committed': committed,
        'skipped_existing': skipped,
        'dry_run': dry_run,
    }


def commit_signal_live(
    signal_hash: str,
    agent_id: str,
    symbol: str,
    decision: int,
    rr_ratio: int,
    entry_type: str,
    signal_timestamp: int,
    market_power_score: int,
    dry_run: bool = False,
) -> str | None:
    """Commit a single signal to the blockchain immediately (called from executor thread).

    Returns the tx_hash string on success, or None on failure / dry_run.
    market_power_score should already be scaled x10 and clamped to [-100, 100].
    """
    redis_client = build_redis()
    existing = redis_client.hget('agent_proof_txs', signal_hash)
    if existing:
        return existing  # already committed

    if dry_run:
        redis_client.hset('agent_proof_txs', signal_hash, 'dry_run')
        return 'dry_run'

    try:
        web3, contract, account_address = build_web3()
        private_key = os.getenv('MANTLE_PRIVATE_KEY', '')
        tx = contract.functions.commitSignal(
            bytes.fromhex(signal_hash),
            agent_id,
            symbol,
            decision,
            rr_ratio,
            entry_type,
            signal_timestamp,
            market_power_score,
        ).build_transaction({'from': account_address, 'chainId': int(os.getenv('MANTLE_CHAIN_ID', '5003'))})
        tx_hash = send_transaction(web3, account_address, private_key, tx)
        redis_client.hset('agent_proof_txs', signal_hash, tx_hash)
        redis_client.hset('agent_proof_status', signal_hash, 'onchain')
        return tx_hash
    except Exception as exc:
        import logging
        logging.getLogger('mantle_proof').warning('commit_signal_live failed: %s', exc)
        return None


def loop_forever(limit: int, interval: int, dry_run: bool) -> None:
    while True:
        result = commit_once(limit=limit, dry_run=dry_run)
        print(json.dumps(result, separators=(',', ':')))
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description='Commit local agent decision hashes to Mantle proof ledger')
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.loop:
        loop_forever(args.limit, args.interval, args.dry_run)
    else:
        print(json.dumps(commit_once(args.limit, args.dry_run), indent=2))


if __name__ == '__main__':
    main()
