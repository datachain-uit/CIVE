"""Common causal decision contract for the three experimental arms."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Literal

Arm = Literal["tech-only", "llm-only", "tech-plus-llm"]
Action = Literal["enter-long", "hold", "exit", "flat"]

@dataclass(frozen=True)
class ArmDecision:
    experiment_id: str
    arm: Arm
    symbol: str
    decision_timestamp_ms: int
    earliest_fill_timestamp_ms: int
    action: Action
    score: float | None
    source_snapshot_hash: str
    pipeline_hash: str
    reason_code: str

    def validate(self) -> None:
        if self.earliest_fill_timestamp_ms <= self.decision_timestamp_ms:
            raise ValueError("fill must occur strictly after the decision cutoff")
        if not self.symbol.endswith("USDT"):
            raise ValueError("controlled experiment requires canonical USDT symbols")
        if len(self.source_snapshot_hash) != 64 or len(self.pipeline_hash) != 64:
            raise ValueError("snapshot and pipeline hashes must be SHA-256 digests")
        if self.arm == "tech-only" and self.score is not None:
            raise ValueError("Tech-only must not carry an AI assessment score")

    def to_payload(self) -> dict:
        self.validate()
        return asdict(self)
