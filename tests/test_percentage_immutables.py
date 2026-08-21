from authorship_shift.candidate_lab import immutable_coverage, immutable_matches


def test_integer_percentage_accepts_percent_word_forms():
    assert immutable_matches("the score was 8 percent better", "8%")
    assert immutable_matches("the score was eight percent better", "8%")
    assert immutable_matches("the score was eight per cent better", "8%")


def test_percentage_equivalence_does_not_change_the_value():
    assert not immutable_matches("the score was 18 percent better", "8%")
    assert not immutable_matches("the score was eighty percent better", "8%")
    assert not immutable_matches("the score was 8.5 percent better", "8%")


def test_percentage_equivalence_does_not_conflate_percentage_points():
    assert not immutable_matches("the change was eight percentage points", "8%")
    assert not immutable_matches("the change was 8 percentage points", "8%")


def test_percentage_surface_change_preserves_immutable_coverage():
    source = "Participants had an average reaction-time score 8% better."
    candidate = "Participants had an average reaction-time score eight percent better."

    coverage, missing = immutable_coverage(source, candidate)
    assert coverage == 1.0
    assert missing == []
