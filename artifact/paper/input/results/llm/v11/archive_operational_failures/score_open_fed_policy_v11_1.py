"""V11.1 scorer: retain scores and align non-contiguous evidence deterministically."""
from __future__ import annotations

from difflib import SequenceMatcher

import score_open_fed_policy_v11 as base


def align_evidence(text: str, evidence: str) -> tuple[str, bool]:
    if evidence in text:
        return evidence, False
    match = SequenceMatcher(None, text, evidence, autojunk=False).find_longest_match()
    aligned = text[match.a:match.a + match.size].strip()
    if len(aligned) < 32:
        raise ValueError("evidence_span has no sufficiently long exact source segment")
    return aligned[:240], True


def validate(result: object, expected: dict) -> dict:
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    candidate = dict(result)
    evidence, fallback = align_evidence(expected["text"], candidate.get("evidence_span", ""))
    candidate["evidence_span"] = evidence
    validated = base.validate(candidate, expected)
    return {**validated, "evidence_alignment_fallback": fallback}


if __name__ == "__main__":
    base.validate = validate
    base.main()
