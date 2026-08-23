from authorship_shift.correction_application import (
    apply_reviewed_corrections_order_invariant,
)
from authorship_shift.text_derivation import (
    PageText,
    apply_reviewed_corrections,
    corrections_sha256,
    pages_sha256,
)


def _payload(pages, replacements):
    return {
        "schema_version": 1,
        "artifact_sha256": "a" * 64,
        "base_text_sha256": pages_sha256(pages),
        "replacements": replacements,
    }


def test_overlapping_substring_rules_fail_preflight():
    pages = [PageText(1, "T ransportation and T ransport,")]
    payload = _payload(
        pages,
        [
            {
                "page": 1,
                "old": "T ransport",
                "new": "Transport",
                "expected_count": 2,
            },
            {
                "page": 1,
                "old": "T ransportation",
                "new": "Transportation",
                "expected_count": 1,
            },
        ],
    )
    try:
        apply_reviewed_corrections_order_invariant(
            pages,
            payload,
            artifact_sha256="a" * 64,
        )
    except ValueError as exc:
        assert "overlapping source text" in str(exc)
    else:
        raise AssertionError("substring-overlapping correction rules must fail")


def test_anchored_short_rule_avoids_overlap():
    pages = [PageText(1, "T ransportation and T ransport,")]
    payload = _payload(
        pages,
        [
            {
                "page": 1,
                "old": "T ransport,",
                "new": "Transport,",
                "expected_count": 1,
            },
            {
                "page": 1,
                "old": "T ransportation",
                "new": "Transportation",
                "expected_count": 1,
            },
        ],
    )
    corrected, _ = apply_reviewed_corrections_order_invariant(
        pages,
        payload,
        artifact_sha256="a" * 64,
    )
    assert corrected[0].text == "Transportation and Transport,"


def test_application_is_order_invariant_when_new_text_matches_another_old_rule():
    pages = [PageText(1, "foo then bar")]
    replacements = [
        {"page": 1, "old": "foo", "new": "bar", "expected_count": 1},
        {"page": 1, "old": "bar", "new": "baz", "expected_count": 1},
    ]
    first, _ = apply_reviewed_corrections_order_invariant(
        pages,
        _payload(pages, replacements),
        artifact_sha256="a" * 64,
    )
    second, _ = apply_reviewed_corrections_order_invariant(
        pages,
        _payload(pages, list(reversed(replacements))),
        artifact_sha256="a" * 64,
    )
    assert first == second
    assert first[0].text == "bar then baz"


def test_public_apply_reviewed_corrections_uses_order_invariant_semantics():
    pages = [PageText(1, "foo then bar")]
    replacements = [
        {"page": 1, "old": "foo", "new": "bar", "expected_count": 1},
        {"page": 1, "old": "bar", "new": "baz", "expected_count": 1},
    ]
    first, _ = apply_reviewed_corrections(
        pages,
        _payload(pages, replacements),
        artifact_sha256="a" * 64,
    )
    second, _ = apply_reviewed_corrections(
        pages,
        _payload(pages, list(reversed(replacements))),
        artifact_sha256="a" * 64,
    )
    assert first == second
    assert first[0].text == "bar then baz"


def test_corrections_hash_is_invariant_to_replacement_order():
    pages = [PageText(1, "foo then bar")]
    replacements = [
        {"page": 1, "old": "foo", "new": "bar", "expected_count": 1, "reason": "repair one"},
        {"page": 1, "old": "bar", "new": "baz", "expected_count": 1, "reason": "repair two"},
    ]
    forward = _payload(pages, replacements)
    reversed_payload = _payload(pages, list(reversed(replacements)))
    assert corrections_sha256(forward) == corrections_sha256(reversed_payload)
