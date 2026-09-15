import copy
import json
import unittest
from pathlib import Path
from controlled_arm_contract import ArmDecision
from freeze_experiment import build_freeze, validate_holdout, verify_freeze

ROOT = Path(__file__).resolve().parents[1]

class ControlledExperimentFreezeTest(unittest.TestCase):
    def test_decision_requires_strictly_later_fill(self):
        value = ArmDecision("x", "tech-only", "BTCUSDT", 10, 10, "hold", None, "a"*64, "b"*64, "test")
        with self.assertRaises(ValueError): value.validate()

    def test_tech_decision_rejects_ai_score(self):
        value = ArmDecision("x", "tech-only", "BTCUSDT", 10, 11, "hold", .2, "a"*64, "b"*64, "test")
        with self.assertRaises(ValueError): value.validate()

    def test_holdout_rejects_overlap(self):
        value = json.loads((ROOT/"configs"/"sealed_forward_holdout_v1.json").read_text(encoding="utf-8"))
        broken = copy.deepcopy(value); broken["start_utc"] = "2026-08-11T00:00:00Z"
        with self.assertRaises(ValueError): validate_holdout(broken, 1786406400000)

    def test_freeze_records_unresolved_ai_arms(self):
        freeze = build_freeze(ROOT)
        self.assertEqual(freeze["freeze_id"], "tech-control-v1-freeze")
        self.assertEqual(len(freeze["configuration_hashes"]), 3)
        self.assertEqual(len(freeze["unresolved_requirements"]), 2)
        verify_freeze(freeze)

    def test_verify_rejects_mutated_hash(self):
        freeze = build_freeze(ROOT)
        freeze["configuration_files"]["technical_control_v1.json"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_freeze(freeze)

if __name__ == "__main__": unittest.main()
