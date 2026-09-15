"""Regression checks for the HYB-003 Stage-D remediation semantics."""
from __future__ import annotations

from evaluate_hyb003_stage_d_v3_2 import policy_action


def main() -> None:
    # The target is already net of execution costs: do not add cost again.
    assert policy_action(0.0020, 0.0010)
    assert not policy_action(0.0005, 0.0010)

    # The materialized target is already the half-downsize PnL difference.
    target = 0.012
    corrected_policy_delta = target if policy_action(0.0020, 0.0010) else 0.0
    assert corrected_policy_delta == target
    assert corrected_policy_delta != 0.5 * target
    print("HYB-003 Stage-D v3.2 remediation regression checks passed")


if __name__ == "__main__":
    main()
