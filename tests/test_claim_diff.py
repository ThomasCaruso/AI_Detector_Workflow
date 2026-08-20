from authorship_shift.claim_diff import claim_coverage_report


def test_claim_precheck_flags_missing_immutable():
    lock = {
        "claims": [
            {"id": "C1", "proposition": "Revenue increased by 20 percent", "importance": "required"},
            {"id": "C2", "proposition": "Costs stayed flat", "importance": "supporting"},
        ],
        "immutable_items": ["20 percent", {"value": "FY2025"}],
    }
    report = claim_coverage_report(lock, "Revenue increased by 20 percent during the period.")
    assert report.required_claims == 1
    assert "FY2025" in report.immutable_items_missing
