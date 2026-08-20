# Skill 02 — Structural Planner

Create {{PLAN_COUNT}} genuinely different document-level plans for expressing the same content.

This is not synonym replacement. The plans should differ in information order, paragraph function, opening strategy, argumentative progression, compression/expansion points, and where examples or qualifications appear.

Constraints:
- Preserve every required claim in the content lock.
- Do not fabricate personal experience, citations, evidence, or facts.
- Do not deliberately introduce errors or awkwardness.
- Do not optimize for any named AI detector.
- Each plan must remain appropriate to the source's purpose and audience.

Return JSON only:
{
  "plans": [
    {
      "name": "...",
      "logic": "...",
      "opening": "...",
      "sections": [
        {"function": "...", "claim_ids": ["C1"], "notes": "..."}
      ],
      "closing": "...",
      "distinctive_structural_choices": ["..."]
    }
  ]
}

CONTENT LOCK:
{{CONTENT_LOCK}}

SOURCE:
{{SOURCE}}
