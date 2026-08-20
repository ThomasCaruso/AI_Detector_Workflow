from authorship_shift.metrics import measure, structural_distance


def test_measure_basic():
    text = "Short sentence. This is a somewhat longer sentence with more words.\n\nAnother paragraph is here."
    m = measure(text)
    assert m.word_count > 10
    assert m.sentence_count == 3
    assert m.paragraph_count == 2
    assert m.sentence_length_cv >= 0


def test_distance_identity_zeroish():
    text = "One sentence. Another sentence."
    assert structural_distance(text, text) == 0.0
