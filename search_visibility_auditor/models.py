from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Status = Literal["passed", "failed", "warning", "not_assessed", "error"]
EvidenceType = Literal["verified", "inferred", "unknown"]
Severity = Literal["critical", "high", "medium", "low", "informational"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Finding:
    id: str
    rule_version: str
    source: str
    category: str
    dimension: str
    title: str
    status: Status
    severity: Severity
    confidence: float
    evidence_type: EvidenceType
    affected_urls: list[str]
    evidence: dict[str, Any]
    impact: float
    effort: float
    reach: float
    recommendation: str
    implementation: dict[str, Any] = field(default_factory=lambda: {"framework": "", "files": [], "steps": []})
    validation: dict[str, Any] = field(default_factory=dict)
    fix_prompt: str = ""
    detected_at: str = field(default_factory=utc_now)
    priority_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdapterResult:
    adapter: str
    status: str
    reason: str = ""
    impact: str = ""
    findings: list[Finding] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return data


@dataclass
class PageSnapshot:
    url: str
    status_code: int
    final_url: str
    content_type: str
    html: str
    title: str
    meta_description: str
    canonical: str
    headings: dict[str, list[str]]
    links_internal: list[str]
    links_external: list[str]
    images_missing_alt: list[str]
    schema_blocks: list[str]
    word_count: int
    noindex: bool
    fetched_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

