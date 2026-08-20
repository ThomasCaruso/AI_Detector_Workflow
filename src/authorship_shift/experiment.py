from __future__ import annotations

from pathlib import Path
import time
from .models import Candidate, ExternalResult, write_json, read_json
from .metrics import measure


class Experiment:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "candidates").mkdir(exist_ok=True)
        (self.root / "external").mkdir(exist_ok=True)
        (self.root / "outbox").mkdir(exist_ok=True)
        (self.root / "frozen").mkdir(exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def initialize(self, title: str, source_text: str, config: dict) -> None:
        if self.manifest_path.exists():
            raise FileExistsError(f"Experiment already exists: {self.root}")
        (self.root / "source.txt").write_text(source_text, encoding="utf-8")
        write_json(self.root / "config.json", config)
        write_json(self.manifest_path, {
            "title": title,
            "created_at": time.time(),
            "source_metrics": measure(source_text).to_dict(),
            "external_queries_used": 0,
            "candidate_ids": [],
            "frozen_candidate_ids": [],
        })

    def manifest(self) -> dict:
        return read_json(self.manifest_path)

    def add_candidate(self, candidate: Candidate) -> Path:
        path = self.root / "candidates" / f"{candidate.id}.json"
        write_json(path, candidate.to_dict())
        m = self.manifest()
        if candidate.id not in m["candidate_ids"]:
            m["candidate_ids"].append(candidate.id)
            write_json(self.manifest_path, m)
        return path

    def get_candidate(self, candidate_id: str) -> Candidate:
        path = self.root / "candidates" / f"{candidate_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown candidate: {candidate_id}")
        return Candidate.from_dict(read_json(path))

    def list_candidates(self) -> list[Candidate]:
        return [self.get_candidate(cid) for cid in self.manifest()["candidate_ids"]]

    def freeze_candidate(self, candidate_id: str, *, note: str = "") -> Path:
        candidate = self.get_candidate(candidate_id)
        if candidate.metadata.get("frozen_at"):
            return self.root / "frozen" / f"{candidate_id}.txt"
        candidate.metadata["frozen_at"] = time.time()
        candidate.metadata["freeze_note"] = note
        self.add_candidate(candidate)
        frozen_path = self.root / "frozen" / f"{candidate_id}.txt"
        frozen_path.write_text(candidate.text, encoding="utf-8")
        m = self.manifest()
        ids = m.setdefault("frozen_candidate_ids", [])
        if candidate_id not in ids:
            ids.append(candidate_id)
            write_json(self.manifest_path, m)
        return frozen_path

    def record_external(self, result: ExternalResult) -> Path:
        m = self.manifest()
        config = read_json(self.root / "config.json")
        external_cfg = config.get("external_evaluation", {})
        budget = int(external_cfg.get("milestone_queries_budget", 0))
        used = int(m.get("external_queries_used", 0))
        if budget and used >= budget:
            raise RuntimeError(f"External evaluation budget exhausted ({used}/{budget}).")

        require_frozen = bool(external_cfg.get("require_frozen_candidate", True))
        if result.candidate_id:
            candidate = self.get_candidate(result.candidate_id)
            frozen = bool(candidate.metadata.get("frozen_at"))
            if require_frozen and not frozen:
                raise RuntimeError(
                    f"Candidate {result.candidate_id} is not frozen. Run 'authorship-shift freeze' first."
                )
            result.frozen_before_test = frozen
        elif require_frozen:
            raise RuntimeError("A candidate ID is required for external evaluation when freeze enforcement is enabled.")

        stamp = int(time.time() * 1000)
        safe_detector = result.detector.replace(" ", "_").replace("/", "_")
        out = self.root / "external" / f"{stamp}_{safe_detector}.json"
        write_json(out, result.to_dict())
        m["external_queries_used"] = used + 1
        write_json(self.manifest_path, m)
        return out

    def status(self) -> dict:
        m = self.manifest()
        config = read_json(self.root / "config.json")
        return {
            "title": m.get("title"),
            "candidates": len(m.get("candidate_ids", [])),
            "frozen": len(m.get("frozen_candidate_ids", [])),
            "external_queries_used": int(m.get("external_queries_used", 0)),
            "external_queries_budget": int(config.get("external_evaluation", {}).get("milestone_queries_budget", 0)),
        }
