"""Inspector-owned policy and evidence contract; no target code is executed."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

from .result import Evidence, Finding

PRODUCT = "production-readiness-inspector"
VERSION = "0.3.0"
RULESET = "2026.10.18.1"
PROFILE = "python-fastapi-container-v1"
BASELINE_FORMAT = "inspector-instances-v1"

# Versions change when applicability, evidence, severity or identity semantics change.
RULES = {
    "PR-PY-001": ("2", "high", "Development mode is explicitly enabled", "Disable literal debug/reload settings in the production configuration."),
    "PR-FASTAPI-001": ("2", "medium", "No direct conventional GET health route was found", "Review /health, /healthz, /ready or /readyz routing and test readiness behavior in the deployed application."),
    "PR-FASTAPI-002": ("1", "high", "Health route declares an unsuccessful status code", "Use a successful status for a healthy probe and test failure semantics separately."),
    "PR-DOCKER-001": ("2", "medium", "External base image is mutable", "Consider a reviewed sha256 digest and an explicit update process; tags can change."),
    "PR-DOCKER-002": ("2", "medium", "Final stage explicitly selects a root runtime user", "Select a non-root runtime user where the application permits it."),
    "PR-DOCKER-003": ("1", "medium", "Final startup uses shell form without exec", "Review signal forwarding; use JSON exec form or a signal-forwarding entrypoint."),
    "PR-DOCKER-004": ("1", "high", "Final startup enables Uvicorn reload", "Remove --reload from the production startup command."),
    "PR-CI-001": ("2", "high", "External action is not pinned to an immutable reference", "Pin remote actions and reusable workflows to a full commit SHA; pin docker actions to a digest."),
    "PR-CI-002": ("2", "high", "Workflow declares write-all token permissions", "Declare the minimum required workflow/job permissions."),
    "PR-SECRET-001": ("2", "high", "An environment file is present in the analysis input", "Review whether this file contains secrets and is tracked or copied into builds. Its contents were not read."),
}


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def public_path(path: str) -> str:
    """Paths are evidence, but control characters and credential-like names are not."""
    path = re.sub(r"[\x00-\x1f\x7f]", "?", path)
    return re.sub(r"(?:[sr]k_(?:live|test)_|whsec_)[A-Za-z0-9]+|AKIA[0-9A-Z]{16}", "[redacted]", path)


@dataclass(frozen=True, slots=True)
class Limits:
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 16_000_000
    max_files: int = 2_000
    max_entries: int = 20_000
    max_seconds: int = 10
    max_findings: int = 2_000

    def __post_init__(self):
        ceilings = (2_000_000, 32_000_000, 5_000, 50_000, 30, 5_000)
        for (name, value), ceiling in zip(asdict(self).items(), ceilings, strict=True):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError(f"invalid {name}")


@dataclass
class Analysis:
    findings: list[Finding] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    coverage: dict[str, str] = field(default_factory=lambda: {
        "repository": "analyzed", "python": "not_detected", "fastapi": "not_detected",
        "docker": "not_detected", "github_actions": "not_detected",
        "compose": "not_supported", "kubernetes": "not_supported",
        "dependencies": "not_supported", "runtime_behavior": "not_analyzed",
        "secret_values": "not_analyzed",
    })
    rule_states: dict[str, str] = field(default_factory=lambda: {rule: "not_applicable" for rule in RULES})
    occurrences: dict[str, int] = field(default_factory=dict)
    file_states: list[dict] = field(default_factory=list)
    max_findings: int = 2_000

    def issue(self, code: str, path: str = "", line: int = 1):
        if len(self.issues) < 100:
            self.issues.append({"code": code, "path": public_path(path), "line": line})

    def note(self, code: str, path: str, line: int = 1):
        if len(self.notes) < 100:
            self.notes.append({"code": code, "path": public_path(path), "line": line})

    def emit(self, rule: str, path: str, line: int, fact: str, anchor: object, *, inference: bool = False):
        if len(self.findings) >= self.max_findings:
            self.issue("finding_limit")
            return
        version, severity, title, remediation = RULES[rule]
        identity = digest([rule, version, path, anchor])
        ordinal = self.occurrences.get(identity, 0)
        self.occurrences[identity] = ordinal + 1
        self.findings.append(Finding(
            id=rule, title=title, severity=severity, confidence=1.0,
            evidence=[Evidence("repository", f"{public_path(path)}:{line}", fact)],
            remediation=remediation,
            metadata={"rule_version": version, "instance_id": digest([identity, ordinal]),
                      "evidence_kind": "inference" if inference else "syntax",
                      "path": public_path(path), "line": line,
                      "confidence_meaning": "deterministic evidence extraction; not a probability of production failure"},
        ))
        self.rule_states[rule] = "inferred" if inference else "evaluated"
