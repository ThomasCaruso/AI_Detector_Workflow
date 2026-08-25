"""Holdout evaluation contract for the personal-style experiment.

Implements the protocol frozen in
``research/lora/configs/personal_b_eval_protocol.json`` before the adapter
existed. Everything the comparison depends on is derived here, deterministically
and without any ML dependency, so the contract can be validated on a machine
that will never load a model.

The single intended variable across the two conditions is whether the adapter is
loaded. Prompt, sampling settings, and per-example seed are identical for both,
which is enforced rather than assumed: :func:`build_generation_plan` produces one
prompt and one seed per example and hands the same objects to both conditions.

Target text never reaches a prompt. The generation prompt is rendered from the
semantic plan alone; :func:`assert_no_target_leakage` is the check that says so
out loud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import random
import re
from typing import Any, Iterable, Mapping, Sequence

CONDITION_BASE = "base"
CONDITION_ADAPTER = "adapter"
REQUIRED_CONDITIONS: tuple[str, ...] = (CONDITION_BASE, CONDITION_ADAPTER)

# Sampling keys that must be identical across conditions.
GENERATION_KEYS: tuple[str, ...] = (
    "do_sample",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "max_new_tokens",
    "num_return_sequences",
    "repetition_penalty",
)


class ProtocolViolation(RuntimeError):
    """The evaluation contract was not satisfied."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def load_protocol(path) -> dict[str, Any]:
    """Load and structurally validate the frozen protocol."""

    from pathlib import Path

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ProtocolViolation("unsupported eval protocol schema_version")
    for key in ("protocol_id", "base_model", "base_model_revision"):
        if not str(payload.get(key, "")).strip():
            raise ProtocolViolation(f"eval protocol requires {key}")

    adapter_sha = payload.get("adapter_artifact_sha256")
    if not adapter_sha:
        raise ProtocolViolation(
            "adapter_artifact_sha256 is not populated; the adapter must be frozen "
            "and bound into the protocol before any holdout generation begins"
        )

    conditions = tuple(payload.get("conditions") or ())
    if conditions != REQUIRED_CONDITIONS:
        raise ProtocolViolation(
            f"protocol conditions {conditions} must be exactly {REQUIRED_CONDITIONS}"
        )

    prompt = payload.get("prompt", {})
    if prompt.get("condition_specific_prompting") is not False:
        raise ProtocolViolation("condition_specific_prompting must be false")
    if prompt.get("enable_thinking") is not False:
        raise ProtocolViolation("enable_thinking must be false")

    generation = payload.get("generation", {})
    for key in GENERATION_KEYS + ("evaluation_seed",):
        if key not in generation:
            raise ProtocolViolation(f"protocol generation block requires {key}")

    contract = payload.get("generation_contract", {})
    for key in (
        "generate_all_outputs_before_scoring",
        "same_prompt_for_both_conditions",
        "same_generation_settings_for_both_conditions",
        "same_per_example_seed_for_both_conditions",
        "no_regeneration_after_scoring_begins",
        "no_hyperparameter_changes_after_holdout_reveal",
    ):
        if contract.get(key) is not True:
            raise ProtocolViolation(f"generation_contract.{key} must be true")

    blinding = payload.get("blinding", {})
    if blinding.get("enabled") is not True:
        raise ProtocolViolation("blinding must be enabled")
    if "blind_seed" not in blinding:
        raise ProtocolViolation("blinding requires blind_seed")

    return payload


def protocol_sha256(protocol: Mapping[str, Any]) -> str:
    """Digest of the protocol content, so a run records which one it obeyed."""

    blob = json.dumps(protocol, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic per-example seed
# ---------------------------------------------------------------------------


def per_example_seed(protocol_id: str, example_id: str, evaluation_seed: int) -> int:
    """The protocol's seed rule, verbatim.

    ``sha256(protocol_id + ':' + example_id)`` low 32 bits, xor evaluation_seed.
    The same value is used for both conditions, so sampling noise is held fixed
    and the only difference between a pair of outputs is the adapter.
    """

    digest = hashlib.sha256(f"{protocol_id}:{example_id}".encode("utf-8")).hexdigest()
    low32 = int(digest, 16) & 0xFFFFFFFF
    return low32 ^ int(evaluation_seed)


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def render_generation_prompt(example) -> str:
    """Render the semantic-plan prompt.

    Byte-identical to ``train_personal_qlora.render_semantic_prompt``, which the
    protocol names as its ``template_source``; a test asserts that equality so
    the two cannot drift apart. Reads only the semantic plan - never
    ``target_text``.
    """

    atoms = "\n".join(f"- {item}" for item in example.content_atoms)
    immutables = (
        "\n".join(f"- {item}" for item in example.immutable_details)
        if example.immutable_details
        else "- none"
    )
    qualifications = (
        "\n".join(f"- {item}" for item in example.required_qualifications)
        if example.required_qualifications
        else "- none"
    )
    return f"""Write the requested prose from the semantic plan below.

Task:
{example.instruction}

Content atoms:
{atoms}

Immutable details:
{immutables}

Required qualifications:
{qualifications}

Preserve meaning, certainty, and supplied details. Do not invent factual claims or names."""


def _spans(text: str, size: int) -> set[str]:
    words = text.lower().split()
    if len(words) < size:
        return set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def assert_no_target_leakage(
    example,
    *,
    min_span: int = 8,
    max_immutable_detail_words: int = 30,
) -> None:
    """Fail if a prompt-bearing field leaks the held-out target.

    This mirrors the contract frozen at annotation time rather than imposing a
    stricter one at evaluation time.

    ``content_atoms``, ``required_qualifications`` and ``instruction`` describe
    the shape of a claim and must not reproduce the target's wording, so a shared
    span of ``min_span`` words is a violation.

    ``immutable_details`` are exempt from the span rule by design: they are the
    names, figures and concrete particulars the model is *supposed* to be given,
    and the frozen contract requires them to agree with the target exactly.
    Forbidding overlap there would forbid the field from doing its job. They are
    bounded a different way - a word cap, so a whole passage cannot be smuggled
    in as a "detail", and a check that no detail is wholly contained in the
    target, which would make it a copied sentence rather than a particular.
    """

    target = example.target_text
    target_spans = _spans(target, min_span)
    normalized_target = " ".join(target.split()).lower()

    for label, values in (
        ("content atom", tuple(example.content_atoms)),
        ("required qualification", tuple(example.required_qualifications)),
        ("instruction", (example.instruction,)),
    ):
        for value in values:
            shared = _spans(value, min_span) & target_spans
            if shared:
                raise ProtocolViolation(
                    f"{example.id}: {label} shares a {min_span}-word span with the "
                    f"holdout target: {sorted(shared)[0]!r}"
                )

    for value in example.immutable_details:
        words = value.split()
        if len(words) > max_immutable_detail_words:
            raise ProtocolViolation(
                f"{example.id}: immutable detail runs {len(words)} words, over the "
                f"{max_immutable_detail_words}-word cap"
            )
        if len(words) >= 12 and " ".join(words).lower() in normalized_target:
            raise ProtocolViolation(
                f"{example.id}: immutable detail is copied wholesale from the target: "
                f"{value!r}"
            )


# ---------------------------------------------------------------------------
# Verbatim target-overlap diagnostic
# ---------------------------------------------------------------------------

# Function words a model inserts when stitching supplied details into prose.
# Deliberately small: every addition here increases the risk of suppressing a
# genuine overlap, so the list covers determiners, conjunctions, copulas and the
# prepositions that appear in list-joining, and nothing else.
_STITCH_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "to", "for", "with", "as",
        "was", "were", "is", "are", "also", "then", "in", "on", "at",
        "by", "from", "that", "this",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s]+")


def normalize_for_overlap(text: str) -> list[str]:
    """Lowercase and drop punctuation, so an Oxford comma cannot change a match."""

    return _PUNCT_RE.sub(" ", text.lower()).split()


def _content_words(words: Sequence[str]) -> list[str]:
    return [word for word in words if word not in _STITCH_WORDS]


@dataclass(frozen=True)
class OverlapDiagnostic:
    """Verbatim overlap between one output and one target.

    Reports raw and eligible counts separately and always. Collapsing them into a
    single number is what made an earlier version of this diagnostic look like
    evidence of memorisation when it was measuring supplied details being
    correctly restated.
    """

    span_words: int
    raw_spans: tuple[str, ...]
    supplied_spans: tuple[str, ...]
    eligible_spans: tuple[str, ...]

    @property
    def raw_count(self) -> int:
        return len(self.raw_spans)

    @property
    def supplied_count(self) -> int:
        return len(self.supplied_spans)

    @property
    def eligible_count(self) -> int:
        return len(self.eligible_spans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_words": self.span_words,
            "raw_count": self.raw_count,
            "supplied_count": self.supplied_count,
            "eligible_count": self.eligible_count,
            "eligible_spans": list(self.eligible_spans),
        }


def _supplied_variants(immutable_details: Sequence[str]) -> list[str]:
    """Every contiguous run of supplied details, joined and connective-stripped.

    Prose naturally concatenates adjacent details ("lunch was X, and dinner was
    Y"), producing spans that cross a detail boundary and therefore match no
    single detail. Matching against contiguous runs catches those without
    licensing arbitrary recombination of unrelated details.
    """

    normalized = [normalize_for_overlap(detail) for detail in immutable_details]
    variants: list[str] = []
    for start in range(len(normalized)):
        joined: list[str] = []
        for end in range(start, len(normalized)):
            joined = joined + normalized[end]
            variants.append(" ".join(_content_words(joined)))
    return variants


def target_overlap_diagnostic(
    output_text: str,
    target_text: str,
    immutable_details: Sequence[str] = (),
    *,
    span_words: int = 8,
) -> OverlapDiagnostic:
    """Long verbatim spans shared by an output and a target.

    A span is attributed to the supplied plan when its content words appear
    contiguously inside some contiguous run of immutable details. Restating a
    detail the prompt provided is the model doing as it was told, not recall.

    What remains - ``eligible_spans`` - is the only part that could indicate the
    model reproducing wording it was not given. Note that for a held-out target
    the model never trained on, even eligible overlap cannot be memorisation of
    that target; measuring memorisation requires comparing outputs against
    TRAINING targets, which this function does not do.
    """

    output_words = normalize_for_overlap(output_text)
    target_words = normalize_for_overlap(target_text)

    target_spans = {
        " ".join(target_words[i : i + span_words])
        for i in range(len(target_words) - span_words + 1)
    }
    raw = sorted(
        {
            " ".join(output_words[i : i + span_words])
            for i in range(len(output_words) - span_words + 1)
        }
        & target_spans
    )

    variants = _supplied_variants(immutable_details)
    supplied: list[str] = []
    eligible: list[str] = []
    for span in raw:
        stripped = " ".join(_content_words(span.split()))
        if stripped and any(stripped in variant for variant in variants):
            supplied.append(span)
        else:
            eligible.append(span)

    return OverlapDiagnostic(
        span_words=span_words,
        raw_spans=tuple(raw),
        supplied_spans=tuple(supplied),
        eligible_spans=tuple(eligible),
    )


# ---------------------------------------------------------------------------
# Generation plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationUnit:
    """One holdout example: one prompt and one seed, shared by both conditions."""

    example_id: str
    source_id: str
    prompt: str
    seed: int


@dataclass(frozen=True)
class GenerationTask:
    """One (example, condition) pair to generate."""

    example_id: str
    condition: str
    prompt: str
    seed: int


@dataclass(frozen=True)
class GenerationPlan:
    protocol_id: str
    units: tuple[GenerationUnit, ...]
    tasks: tuple[GenerationTask, ...]
    generation_kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def expected_output_count(self) -> int:
        return len(self.tasks)


def order_examples(examples: Iterable[Any]) -> list[Any]:
    """Stable ascending example-id order, as the protocol requires."""

    return sorted(examples, key=lambda example: str(example.id))


def build_generation_plan(
    examples: Sequence[Any],
    protocol: Mapping[str, Any],
    *,
    check_target_leakage: bool = True,
) -> GenerationPlan:
    """Derive every prompt, seed, and task from the holdout set and protocol."""

    holdout = protocol.get("holdout", {})
    expected = int(holdout.get("expected_examples", 0))
    ordered = order_examples(examples)
    if len(ordered) != expected:
        raise ProtocolViolation(
            f"expected exactly {expected} holdout examples, got {len(ordered)}"
        )

    offending = sorted({str(example.split) for example in ordered} - {"holdout"})
    if offending:
        raise ProtocolViolation(f"non-holdout rows in the evaluation set: {offending}")

    ids = [str(example.id) for example in ordered]
    if len(set(ids)) != len(ids):
        raise ProtocolViolation("duplicate example ids in the holdout set")

    protocol_id = str(protocol["protocol_id"])
    evaluation_seed = int(protocol["generation"]["evaluation_seed"])

    units: list[GenerationUnit] = []
    for example in ordered:
        prompt = render_generation_prompt(example)
        if check_target_leakage:
            assert_no_target_leakage(example)
            # The rendered prompt must contain no field the plan did not supply.
            if example.target_text.strip() and example.target_text.strip() in prompt:
                raise ProtocolViolation(
                    f"{example.id}: rendered prompt contains the holdout target verbatim"
                )
        units.append(
            GenerationUnit(
                example_id=str(example.id),
                source_id=str(example.provenance.source_id),
                prompt=prompt,
                seed=per_example_seed(protocol_id, str(example.id), evaluation_seed),
            )
        )

    # Both conditions receive the SAME prompt object and the SAME seed. There is
    # no per-condition branch here, which is what makes the settings identical by
    # construction rather than by convention.
    tasks: list[GenerationTask] = []
    for unit in units:
        for condition in REQUIRED_CONDITIONS:
            tasks.append(
                GenerationTask(
                    example_id=unit.example_id,
                    condition=condition,
                    prompt=unit.prompt,
                    seed=unit.seed,
                )
            )

    generation = protocol["generation"]
    return GenerationPlan(
        protocol_id=protocol_id,
        units=tuple(units),
        tasks=tuple(tasks),
        generation_kwargs={key: generation[key] for key in GENERATION_KEYS},
    )


def verify_plan_contract(plan: GenerationPlan, protocol: Mapping[str, Any]) -> None:
    """Check the derived plan against the protocol's own stated expectations."""

    contract = protocol.get("generation_contract", {})
    expected_outputs = int(contract.get("expected_output_count", 0))
    if plan.expected_output_count != expected_outputs:
        raise ProtocolViolation(
            f"plan produces {plan.expected_output_count} outputs, protocol expects "
            f"{expected_outputs}"
        )

    by_example: dict[str, list[GenerationTask]] = {}
    for task in plan.tasks:
        by_example.setdefault(task.example_id, []).append(task)

    for example_id, tasks in by_example.items():
        conditions = tuple(task.condition for task in tasks)
        if conditions != REQUIRED_CONDITIONS:
            raise ProtocolViolation(
                f"{example_id}: conditions {conditions} != {REQUIRED_CONDITIONS}"
            )
        if len({task.prompt for task in tasks}) != 1:
            raise ProtocolViolation(f"{example_id}: prompts differ across conditions")
        if len({task.seed for task in tasks}) != 1:
            raise ProtocolViolation(f"{example_id}: seeds differ across conditions")


# ---------------------------------------------------------------------------
# Blinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlindAssignment:
    label: str
    example_id: str
    condition: str


def assign_blind_labels(
    plan: GenerationPlan, protocol: Mapping[str, Any]
) -> tuple[BlindAssignment, ...]:
    """Deterministically shuffle all outputs and label them EVAL-###.

    Seeded from the protocol's ``blind_seed``, so the assignment is fixed in
    advance and cannot be re-rolled after seeing results.
    """

    blinding = protocol.get("blinding", {})
    if blinding.get("shuffle_all_24_outputs") is not True:
        raise ProtocolViolation("blinding.shuffle_all_24_outputs must be true")

    ordered = sorted(plan.tasks, key=lambda task: (task.example_id, task.condition))
    shuffled = list(ordered)
    random.Random(int(blinding["blind_seed"])).shuffle(shuffled)

    width = str(blinding.get("label_format", "EVAL-###")).count("#") or 3
    return tuple(
        BlindAssignment(
            label=f"EVAL-{index:0{width}d}",
            example_id=task.example_id,
            condition=task.condition,
        )
        for index, task in enumerate(shuffled, start=1)
    )


def split_blinded_outputs(
    assignments: Sequence[BlindAssignment],
    texts: Mapping[tuple[str, str], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate what a scorer may see from what identifies a condition.

    Returns ``(blinded, mapping)``. The blinded records carry a label and the
    generated text and nothing else - no example id, no condition, no source.
    Keeping them in separate structures is what makes the blinding real rather
    than a promise not to look.
    """

    blinded: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    for assignment in assignments:
        key = (assignment.example_id, assignment.condition)
        if key not in texts:
            raise ProtocolViolation(f"missing generated text for {key}")
        blinded.append({"label": assignment.label, "output_text": texts[key]})
        mapping.append(
            {
                "label": assignment.label,
                "example_id": assignment.example_id,
                "condition": assignment.condition,
            }
        )
    return blinded, mapping


_LABEL_RE = re.compile(r"^EVAL-\d{3}$")


def assert_blinded_records_are_clean(
    blinded: Sequence[Mapping[str, Any]], assignments: Sequence[BlindAssignment]
) -> None:
    """Fail if a blinded record carries anything identifying beyond its label.

    This is a STRUCTURAL check. It does not inspect ``output_text``, because that
    is model-generated prose: rejecting it for containing the word "base" would
    fire on ordinary English - this corpus trains on the phrase "customer base" -
    and censoring a condition's output on the basis of its wording would bias the
    very comparison the blinding exists to protect.

    What is enforced instead: a record has exactly a label and a text, the label
    is a well-formed EVAL-### drawn from the assignment set, and no field encodes
    the example or condition.
    """

    allowed = {"label", "output_text"}
    known_labels = {assignment.label for assignment in assignments}
    example_ids = {assignment.example_id for assignment in assignments}
    seen: set[str] = set()

    for record in blinded:
        extra = sorted(set(record) - allowed)
        if extra:
            raise ProtocolViolation(f"blinded record carries extra fields: {extra}")
        missing = sorted(allowed - set(record))
        if missing:
            raise ProtocolViolation(f"blinded record is missing fields: {missing}")

        label = str(record["label"])
        if not _LABEL_RE.match(label):
            raise ProtocolViolation(f"blinded record has a malformed label: {label!r}")
        if known_labels and label not in known_labels:
            raise ProtocolViolation(f"blinded record uses an unassigned label: {label!r}")
        if label in seen:
            raise ProtocolViolation(f"duplicate blind label: {label!r}")
        seen.add(label)

        # The label is the only identifier a scorer sees, so it must not itself
        # encode the answer.
        if any(condition in label.lower() for condition in REQUIRED_CONDITIONS):
            raise ProtocolViolation(f"blind label names a condition: {label!r}")
        if any(example_id in label for example_id in example_ids):
            raise ProtocolViolation(f"blind label names an example: {label!r}")
