# Skill 07 — Candidate Selector

Select candidates for scarce external evaluation using ONLY the supplied internal evidence.

Priority order:
1. Fidelity is a hard gate. Reject anything below 0.96 or with substantive claim changes.
2. Quality must be equal to or better than the source.
3. Among survivors, prefer genuine structural diversity rather than cosmetic paraphrase.
4. Prefer a small number of meaningfully different candidates over many near-duplicates.

Do not guess what any commercial AI detector will do. Do not invent detector scores.

Return JSON only:
{
  "recommended_candidate_ids": [],
  "rejected": [{"candidate_id": "...", "reason": "..."}],
  "selection_reasoning": "..."
}

CANDIDATES:
{{CANDIDATES}}
