"""Inspector-owned typed result, compatible with the suite's JSON envelope."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class Evidence:
    source: str
    locator: str
    fact: str
    excerpt: str | None = None


@dataclass(slots=True)
class Finding:
    id: str
    title: str
    severity: str = "info"
    origin: str = "deterministic"
    confidence: float = 1.0
    evidence: list[Evidence] = field(default_factory=list)
    remediation: str | None = None
    status: str = "open"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProductResult:
    product: str
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    coverage: dict[str, str] = field(default_factory=dict)
    input_fingerprint: str | None = None
    schema_version: str = "1.0"
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def blocking(self) -> bool:
        return self.verdict in {"blocked", "error", "incomplete", "unsupported"}
