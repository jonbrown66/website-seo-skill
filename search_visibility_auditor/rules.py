from __future__ import annotations

from collections import Counter

from .crawler import validate_json_ld
from .models import Finding, PageSnapshot
from .utils import normalize_url

RULE_VERSION = "1.0.0"


def make_finding(
    rule_id: str,
    page: PageSnapshot,
    title: str,
    status: str,
    severity: str,
    evidence: dict,
    recommendation: str,
    impact: float,
    effort: float,
    reach: float,
    dimension: str = "seo_foundation",
    category: str = "technical_seo",
    confidence: float = 1.0,
    evidence_type: str = "verified",
) -> Finding:
    validation = {"method": f"Re-run rule {rule_id}", "expected_result": evidence.get("expected", "")}
    fix_prompt = (
        f"Fix finding {rule_id} for {page.final_url or page.url}. "
        f"Observed: {evidence.get('observed')}. Expected: {evidence.get('expected')}. "
        f"Implement: {recommendation}. Add validation matching: {validation['expected_result']}."
    )
    return Finding(
        id=rule_id,
        rule_version=RULE_VERSION,
        source="internal_crawler",
        category=category,
        dimension=dimension,
        title=title,
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,
        evidence_type=evidence_type,  # type: ignore[arg-type]
        affected_urls=[page.final_url or page.url],
        evidence=evidence,
        impact=impact,
        effort=effort,
        reach=reach,
        recommendation=recommendation,
        validation=validation,
        fix_prompt=fix_prompt,
    )


def evaluate_pages(pages: list[PageSnapshot], robots_meta: dict) -> list[Finding]:
    findings: list[Finding] = []
    total_pages = max(len(pages), 1)
    title_counts = Counter(page.title for page in pages if page.title)
    description_counts = Counter(page.meta_description for page in pages if page.meta_description)
    for page in pages:
        reach = 1 / total_pages
        expected_self = normalize_url(page.final_url or page.url)
        if page.status_code == 0 or page.status_code >= 500:
            findings.append(make_finding("SEO-STATUS-001", page, "Page is unavailable or returns 5xx", "failed", "critical", {"observed": page.status_code, "expected": "HTTP 200-399"}, "Restore the page or fix the server error.", 5, 2, reach))
        elif page.status_code >= 400:
            findings.append(make_finding("SEO-STATUS-002", page, "Page returns a client error", "failed", "high", {"observed": page.status_code, "expected": "HTTP 200-399"}, "Fix the URL, redirect it, or remove internal links to it.", 4, 2, reach))
        else:
            findings.append(make_finding("SEO-STATUS-OK", page, "Page returns a successful status", "passed", "informational", {"observed": page.status_code, "expected": "HTTP 200-399"}, "No action required.", 0, 1, reach))
        if page.noindex:
            findings.append(make_finding("SEO-INDEX-001", page, "Page has noindex directive", "failed", "critical", {"observed": "noindex", "expected": "indexable page unless intentionally excluded"}, "Remove noindex from pages that should receive organic traffic.", 5, 1, reach))
        if not page.title:
            findings.append(make_finding("SEO-TITLE-001", page, "Missing meta title", "failed", "high", {"observed": "", "expected": "Unique descriptive title"}, "Add a unique title matching page intent.", 4, 1, reach))
        elif len(page.title) > 65:
            findings.append(make_finding("SEO-TITLE-002", page, "Meta title is likely too long", "warning", "low", {"observed": page.title, "expected": "Concise title around 30-65 characters"}, "Shorten the title while preserving primary intent.", 2, 1, reach))
        if not page.meta_description:
            findings.append(make_finding("SEO-DESC-001", page, "Missing meta description", "failed", "medium", {"observed": "", "expected": "Unique page summary"}, "Add a unique description that sets expectations for searchers.", 3, 1, reach))
        if not page.canonical:
            findings.append(make_finding("SEO-CANONICAL-001", page, "Missing canonical URL", "warning", "medium", {"observed": "", "expected": expected_self}, "Add a self-referencing canonical URL.", 3, 1, reach))
        elif normalize_url(page.canonical) != expected_self:
            findings.append(make_finding("SEO-CANONICAL-002", page, "Canonical URL points to a different page", "failed", "high", {"observed": page.canonical, "expected": expected_self}, "Set canonical to the current page unless consolidation is intentional.", 4, 1, reach))
        if not page.headings.get("h1"):
            findings.append(make_finding("SEO-HEADING-001", page, "Missing H1 heading", "failed", "medium", {"observed": "", "expected": "One descriptive H1"}, "Add one descriptive H1 aligned with the page intent.", 3, 1, reach, dimension="content_answerability", category="on_page_seo"))
        elif len(page.headings.get("h1", [])) > 1:
            findings.append(make_finding("SEO-HEADING-002", page, "Multiple H1 headings", "warning", "low", {"observed": page.headings["h1"], "expected": "One primary H1"}, "Use one primary H1 and demote secondary headings.", 2, 1, reach, dimension="content_answerability", category="on_page_seo"))
        else:
            findings.append(make_finding("CONTENT-ANSWER-HEADING-OK", page, "Page has a clear primary H1", "passed", "informational", {"observed": page.headings["h1"][0], "expected": "One primary H1"}, "No action required.", 0, 1, reach, dimension="content_answerability", category="content_quality"))
        if page.word_count < 150:
            findings.append(make_finding("CONTENT-DEPTH-001", page, "Page has very little indexable text", "warning", "medium", {"observed": page.word_count, "expected": "Enough content to satisfy the page intent"}, "Expand the page with useful, specific content and direct answers.", 3, 2, reach, dimension="content_answerability", category="content_quality", confidence=0.85, evidence_type="inferred"))
        else:
            findings.append(make_finding("CONTENT-DEPTH-OK", page, "Page has enough indexable text for basic answerability", "passed", "informational", {"observed": page.word_count, "expected": "At least 150 indexable words"}, "No action required.", 0, 1, reach, dimension="content_answerability", category="content_quality"))
        if not page.schema_blocks:
            findings.append(make_finding("SEO-SCHEMA-001", page, "No structured data detected", "not_assessed", "informational", {"observed": "none", "expected": "Schema only when relevant"}, "Add JSON-LD only when it accurately represents visible page content.", 0, 2, reach))
        for block in page.schema_blocks:
            if not validate_json_ld(block):
                findings.append(make_finding("SEO-SCHEMA-002", page, "Invalid JSON-LD structured data", "failed", "high", {"observed": block[:300], "expected": "Valid JSON-LD"}, "Fix JSON-LD syntax and validate with a structured data validator.", 4, 2, reach))
        if page.images_missing_alt:
            findings.append(make_finding("SEO-IMAGE-ALT-001", page, "Images missing alt text", "warning", "low", {"observed": page.images_missing_alt[:10], "expected": "Informative images have meaningful alt text; decorative images use empty alt"}, "Add meaningful alt text where images convey content.", 2, 2, reach, dimension="content_answerability", category="accessibility"))
        if title_counts.get(page.title, 0) > 1:
            findings.append(make_finding("SEO-TITLE-003", page, "Duplicate meta title", "warning", "medium", {"observed": page.title, "expected": "Unique title per canonical page"}, "Make the title specific to this page.", 3, 1, reach))
        if page.meta_description and description_counts.get(page.meta_description, 0) > 1:
            findings.append(make_finding("SEO-DESC-002", page, "Duplicate meta description", "warning", "medium", {"observed": page.meta_description, "expected": "Unique description per canonical page"}, "Make the description specific to this page.", 3, 1, reach))
    if robots_meta.get("blocked"):
        synthetic = pages[0] if pages else _synthetic_page()
        findings.append(make_finding("SEO-ROBOTS-001", synthetic, "Robots.txt blocked crawled URLs", "failed", "critical", {"observed": robots_meta["blocked"], "expected": "Important pages crawlable"}, "Review robots rules and unblock pages intended for organic search.", 5, 1, len(robots_meta["blocked"]) / max(total_pages, 1)))
    return deduplicate_findings(findings)


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    merged: dict[tuple[str, tuple[str, ...]], Finding] = {}
    for finding in findings:
        key = (finding.id, tuple(sorted(finding.affected_urls)))
        if key not in merged or finding.confidence > merged[key].confidence:
            merged[key] = finding
    return list(merged.values())


_SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "informational": 1}
_STATUS_RANK = {"failed": 4, "error": 3, "warning": 2, "passed": 1, "not_assessed": 0}


def aggregate_by_rule(findings: list[Finding]) -> list[Finding]:
    """Roll up findings that share a rule id into one entry per rule.

    The report layer uses this so the same rule firing across many pages
    appears once with an affected-page count, instead of N duplicate cards.
    The rollup only touches display fields; scores/findings JSON still keep
    the fine-grained per-URL records for auditability.

    Passed/informational findings are kept verbatim (they never duplicate
    problem cards); only failed/warning/error findings are merged.
    """
    keep: list[Finding] = []
    buckets: dict[str, list[Finding]] = {}
    for finding in findings:
        is_problem = finding.status in {"failed", "warning", "error"}
        if not is_problem:
            keep.append(finding)
            continue
        buckets.setdefault(finding.id, []).append(finding)

    for rule_id, group in buckets.items():
        if len(group) == 1:
            keep.append(_with_rollup_metadata(group[0]))
            continue
        keep.append(_merge_group(rule_id, group))

    _rescore(keep)
    keep.sort(key=lambda f: f.priority_score, reverse=True)
    return keep


def _rescore(findings: list[Finding]) -> None:
    # Mirror scoring.add_priority_scores so rollups stay ordered correctly
    # after their reach/impact/severity are recomputed during merge.
    severity_weights = {"critical": 5, "high": 3, "medium": 2, "low": 1, "informational": 0.5}
    for finding in findings:
        effort = max(finding.effort, 0.1)
        finding.priority_score = round(
            severity_weights[finding.severity] * finding.impact * finding.confidence * finding.reach / effort, 4
        )


def _merge_group(rule_id: str, group: list[Finding]) -> Finding:
    worst = max(group, key=lambda f: (_SEVERITY_RANK.get(f.severity, 0), _STATUS_RANK.get(f.status, 0), f.priority_score))
    affected_urls: list[str] = []
    seen_urls: set[str] = set()
    for finding in group:
        for url in finding.affected_urls:
            if url and url not in seen_urls:
                seen_urls.add(url)
                affected_urls.append(url)
    sample_urls = affected_urls[:10]
    observed_values = [
        finding.evidence.get("observed")
        for finding in group
        if finding.evidence.get("observed") is not None
    ]
    representative = worst.evidence.get("observed")
    merged_evidence = {
        "observed": representative,
        "expected": worst.evidence.get("expected", ""),
        "page_count": len(affected_urls),
        "sample_urls": sample_urls,
        "distinct_observed": sorted({str(v) for v in observed_values})[:8],
    }
    rolled = _with_rollup_metadata(worst)
    rolled.affected_urls = affected_urls
    rolled.reach = min(1.0, sum(finding.reach for finding in group))
    rolled.evidence = merged_evidence
    rolled.title = worst.title
    return rolled


def _with_rollup_metadata(finding: Finding) -> Finding:
    clone = Finding(
        id=finding.id,
        rule_version=finding.rule_version,
        source=finding.source,
        category=finding.category,
        dimension=finding.dimension,
        title=finding.title,
        status=finding.status,
        severity=finding.severity,
        confidence=finding.confidence,
        evidence_type=finding.evidence_type,
        affected_urls=list(finding.affected_urls),
        evidence=dict(finding.evidence),
        impact=finding.impact,
        effort=finding.effort,
        reach=finding.reach,
        recommendation=finding.recommendation,
        implementation=dict(finding.implementation) if finding.implementation else {"framework": "", "files": [], "steps": []},
        validation=dict(finding.validation) if finding.validation else {},
        fix_prompt=finding.fix_prompt,
        detected_at=finding.detected_at,
        priority_score=finding.priority_score,
    )
    clone.evidence.setdefault("page_count", len(finding.affected_urls))
    return clone


def _synthetic_page() -> PageSnapshot:
    return PageSnapshot("", 0, "", "", "", "", "", "", {f"h{i}": [] for i in range(1, 7)}, [], [], [], [], 0, False)
