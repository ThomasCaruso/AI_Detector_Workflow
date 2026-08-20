from __future__ import annotations

from pathlib import Path
import time

from .models import Candidate, ExternalResult, write_json, read_json
from .metrics import measure
from .provenance import canonical_json_sha256, sha256_file, sha256_text


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
            "source_sha256": sha256_text(source_text),
            "config_sha256": canonical_json_sha256(config),
            "external_queries_used": 0,
            "candidate_ids": [],
            "frozen_candidate_ids": [],
        })

    def manifest(self) -> dict:
        return read_json(self.manifest_path)

    def add_candidate(self, candidate: Candidate) -> Path:
        candidate.metadata["content_sha256"] = sha256_text(candidate.text)
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
        frozen_path = self.root / "frozen" / f"{candidate_id}.txt"
        expected_hash = sha256_text(candidate.text)
        if candidate.metadata.get("frozen_at"):
            if not frozen_path.exists():
                raise RuntimeError(f"Frozen candidate metadata exists but frozen file is missing: {candidate_id}")
            if sha256_file(frozen_path) != expected_hash:
                raise RuntimeError(f"Frozen candidate file does not match candidate content: {candidate_id}")
            return frozen_path
        candidate.metadata["frozen_at"] = time.time()
        candidate.metadata["freeze_note"] = note
        candidate.metadata["frozen_sha256"] = expected_hash
        self.add_candidate(candidate)
        frozen_path.write_text(candidate.text, encoding="utf-8")
        if sha256_file(frozen_path) != expected_hash:
            raise RuntimeError(f"Frozen candidate hash verification failed: {candidate_id}")
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
            expected_hash = sha256_text(candidate.text)
            if frozen:
                frozen_path = self.root / "frozen" / f"{result.candidate_id}.txt"
                if not frozen_path.exists():
                    raise RuntimeError(f"Frozen file is missing for candidate {result.candidate_id}.")
                if sha256_file(frozen_path) != expected_hash:
                    raise RuntimeError(f"Frozen file hash mismatch for candidate {result.candidate_id}.")
                recorded_hash = candidate.metadata.get("frozen_sha256")
                if recorded_hash and recorded_hash != expected_hash:
                    raise RuntimeError(f"Frozen metadata hash mismatch for candidate {result.candidate_id}.")
            result.frozen_before_test = frozen
            result.candidate_sha256 = expected_hash
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
            "source_sha256": m.get("source_sha256"),
            "config_sha256": m.get("config_sha256"),
        }
