from hyb005_cross_asset_common import canonical_asset, tilted_pair_weights


def main() -> None:
    assert canonical_asset("Ethereum") == "ETHUSDT"
    assert canonical_asset("Ripple") == "XRPUSDT"
    assert canonical_asset("unknown") is None
    scores = {"BTCUSDT": 1.0, "ETHUSDT": -1.0, "XRPUSDT": 0.0, "SOLUSDT": 0.0, "BNBUSDT": 0.0}
    weights = tilted_pair_weights({"BTCUSDT", "ETHUSDT"}, scores)
    assert weights["BTCUSDT"] == 0.75 and weights["ETHUSDT"] == 0.25
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    single = tilted_pair_weights({"SOLUSDT"}, {symbol: 0.0 for symbol in scores})
    assert single["SOLUSDT"] == 1.0 and sum(single.values()) == 1.0
    print("HYB-005 helper tests passed")


if __name__ == "__main__":
    main()
