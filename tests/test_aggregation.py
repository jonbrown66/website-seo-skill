from search_visibility_auditor.crawler import parse_page
from search_visibility_auditor.models import AdapterResult
from search_visibility_auditor.reporting import build_enterprise_report
from search_visibility_auditor.rules import aggregate_by_rule, make_finding
from search_visibility_auditor.scoring import score_findings


def _canon_finding(url: str):
    page = parse_page(url, 200, url, "text/html", f"<title>{url}</title><h1>x</h1>")
    return make_finding(
        "SEO-CANONICAL-002",
        page,
        "Canonical URL points to a different page",
        "failed",
        "high",
        {"observed": "https://example.com/", "expected": url},
        "Set canonical to the current page.",
        4,
        1,
        1.0 / 3,
    )


def test_aggregate_by_rule_collapses_same_rule_across_urls():
    findings = [_canon_finding(u) for u in ("https://example.com/a", "https://example.com/b", "https://example.com/c")]
    score_findings(findings)
    rolled = aggregate_by_rule(findings)

    assert len(rolled) == 1
    assert rolled[0].id == "SEO-CANONICAL-002"
    assert len(rolled[0].affected_urls) == 3
    assert rolled[0].evidence["page_count"] == 3
    assert rolled[0].reach <= 1.0


def test_aggregate_keeps_distinct_rules_separate():
    findings = [_canon_finding("https://example.com/a")]
    page = parse_page("https://example.com/b", 200, "https://example.com/b", "text/html", "<title>b</title>")
    findings.append(make_finding("SEO-TITLE-001", page, "Missing title", "failed", "high", {"observed": "", "expected": "title"}, "Add title", 4, 1, 0.5))
    score_findings(findings)
    rolled = aggregate_by_rule(findings)
    ids = {f.id for f in rolled}
    assert ids == {"SEO-CANONICAL-002", "SEO-TITLE-001"}


def test_aggregate_takes_worst_severity():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>x</title>")
    medium = make_finding("X-1", page, "Issue", "warning", "medium", {"observed": "m", "expected": "g"}, "Fix", 3, 1, 0.5)
    critical = make_finding("X-1", page, "Issue", "failed", "critical", {"observed": "c", "expected": "g"}, "Fix", 5, 1, 0.5)
    score_findings([medium, critical])
    rolled = aggregate_by_rule([medium, critical])
    assert len(rolled) == 1
    assert rolled[0].severity == "critical"
    assert rolled[0].status == "failed"


def test_passed_findings_are_not_merged_into_problems():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>x</title>")
    passed = make_finding("SEO-STATUS-OK", page, "ok", "passed", "informational", {"observed": 200, "expected": 200}, "none", 0, 1, 1)
    failed = make_finding("SEO-STATUS-001", page, "down", "failed", "critical", {"observed": 500, "expected": 200}, "fix", 5, 1, 1)
    score_findings([passed, failed])
    rolled = aggregate_by_rule([passed, failed])
    ids = [f.id for f in rolled]
    assert "SEO-STATUS-OK" in ids
    assert "SEO-STATUS-001" in ids


def test_top_opportunities_do_not_repeat_same_rule():
    findings = [_canon_finding(u) for u in ("https://example.com/a", "https://example.com/b", "https://example.com/c")]
    score_findings(findings)
    audit = {
        "audit_id": "t",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, findings, score_findings(findings), [AdapterResult("internal_crawler", "ok")])

    top_ids = [item["id"] for item in report["top_opportunities"]]
    assert top_ids == ["SEO-CANONICAL-002"]
    assert report["top_opportunities"][0]["affected_count"] == 3
    assert len(report["executive_decision"]["top_fix_ids"]) == 1
    assert len(report["fix_roadmap"]["now"]) == 1
