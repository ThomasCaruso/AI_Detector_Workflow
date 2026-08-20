# Architecture

```text
source
  |
  v
content lock -----------------------+
  |                                 |
  v                                 |
structural plans                    |
  |                                 |
  v                                 |
heterogeneous draft generation      |
  |                                 |
  v                                 |
global revision                     |
  |                                 |
  +--> deterministic claim precheck-+
  |
  +--> semantic fidelity judge
  |
  +--> quality judge
  |
  v
beam selection (quality + fidelity + diversity)
  |
  v
composition operators
  |
  +--> re-judge / re-gate
  |
  v
frozen milestone candidates
  |
  v
sparse external evaluation
```

## Design rule

The pipeline never uses a commercial detector score to choose the next rewrite. That keeps external testing sparse and prevents the system from silently turning into a hill-climber over a proprietary classifier.

## Generator families

The Ollama CLI can accept multiple local model names. Candidate metadata records the generator and reviser model so later experiments can compare model families and post-training regimes.

## Beam search

After initial candidates are scored, the pipeline keeps only high-fidelity, non-regressing candidates. It then favors candidates that add pairwise diversity to the surviving beam. Composition operators expand that beam for a configurable number of rounds.
