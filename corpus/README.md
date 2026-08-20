# Corpus

Place `.txt` samples here if you want a development/holdout split. Do not commit private or copyrighted documents you do not have permission to publish.

Create a deterministic split:

```bash
authorship-shift split-corpus corpus --holdout 0.2 --seed v1
```

The resulting `split.json` should be frozen before using the held-out set for final validation.
