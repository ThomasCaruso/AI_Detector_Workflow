import json
from pathlib import Path
import shutil

from authorship_shift.ablation import build_ablation_plan
from authorship_shift.compute import estimate_ablation_suite
from authorship_shift.corpus import build_manifest, validate_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_smoke_corpus_and_config_are_offline_ready(tmp_path):
    source_corpus = PROJECT_ROOT / "corpus"
    corpus = tmp_path / "corpus"
    shutil.copytree(source_corpus, corpus)

    manifest_path = build_manifest(corpus)
    validation = validate_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = json.loads((PROJECT_ROOT / "configs" / "smoke.json").read_text(encoding="utf-8"))

    assert validation["ok"] is True
    assert validation["errors"] == []
    assert manifest["sample_count"] == 3
    assert {entry["genre"] for entry in manifest["entries"]} == {"business", "science", "technology"}
    assert all(entry["word_count"] >= 250 for entry in manifest["entries"])

    variants = ",".join(config["ablation"]["default_variants"])
    plan = build_ablation_plan(
        corpus,
        variants=variants,
        max_samples=config["ablation"]["max_development_samples"],
    )
    estimate = estimate_ablation_suite(
        corpus,
        config,
        variants=variants,
        max_samples=config["ablation"]["max_development_samples"],
    )

    assert plan["sample_count"] == 3
    assert plan["variant_count"] == 3
    assert plan["task_count"] == 9
    assert [task["variant"]["name"] for task in plan["tasks"][:3]] == ["baseline", "planning_revision", "full"]
    assert len({task["sample_id"] for task in plan["tasks"][:3]}) == 1
    assert estimate["run_count"] == 9
    assert estimate["total_model_calls_upper_bound"] == 123
    assert config["external_evaluation"]["development_queries_allowed"] == 0
    assert config["external_evaluation"]["milestone_queries_budget"] == 0
