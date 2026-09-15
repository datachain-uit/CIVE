"""Deterministic alias checks for v18 multi-coin transfer."""
from multicoin_transfer_v18_common import ASSETS, is_asset_event


def main() -> None:
    assert is_asset_event({"affected_assets": ["Bitcoin"]}, set(ASSETS["BTCUSDT"]["aliases"]))
    assert is_asset_event({"affected_assets": ["Ripple"]}, set(ASSETS["XRPUSDT"]["aliases"]))
    assert is_asset_event({"affected_assets": ["Solana"]}, set(ASSETS["SOLUSDT"]["aliases"]))
    assert is_asset_event({"affected_assets": ["Binance Coin"]}, set(ASSETS["BNBUSDT"]["aliases"]))
    assert not is_asset_event({"affected_assets": ["Binance"]}, set(ASSETS["BNBUSDT"]["aliases"]))
    print("Multi-coin transfer v18 helper tests passed")


if __name__ == "__main__":
    main()
