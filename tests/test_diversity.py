from authorship_shift.diversity import lexical_jaccard, summarize_diversity


def test_diversity_identity():
    text = "One useful sentence. Another useful sentence."
    assert lexical_jaccard(text, text) == 1.0
    summary = summarize_diversity([text, text])
    assert summary.pair_count == 1
    assert summary.mean_pair_distance == 0.0
