import json
from pathlib import Path

from authorship_shift.ablation import variant_registry
from authorship_shift.smoke import analyze_smoke_suite, write_smoke_report


VARIANTS = ["baseline", "planning_revision", "full"]
CALLS = {"baseline": 5, "planning_revision": 15, "full": 21}


def _config():
    return {
        "generation": {
            "plans": 2,
            "drafts_per_plan": 1,
            "beam_width": 2,
            "beam_rounds": 1,
            "operators_per_candidate": 1,
            "operators": ["claim_first", "mechanism_first"],
        },
        "gates": {"minimum_fidelity": 0.96, "minimum_quality_delta": 0.0, "diversity_weight": 0.25},
        "ablation": {"max_development_samples": 3, "default_variants": VARIANTS},
        "external_evaluation": {"development_queries_allowed": 0, "milestone_queries_budget": 0},
    }


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _build_suite(tmp_path: Path, *, full: bool = False) -> tuple[Path, Path]:
    suite = tmp_path / "suite"
    config_path = tmp_path / "smoke.json"
    _write_json(config_path, _config())

    registry = variant_registry()
    tasks = []
    samples = ["sample-a", "sample-b", "sample-c"]
    for sample in samples:
        for variant in VARIANTS:
            tasks.append({
                "sample_id": sample,
                "source_path": f"{sample}.txt",
                "variant": registry[variant].to_dict(),
            })
    _write_json(suite / "suite_plan.json", {
        "sample_count": 3,
        "variant_count": 3,
        "task_count": 9,
        "variants": [registry[name].to_dict() for name in VARIANTS],
        "tasks": tasks,
    })

    selected_tasks = tasks if full else tasks[:3]
    rows = []
    for task in selected_tasks:
        sample = task["sample_id"]
        variant = task["variant"]["name"]
        run_root = suite / "runs" / sample / variant
        run_root.mkdir(parents=True, exist_ok=True)
        calls = CALLS[variant]
        call_counts = {"all": calls}
        run_config = _config()
        run_config["ablation_variant"] = task["variant"]
        artifacts = {
            "manifest.json": {"external_queries_used": 0},
            "config.json": run_config,
            "content_lock.json": {"claims": []},
            "plans.json": {"plans": [{}]},
            "ranking.json": [{"fidelity": {"score": 1.0, "pass": True}, "quality": {"candidate_minus_source": 0.1, "pass": True}}],
            "selection.json": {"deterministic_beam_ids": ["x"]},
            "pipeline_stats.json": {"total_model_calls": calls, "call_counts": call_counts},
            "ablation_summary.json": {"variant": variant},
        }
        (run_root / "source.txt").write_text("source", encoding="utf-8")
        for name, value in artifacts.items():
            _write_json(run_root / name, value)
        rows.append({
            "sample_id": sample,
            "variant": variant,
            "source_path": task["source_path"],
            # Deliberately stale: diagnostics must recover from the canonical suite layout.
            "experiment_root": f"/old-machine/obsolete/{sample}/{variant}",
            "candidate_count": 1,
            "beam_size": 1,
            "models": ["fake:model"],
            "hard_gate_pass_rate": 1.0,
            "mean_fidelity": 1.0,
            "mean_quality_delta": 0.1,
            "total_model_calls": calls,
            "call_counts": call_counts,
            "external_queries_used": 0,
        })

    _write_json(suite / "suite_results.json", {
        "planned_runs": 9,
        "completed_runs": len(rows),
        "runs": rows,
    })
    return suite, config_path


def test_checkpoint_passes_and_recovers_from_stale_absolute_run_paths(tmp_path):
    suite, config = _build_suite(tmp_path)
    report = analyze_smoke_suite(suite, config, mode="checkpoint")
    assert report["ok"] is True
    assert report["target_expected_model_calls"] == 41
    assert report["target_measured_model_calls"] == 41
    assert report["errors"] == []

    md = write_smoke_report(suite, config, mode="checkpoint")
    assert md.exists()
    assert md.with_suffix(".json").exists()
    assert "Status: **PASS**" in md.read_text(encoding="utf-8")


def test_checkpoint_fails_on_detector_usage(tmp_path):
    suite, config = _build_suite(tmp_path)
    results_path = suite / "suite_results.json"
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    payload["runs"][0]["external_queries_used"] = 1
    _write_json(results_path, payload)

    report = analyze_smoke_suite(suite, config, mode="checkpoint")
    assert report["ok"] is False
    assert any("external detector query usage is nonzero" in error for error in report["errors"])


def test_checkpoint_fails_on_model_call_drift(tmp_path):
    suite, config = _build_suite(tmp_path)
    results_path = suite / "suite_results.json"
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    payload["runs"][2]["total_model_calls"] = 22
    payload["runs"][2]["call_counts"] = {"all": 22}
    _write_json(results_path, payload)

    run_stats = suite / "runs" / "sample-a" / "full" / "pipeline_stats.json"
    _write_json(run_stats, {"total_model_calls": 22, "call_counts": {"all": 22}})

    report = analyze_smoke_suite(suite, config, mode="checkpoint")
    assert report["ok"] is False
    assert any("model-call drift" in error for error in report["errors"])
    assert any("target batch call total drifted" in error for error in report["errors"])


def test_full_mode_rejects_checkpoint_only_results(tmp_path):
    suite, config = _build_suite(tmp_path)
    report = analyze_smoke_suite(suite, config, mode="full")
    assert report["ok"] is False
    assert any("full smoke suite requires exactly 9" in error for error in report["errors"])


def test_full_mode_accepts_complete_nine_run_suite(tmp_path):
    suite, config = _build_suite(tmp_path, full=True)
    report = analyze_smoke_suite(suite, config, mode="full")
    assert report["ok"] is True
    assert report["target_expected_model_calls"] == 123
    assert report["target_measured_model_calls"] == 123
