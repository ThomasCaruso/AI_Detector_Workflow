"""Verifying that a set of frozen protocol artifacts agree with each other.

Precommitting an experiment means writing several files - a training config, an
environment manifest, an evaluation protocol, a scoring protocol - each of which
names the data and code it applies to. The freeze is only worth something if
those files agree. A training config bound to one dataset digest and an
evaluation protocol bound to another describe two different experiments, and
nothing in either file reveals that on its own.

This module checks two properties across a set of artifacts:

* **binding consistency** - every artifact that declares a given binding key
  declares the same value for it, and every artifact declares the keys it is
  required to;
* **digest integrity** - the digest an artifact records for a file matches the
  bytes actually on disk.

Neither property is about what the protocol *says*. A protocol can be poorly
designed and still be internally consistent. What these checks buy is that a
result carrying these digests can be traced to exactly the inputs that produced
it, and that silent drift between artifacts is detectable rather than assumed
absent.

Root artifacts are the exception worth naming: an artifact cannot record its own
digest, and the first artifact written cannot record the digest of one written
after it. :func:`verify_binding_consistency` takes ``exempt`` for that reason
rather than pretending the cycle does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

PROTOCOL_FREEZE_SCHEMA_VERSION = 1


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    """Stable JSON bytes for hashing: sorted keys, explicit newline, UTF-8.

    Pinned so a digest does not depend on platform line endings or on the
    insertion order of a dict.
    """

    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


@dataclass(frozen=True)
class FrozenArtifact:
    """One precommitted file and the bindings it declares."""

    name: str
    path: str
    sha256: str
    bindings: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "bindings": dict(self.bindings),
        }


@dataclass(frozen=True)
class FreezeFinding:
    check: str
    detail: str
    fatal: bool = True


@dataclass(frozen=True)
class FreezeReport:
    findings: tuple[FreezeFinding, ...] = ()
    checks_run: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(finding.fatal for finding in self.findings)

    @property
    def fatal(self) -> tuple[FreezeFinding, ...]:
        return tuple(f for f in self.findings if f.fatal)


def verify_binding_consistency(
    artifacts: Sequence[FrozenArtifact],
    *,
    required_keys: Iterable[str],
    exempt: Mapping[str, Iterable[str]] | None = None,
) -> FreezeReport:
    """Check that artifacts agree on every binding key they share.

    ``exempt`` maps an artifact name to keys it is not required to declare -
    used for root artifacts that cannot reference a digest depending on them.
    An exempt artifact that declares the key anyway is still checked for
    agreement; exemption removes the obligation to declare, not the obligation
    to be correct.
    """

    required = list(required_keys)
    exemptions = {name: set(keys) for name, keys in (exempt or {}).items()}
    findings: list[FreezeFinding] = []

    seen: dict[str, dict[str, list[str]]] = {}
    for artifact in artifacts:
        for key, value in artifact.bindings.items():
            seen.setdefault(key, {}).setdefault(json.dumps(value, sort_keys=True), []).append(
                artifact.name
            )

    for key in required:
        for artifact in artifacts:
            if key in artifact.bindings:
                continue
            if key in exemptions.get(artifact.name, set()):
                continue
            findings.append(
                FreezeFinding(
                    "missing_required_binding",
                    f"{artifact.name} does not declare required binding {key!r}",
                )
            )

    for key, by_value in sorted(seen.items()):
        if len(by_value) > 1:
            rendered = "; ".join(
                f"{value} declared by {sorted(names)}" for value, names in sorted(by_value.items())
            )
            findings.append(
                FreezeFinding(
                    "binding_disagreement",
                    f"artifacts disagree on {key!r}: {rendered}",
                )
            )

    names = [artifact.name for artifact in artifacts]
    if len(names) != len(set(names)):
        findings.append(
            FreezeFinding("duplicate_artifact_name", f"artifact names repeat: {sorted(names)}")
        )

    return FreezeReport(
        findings=tuple(findings),
        checks_run=("missing_required_binding", "binding_disagreement", "duplicate_artifact_name"),
    )


def verify_recorded_digests(artifacts: Sequence[FrozenArtifact]) -> FreezeReport:
    """Check that each artifact's recorded digest matches the bytes on disk."""

    findings: list[FreezeFinding] = []
    for artifact in artifacts:
        try:
            actual = sha256_file(artifact.path)
        except OSError as exc:
            findings.append(
                FreezeFinding("artifact_unreadable", f"{artifact.name}: {exc}")
            )
            continue
        if actual != artifact.sha256:
            findings.append(
                FreezeFinding(
                    "digest_mismatch",
                    f"{artifact.name}: recorded {artifact.sha256[:12]}... "
                    f"but file hashes to {actual[:12]}...",
                )
            )
    return FreezeReport(
        findings=tuple(findings), checks_run=("artifact_unreadable", "digest_mismatch")
    )


def verify_freeze(
    artifacts: Sequence[FrozenArtifact],
    *,
    required_keys: Iterable[str],
    exempt: Mapping[str, Iterable[str]] | None = None,
) -> FreezeReport:
    """Run both checks and merge their findings."""

    consistency = verify_binding_consistency(
        artifacts, required_keys=required_keys, exempt=exempt
    )
    digests = verify_recorded_digests(artifacts)
    return FreezeReport(
        findings=consistency.findings + digests.findings,
        checks_run=consistency.checks_run + digests.checks_run,
    )
