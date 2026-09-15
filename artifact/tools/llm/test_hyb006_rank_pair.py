"""Small deterministic unit checks for HYB-006 weighting."""
from hyb005_cross_asset_common import SYMBOLS
from hyb006_rank_pair_common import pair_weights
from evaluate_hyb006_rank_pair_reallocation import arm_series, turnovers


def main() -> None:
    selected = ("BTCUSDT", "ETHUSDT")
    neutral = pair_weights(selected, {symbol: 0.0 for symbol in SYMBOLS})
    assert neutral["BTCUSDT"] == 0.5 and neutral["ETHUSDT"] == 0.5
    positive = pair_weights(selected, {**{symbol: 0.0 for symbol in SYMBOLS}, "BTCUSDT": 1.0, "ETHUSDT": -1.0})
    assert positive["BTCUSDT"] == 0.75 and positive["ETHUSDT"] == 0.25
    assert abs(sum(positive.values()) - 1.0) < 1e-12
    assert all(0.0 <= value <= 0.75 for value in positive.values())
    rows = [
        {"index": 0, "base_weights": {symbol: (0.5 if symbol in {"BTCUSDT", "ETHUSDT"} else 0.0) for symbol in SYMBOLS}},
        {"index": 1, "base_weights": {symbol: (0.5 if symbol in {"ETHUSDT", "XRPUSDT"} else 0.0) for symbol in SYMBOLS}},
    ]
    assert turnovers(rows, "base_weights") == [1.0, 0.5]
    closes = {symbol: [100.0, 100.0, 100.0] for symbol in SYMBOLS}
    closes["BTCUSDT"] = [100.0, 110.0, 110.0]
    closes["XRPUSDT"] = [100.0, 100.0, 110.0]
    series = arm_series(rows, closes, "base_weights", 0.001)
    assert all(abs(actual - expected) < 1e-12 for actual, expected in zip(series["gross"], [0.05, 0.05], strict=True))
    assert all(abs(actual - expected) < 1e-12 for actual, expected in zip(series["net"], [0.049, 0.0495], strict=True))
    print("HYB-006 helper tests passed")


if __name__ == "__main__":
    main()
