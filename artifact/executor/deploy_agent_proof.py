from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from solcx import compile_standard, install_solc
from web3 import Web3


load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / '.env')


def compile_contract(contract_path: Path, solc_version: str) -> tuple[list[dict[str, Any]], str]:
    source = contract_path.read_text(encoding='utf-8')
    install_solc(solc_version)
    compiled = compile_standard(
        {
            'language': 'Solidity',
            'sources': {
                contract_path.name: {
                    'content': source,
                },
            },
            'settings': {
                'optimizer': {
                    'enabled': True,
                    'runs': 200,
                },
                'outputSelection': {
                    '*': {
                        '*': ['abi', 'evm.bytecode.object'],
                    },
                },
            },
        },
        solc_version=solc_version,
    )
    contract = compiled['contracts'][contract_path.name]['AgentProofLedger']
    abi = contract['abi']
    bytecode = contract['evm']['bytecode']['object']
    return abi, bytecode


def deploy(contract_path: Path, solc_version: str, dry_run: bool = False) -> dict[str, Any]:
    rpc_url = os.getenv('MANTLE_RPC_URL')
    private_key = os.getenv('MANTLE_PRIVATE_KEY')
    chain_id = int(os.getenv('MANTLE_CHAIN_ID', '5003'))
    if not rpc_url or not private_key:
        raise RuntimeError('MANTLE_RPC_URL and MANTLE_PRIVATE_KEY are required')

    abi, bytecode = compile_contract(contract_path, solc_version)
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 30}))
    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)

    tx = contract.constructor().build_transaction({
        'from': account.address,
        'chainId': chain_id,
        'nonce': web3.eth.get_transaction_count(account.address),
    })
    if 'maxFeePerGas' not in tx and 'maxPriorityFeePerGas' not in tx:
        tx.setdefault('gasPrice', web3.eth.gas_price)
    else:
        tx.pop('gasPrice', None)
    tx['gas'] = int(web3.eth.estimate_gas(tx) * 1.2)

    if dry_run:
        return {
            'dry_run': True,
            'deployer': account.address,
            'chain_id': chain_id,
            'gas': tx['gas'],
        }

    signed = web3.eth.account.sign_transaction(tx, private_key)
    raw_tx = getattr(signed, 'rawTransaction', None) or getattr(signed, 'raw_transaction')
    tx_hash = web3.eth.send_raw_transaction(raw_tx)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    return {
        'dry_run': False,
        'deployer': account.address,
        'chain_id': chain_id,
        'tx_hash': web3.to_hex(tx_hash),
        'contract_address': receipt.contractAddress,
        'gas_used': receipt.gasUsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Deploy AgentProofLedger to Mantle')
    parser.add_argument(
        '--contract',
        default=str(Path(__file__).resolve().parents[1] / 'contracts' / 'AgentProofLedger.sol'),
    )
    parser.add_argument('--solc-version', default='0.8.20')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    result = deploy(Path(args.contract), args.solc_version, args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
