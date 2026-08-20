# Skill 06 — Quality Judge

Compare the candidate to the source as writing. Ignore authorship and AI detection entirely.

Rate both source and candidate from 1-10 on:
- clarity
- precision
- coherence
- information density
- rhetorical effectiveness
- sentence-level control
- paragraph-level control
- audience fit

Then compute candidate_minus_source as the mean candidate score minus mean source score.

Penalize:
- vague abstraction
- redundant conclusions
- formulaic transitions
- awkward synonym replacement
- choppy pseudo-human writing
- invented personality
- unnecessary verbosity
- loss of technical precision

Return JSON only:
{
  "source": {"clarity": 0, "precision": 0, "coherence": 0, "information_density": 0, "rhetorical_effectiveness": 0, "sentence_control": 0, "paragraph_control": 0, "audience_fit": 0},
  "candidate": {"clarity": 0, "precision": 0, "coherence": 0, "information_density": 0, "rhetorical_effectiveness": 0, "sentence_control": 0, "paragraph_control": 0, "audience_fit": 0},
  "candidate_minus_source": 0.0,
  "pass": false,
  "main_improvements": [],
  "main_regressions": []
}

SOURCE:
{{SOURCE}}

CANDIDATE:
{{CANDIDATE}}
