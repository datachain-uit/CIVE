"""Deterministic unit checks for HYB-008 helpers."""
from hyb008_conditional_downside_common import BAR_MS, tech_features
from evaluate_hyb008_conditional_downside import shifted_semantics


def main():
    ts = 18 * BAR_MS
    opens = {i * BAR_MS: 100.0 + i for i in range(19)}
    features = tech_features("ETHUSDT", ts, ["ETHUSDT", "SOLUSDT"], opens)
    assert features is not None
    assert features["tech_rank_first"] == 1.0
    assert features["tech_asset_sol"] == 0.0
    assert shifted_semantics([{"x": i} for i in range(4)], 1) == [{"x": 3}, {"x": 0}, {"x": 1}, {"x": 2}]
    print("HYB-008 helper tests passed")


if __name__ == "__main__":
    main()
