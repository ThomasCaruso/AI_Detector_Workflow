# Skill 05 — Semantic Fidelity Judge

Compare the candidate against the source and content lock. Be strict.

Score semantic fidelity from 0.0 to 1.0. A score above 0.96 should require that essentially all required propositions, qualifications, numbers, names, causal direction, and certainty levels are preserved.

Identify:
- missing required claims
- altered claims
- added factual claims
- changed certainty
- changed causal relationships
- immutable-item violations

Return JSON only:
{
  "score": 0.0,
  "required_claims_total": 0,
  "required_claims_preserved": 0,
  "missing_claim_ids": [],
  "altered_claim_ids": [],
  "added_claims": [],
  "certainty_changes": [],
  "immutable_violations": [],
  "pass": false,
  "reason": "..."
}

SOURCE:
{{SOURCE}}

CONTENT LOCK:
{{CONTENT_LOCK}}

CANDIDATE:
{{CANDIDATE}}
