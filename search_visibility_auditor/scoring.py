from __future__ import annotations

from collections import defaultdict

from .models import Finding

DIMENSION_WEIGHTS = {
    "seo_foundation": 25,
    "content_answerability": 20,
    "authority_entity": 15,
    "search_performance": 15,
    "ai_visibility": 15,
    "ux_business_outcome": 10,
}
SEVERITY_WEIGHTS = {"critical": 5, "high": 3, "medium": 2, "low": 1, "informational": 0.5}
RUBRIC_VERSION = "2.0.0"


def add_priority_scores(findings: list[Finding]) -> list[Finding]:
    for finding in findings:
        severity_weight = SEVERITY_WEIGHTS[finding.severity]
        effort = max(finding.effort, 0.1)
        finding.priority_score = round(severity_weight * finding.impact * finding.confidence * finding.reach / effort, 4)
    return findings


def score_findings(findings: list[Finding]) -> dict:
    add_priority_scores(findings)
    dimension_findings: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        dimension_findings[finding.dimension].append(finding)

    scores: dict[str, dict] = {}
    assessed_weight_total = 0.0
    weighted_score_total = 0.0
    assessed_dimensions = 0
    for dimension, weight in DIMENSION_WEIGHTS.items():
        items = dimension_findings.get(dimension, [])
        assessed = [item for item in items if item.status in {"passed", "failed", "warning", "error"}]
        unknown = [item for item in items if item.status == "not_assessed"]
        if not assessed:
            scores[dimension] = {"score": None, "weight": weight, "assessed": False, "findings": len(items), "unknown": len(unknown)}
            continue
        assessed_dimensions += 1
        assessed_weight_total += weight
        # Score penalties by rule, not by page: the same rule firing across many
        # pages counts once (taking the worst severity), so a multi-page site is
        # not unfairly driven to zero. Coverage still reflects every finding.
        problem_findings = [item for item in assessed if item.status in {"failed", "warning", "error"}]
        penalty = sum(_penalty(rule_worst) for rule_worst in _worst_per_rule(problem_findings))
        penalty = min(penalty, 100)
        dimension_score = max(0, round(100 - penalty, 2))
        weighted_score_total += dimension_score * weight
        scores[dimension] = {"score": dimension_score, "weight": weight, "assessed": True, "findings": len(items), "unknown": len(unknown)}

    overall = round(weighted_score_total / assessed_weight_total, 2) if assessed_weight_total else None
    total = max(len(findings), 1)
    verified = sum(1 for finding in findings if finding.evidence_type == "verified")
    inferred = sum(1 for finding in findings if finding.evidence_type == "inferred")
    unknown = sum(1 for finding in findings if finding.evidence_type == "unknown" or finding.status == "not_assessed")
    data_coverage = round((assessed_weight_total / sum(DIMENSION_WEIGHTS.values())) * 100, 2)
    confidence = "high" if data_coverage >= 80 and verified / total >= 0.7 else "medium" if data_coverage >= 45 else "low"
    return {
        "overall_score": overall,
        "data_coverage": data_coverage,
        "confidence": confidence,
        "verified_evidence_ratio": round(verified / total, 2),
        "inferred_evidence_ratio": round(inferred / total, 2),
        "unknown_ratio": round(unknown / total, 2),
        "rubric_version": RUBRIC_VERSION,
        "scoring_method": "rule_aggregated",
        "dimensions": scores,
    }


def _worst_per_rule(findings: list[Finding]) -> list[Finding]:
    """Collapse findings sharing a rule id into the single most severe one.

    Keeps distinct rules separate so unrelated deductions are still summed,
    but stops the same rule from compounding across pages.
    """
    buckets: dict[str, Finding] = {}
    for finding in findings:
        current = buckets.get(finding.id)
        if current is None or _severity_rank(finding) > _severity_rank(current) or (
            _severity_rank(finding) == _severity_rank(current) and finding.priority_score > current.priority_score
        ):
            buckets[finding.id] = finding
    return list(buckets.values())


def _severity_rank(finding: Finding) -> int:
    rank = {"critical": 5, "high": 4, "medium": 3, "low": 2, "informational": 1}
    status_rank = {"failed": 4, "error": 3, "warning": 2, "passed": 1, "not_assessed": 0}
    return rank.get(finding.severity, 0) * 10 + status_rank.get(finding.status, 0)


def _penalty(finding: Finding) -> float:
    if finding.status == "warning":
        multiplier = 0.6
    elif finding.status == "error":
        multiplier = 0.4
    else:
        multiplier = 1.0
    return SEVERITY_WEIGHTS[finding.severity] * finding.impact * finding.confidence * max(finding.reach, 0.05) * multiplier

