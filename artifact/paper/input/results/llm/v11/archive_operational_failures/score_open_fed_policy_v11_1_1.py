"""V11.1.1 scorer: fixed validator delegation for evidence alignment."""
from __future__ import annotations
from difflib import SequenceMatcher
import score_open_fed_policy_v11 as base

BASE_VALIDATE = base.validate

def align_evidence(text: str, evidence: str) -> tuple[str, bool]:
    if evidence in text: return evidence, False
    match = SequenceMatcher(None, text, evidence, autojunk=False).find_longest_match()
    aligned = text[match.a:match.a + match.size].strip()
    if len(aligned) < 32: raise ValueError("evidence_span has no sufficiently long exact source segment")
    return aligned[:240], True

def validate(result: object, expected: dict) -> dict:
    if not isinstance(result, dict): raise ValueError("result must be an object")
    candidate = dict(result)
    evidence, fallback = align_evidence(expected["text"], candidate.get("evidence_span", ""))
    candidate["evidence_span"] = evidence
    return {**BASE_VALIDATE(candidate, expected), "evidence_alignment_fallback": fallback}

if __name__ == "__main__":
    base.validate = validate
    base.main()
