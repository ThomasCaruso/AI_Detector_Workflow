"""Tests for reversible inference-only LoRA scaling. Synthetic fakes only."""

from __future__ import annotations

import pytest

from authorship_shift.lora_scaling import (
    LoraScaler,
    find_lora_layers,
    scaled_lora,
)


class FakeLoraLayer:
    """Minimal stand-in for a PEFT LoraLayer: a dict of adapter -> scaling."""

    def __init__(self, scaling: dict[str, float]):
        self.scaling = dict(scaling)

    def residual(self, x: float, adapter: str = "default") -> float:
        """LoRA residual is linear in scaling; 2.0 stands in for B(A(x))/x."""

        return 2.0 * x * self.scaling[adapter]


class FakePlainLayer:
    def __init__(self):
        self.weight = 1.0


def make_model(n: int = 3, scaling: float = 2.0) -> list:
    return [FakeLoraLayer({"default": scaling}) for _ in range(n)] + [FakePlainLayer()]


# --- discovery -------------------------------------------------------------

def test_finds_only_lora_layers():
    model = make_model(3)

    assert len(find_lora_layers(model)) == 3


def test_ignores_layers_with_empty_scaling():
    assert find_lora_layers([FakeLoraLayer({})]) == []


def test_ignores_non_numeric_scaling_values():
    bogus = FakeLoraLayer({"default": 1.0})
    bogus.scaling = {"default": "1.0"}

    assert find_lora_layers([bogus]) == []


def test_ignores_bool_scaling_values():
    """bool is an int subclass; a True scaling is a bug, not a valid layer."""

    bogus = FakeLoraLayer({"default": 1.0})
    bogus.scaling = {"default": True}

    assert find_lora_layers([bogus]) == []


def test_accepts_a_torch_like_model_exposing_modules():
    class Model:
        def __init__(self, layers):
            self._layers = layers

        def modules(self):
            return iter(self._layers)

    assert len(find_lora_layers(Model(make_model(2)))) == 2


def test_refuses_a_model_with_no_adapter():
    with pytest.raises(ValueError, match="no LoRA layers found"):
        LoraScaler([FakePlainLayer()])


# --- the property the whole diagnostic rests on ----------------------------

def test_scale_zero_makes_the_residual_exactly_zero():
    model = make_model(1, scaling=2.0)
    LoraScaler(model).apply(0.0)

    assert model[0].scaling["default"] == 0.0
    assert model[0].residual(5.0) == 0.0


def test_scale_one_reproduces_the_trained_scaling_exactly():
    model = make_model(1, scaling=0.1)
    baseline = model[0].scaling["default"]
    LoraScaler(model).apply(1.0)

    assert model[0].scaling["default"] == baseline


def test_residual_is_proportional_to_the_factor():
    model = make_model(1, scaling=2.0)
    scaler = LoraScaler(model)
    full = model[0].residual(3.0)

    scaler.apply(0.25)
    assert model[0].residual(3.0) == pytest.approx(0.25 * full)
    scaler.apply(0.5)
    assert model[0].residual(3.0) == pytest.approx(0.5 * full)


def test_residual_scale_ratio_reports_the_applied_factor():
    model = make_model(3, scaling=2.0)
    scaler = LoraScaler(model)
    scaler.apply(0.75)

    assert scaler.residual_scale_ratio() == pytest.approx([0.75] * 3)


def test_ratio_is_monotone_across_the_frozen_sweep():
    model = make_model(2, scaling=2.0)
    scaler = LoraScaler(model)
    seen = []
    for factor in (0.0, 0.25, 0.5, 0.75, 1.0):
        scaler.apply(factor)
        seen.append(scaler.residual_scale_ratio()[0])

    assert seen == sorted(seen)
    assert seen == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])


# --- the PEFT footgun this module exists to avoid --------------------------

def test_apply_is_absolute_not_cumulative():
    """PEFT's scale_layer multiplies in place; a sweep would compound. This does not."""

    model = make_model(1, scaling=2.0)
    scaler = LoraScaler(model)

    scaler.apply(0.5)
    scaler.apply(0.5)

    assert model[0].scaling["default"] == pytest.approx(1.0)  # not 0.5


def test_a_sweep_through_zero_still_recovers_full_strength():
    """Dividing back cannot recover from zero; writing the baseline can."""

    model = make_model(1, scaling=2.0)
    scaler = LoraScaler(model)

    scaler.apply(0.0)
    scaler.apply(1.0)

    assert model[0].scaling["default"] == 2.0


def test_sweep_order_does_not_matter():
    a, b = make_model(1, 2.0), make_model(1, 2.0)
    sa, sb = LoraScaler(a), LoraScaler(b)
    for f in (0.0, 0.25, 0.5, 0.75):
        sa.apply(f)
    for f in (0.75, 0.5, 0.25, 0.0):
        sb.apply(f)
    sa.apply(0.5)
    sb.apply(0.5)

    assert a[0].scaling["default"] == b[0].scaling["default"]


# --- reversibility ---------------------------------------------------------

def test_restore_returns_the_exact_original_float():
    model = make_model(1, scaling=0.1 + 0.2)  # deliberately not exactly 0.3
    original = model[0].scaling["default"]
    scaler = LoraScaler(model)

    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        scaler.apply(f)
    scaler.restore()

    assert model[0].scaling["default"] == original


def test_context_manager_restores_on_normal_exit():
    model = make_model(2, scaling=2.0)
    with scaled_lora(model, 0.25):
        assert model[0].scaling["default"] == pytest.approx(0.5)

    assert model[0].scaling["default"] == 2.0


def test_context_manager_restores_even_when_the_body_raises():
    """A failed generation must not leak a scaled model into the next condition."""

    model = make_model(2, scaling=2.0)
    with pytest.raises(RuntimeError):
        with scaled_lora(model, 0.0):
            raise RuntimeError("generation blew up")

    assert model[0].scaling["default"] == 2.0


def test_baseline_snapshot_is_not_aliased_to_live_state():
    model = make_model(1, scaling=2.0)
    scaler = LoraScaler(model)
    scaler.apply(0.0)

    assert scaler.baseline[0]["default"] == 2.0


# --- multiple adapters -----------------------------------------------------

def test_scales_every_adapter_by_default():
    model = [FakeLoraLayer({"default": 2.0, "other": 4.0})]
    LoraScaler(model).apply(0.5)

    assert model[0].scaling == {"default": 1.0, "other": 2.0}


def test_can_restrict_to_one_adapter_leaving_others_untouched():
    model = [FakeLoraLayer({"default": 2.0, "other": 4.0})]
    LoraScaler(model, adapter_names=["default"]).apply(0.0)

    assert model[0].scaling == {"default": 0.0, "other": 4.0}


def test_unknown_adapter_name_is_rejected():
    with pytest.raises(ValueError, match="no adapter named"):
        LoraScaler([FakeLoraLayer({"default": 2.0})], adapter_names=["missing"])


# --- input validation ------------------------------------------------------

@pytest.mark.parametrize("bad", [-0.5, float("nan"), float("inf")])
def test_rejects_invalid_factors(bad):
    with pytest.raises(ValueError):
        LoraScaler(make_model(1)).apply(bad)


def test_rejects_non_numeric_factor():
    with pytest.raises(TypeError, match="must be a real number"):
        LoraScaler(make_model(1)).apply("1.0")


def test_rejects_bool_factor():
    with pytest.raises(TypeError, match="must be a real number"):
        LoraScaler(make_model(1)).apply(True)


def test_factor_above_one_is_allowed():
    """Amplification is not part of the frozen sweep but is not an error."""

    model = make_model(1, scaling=2.0)
    LoraScaler(model).apply(2.0)

    assert model[0].scaling["default"] == 4.0
