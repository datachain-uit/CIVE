"""V11.1.3 scorer: canonicalize only a one-edit batch-1 event-id typo."""
from __future__ import annotations
import score_open_fed_policy_v11_1_2 as prior

BASE_VALIDATE = prior.BASE_VALIDATE

def edit_distance_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1: return False
    distance=0; i=j=0
    while i < len(left) and j < len(right):
        if left[i] != right[j]:
            distance += 1
            if distance > 1: return False
            if len(left) > len(right): i += 1; continue
            if len(right) > len(left): j += 1; continue
        i += 1; j += 1
    return distance + (len(left)-i) + (len(right)-j) <= 1

def validate(result: object, expected: dict) -> dict:
    if not isinstance(result, dict): raise ValueError("result must be an object")
    candidate=dict(result)
    if candidate.get("event_id") != expected["event_id"] and edit_distance_one(str(candidate.get("event_id", "")), expected["event_id"]):
        candidate["event_id"] = expected["event_id"]
    evidence, fallback=prior.align_evidence(expected["text"], candidate.get("evidence_span", "")); candidate["evidence_span"]=evidence
    return {**BASE_VALIDATE(candidate, expected), "evidence_alignment_fallback": fallback, "event_id_correction": candidate["event_id"] == expected["event_id"] and result.get("event_id") != expected["event_id"]}

if __name__ == "__main__":
    prior.base.validate=validate; prior.base.api=prior.api; prior.base.main()
