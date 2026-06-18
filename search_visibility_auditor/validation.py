from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FINDING_FIELDS = {
    "id",
    "rule_version",
    "source",
    "category",
    "dimension",
    "title",
    "status",
    "severity",
    "confidence",
    "evidence_type",
    "affected_urls",
    "evidence",
    "recommendation",
    "validation",
    "detected_at",
}


def validate_audit_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for field in ["audit_id", "url", "mode", "scores", "findings"]:
        if field not in data:
            errors.append(f"missing field: {field}")
    for index, finding in enumerate(data.get("findings", [])):
        missing = REQUIRED_FINDING_FIELDS - set(finding)
        if missing:
            errors.append(f"finding[{index}] missing: {sorted(missing)}")
        if finding.get("status") in {"failed", "warning"} and not finding.get("evidence"):
            errors.append(f"finding[{index}] failed/warning without evidence")
    return {"valid": not errors, "errors": errors}

