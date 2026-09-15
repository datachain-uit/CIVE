"""Record the HYB-004 v1.1 causal-initialization remediation contract."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eth_transfer_v17_common import sha256, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-config", type=Path, required=True)
    parser.add_argument("--parent-result", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parent = json.loads(args.parent_config.read_text(encoding="utf-8"))
    parent["experiment_id"] = "HYB-004-Bennett-adaptive-MSFE-ETH-transfer-v1.1-remediation"
    parent["frozen_at"] = datetime.now(timezone.utc).isoformat()
    parent["stage"] = "POST_OUTCOME_REMEDIATION_NOT_VALIDATION"
    parent["outcomes_consulted_for_this_design"] = True
    parent["adaptive_fusion"]["initialization"] = "0.5 Tech / 0.5 LLM until 30 matured OOS forecast errors are available within each fold"
    parent["sources"]["hybrid_evaluator"] = {"path": str(args.evaluator), "sha256": sha256(args.evaluator)}
    parent["supersedes"] = {
        "config": {"path": str(args.parent_config), "sha256": sha256(args.parent_config)},
        "result": {"path": str(args.parent_result), "sha256": sha256(args.parent_result)},
        "reason": "v1 initialization used fitted train residuals rather than genuine matured forecast errors",
    }
    parent["holdout_authorization"] = False
    write_json(args.output, parent)
    print(json.dumps({"output": str(args.output), "status": parent["stage"]}, indent=2))


if __name__ == "__main__":
    main()
