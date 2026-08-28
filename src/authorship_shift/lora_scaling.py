"""Reversible, inference-only scaling of a LoRA adapter's residual contribution.

A PEFT LoRA layer computes ``base(x) + B(A(x)) * scaling`` where ``scaling`` is
``lora_alpha / r``. Multiplying that one float by a factor scales the learned
residual and nothing else: base weights are untouched, adapter tensors on disk
are untouched, prompts and sampling are untouched, and nothing is merged.

Why this module exists rather than calling PEFT's ``scale_layer``:

* ``scale_layer(s)`` multiplies the *current* scaling in place, so calling it
  twice compounds. Sweeping 0.00, 0.25, 0.50 by that route silently produces
  0.00, 0.00, 0.00 once the first call has zeroed the value. Every factor here
  is applied against a baseline captured at construction, so a sweep is exact
  and order-independent.
* ``unscale_layer()`` divides back, which cannot recover from a zero and can
  drift under repeated float round-trips. Restoration here writes the captured
  baseline back verbatim.

Editing ``lora_alpha`` in ``adapter_config.json`` would be mathematically
equivalent, but it mutates a frozen artifact on disk. This is runtime-only.

The layer protocol is deliberately narrow -- any object with a ``scaling`` dict
mapping adapter name to float -- so the logic is testable without torch.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any, Iterable, Iterator


def find_lora_layers(model: Any) -> list[Any]:
    """Every submodule carrying a LoRA ``scaling`` mapping.

    Accepts a torch module (uses ``.modules()``) or a plain iterable of layers.
    """

    candidates: Iterable[Any]
    if hasattr(model, "modules") and callable(model.modules):
        candidates = model.modules()
    else:
        candidates = model

    layers = []
    for module in candidates:
        scaling = getattr(module, "scaling", None)
        if isinstance(scaling, dict) and scaling and all(
            isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in scaling.items()
        ):
            layers.append(module)
    return layers


class LoraScaler:
    """Scales LoRA residuals against a baseline captured at construction.

    Construct once, before any scaling is applied. ``apply`` is absolute, not
    cumulative, so repeated calls with different factors are exact.
    """

    def __init__(self, model: Any, *, adapter_names: Iterable[str] | None = None) -> None:
        self.layers = find_lora_layers(model)
        if not self.layers:
            raise ValueError(
                "no LoRA layers found; refusing to run a scaling sweep against a model "
                "with no adapter attached"
            )
        wanted = set(adapter_names) if adapter_names is not None else None
        self._baseline: list[dict[str, float]] = []
        for layer in self.layers:
            keys = layer.scaling.keys() if wanted is None else (wanted & layer.scaling.keys())
            self._baseline.append({k: float(layer.scaling[k]) for k in keys})
        if not any(self._baseline):
            raise ValueError(f"no adapter named in {sorted(wanted or [])} on any LoRA layer")

    @property
    def baseline(self) -> list[dict[str, float]]:
        """The scaling values captured at construction, per layer."""

        return [dict(b) for b in self._baseline]

    def apply(self, factor: float) -> None:
        """Set every tracked scaling to ``baseline * factor``.

        Absolute, never cumulative. ``factor=1.0`` restores the trained value
        exactly; ``factor=0.0`` makes the residual identically zero.
        """

        if isinstance(factor, bool) or not isinstance(factor, (int, float)):
            raise TypeError(f"factor must be a real number, got {type(factor).__name__}")
        if not math.isfinite(factor):
            raise ValueError(f"factor must be finite, got {factor!r}")
        if factor < 0:
            raise ValueError(f"factor must be non-negative, got {factor!r}")

        for layer, base in zip(self.layers, self._baseline):
            for name, value in base.items():
                layer.scaling[name] = value * factor

    def restore(self) -> None:
        """Write the captured baseline back verbatim."""

        for layer, base in zip(self.layers, self._baseline):
            for name, value in base.items():
                layer.scaling[name] = value

    def current(self) -> list[dict[str, float]]:
        """The live scaling values for the tracked adapters, per layer."""

        return [{k: float(layer.scaling[k]) for k in base}
                for layer, base in zip(self.layers, self._baseline)]

    def residual_scale_ratio(self) -> list[float]:
        """Live scaling divided by baseline, per tracked entry.

        The LoRA residual is linear in ``scaling``, so this is exactly the factor
        by which each layer's residual contribution has been multiplied.
        """

        out = []
        for live, base in zip(self.current(), self._baseline):
            for name, value in base.items():
                out.append(live[name] / value if value else 0.0)
        return out


@contextmanager
def scaled_lora(model: Any, factor: float, *, adapter_names: Iterable[str] | None = None
                ) -> Iterator[LoraScaler]:
    """Temporarily scale LoRA residuals, restoring the baseline on exit.

    Restoration runs even if the body raises, so a failed generation cannot
    leave the model in a scaled state for the next condition.
    """

    scaler = LoraScaler(model, adapter_names=adapter_names)
    scaler.apply(factor)
    try:
        yield scaler
    finally:
        scaler.restore()
