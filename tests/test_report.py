import json

from search_visibility_auditor.crawler import parse_page
from search_visibility_auditor.models import AdapterResult
from search_visibility_auditor.reporting import build_enterprise_report, render_html_from_report, render_markdown_from_report, write_audit_outputs
from search_visibility_auditor.rules import make_finding
from search_visibility_auditor.scoring import score_findings


def test_report_outputs_json_markdown_html_and_escapes(tmp_path):
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("XSS", page, "<script>", "failed", "low", {"observed": "<b>", "expected": "safe"}, "Fix <tag>", 1, 1, 1)
    scores = score_findings([finding])
    audit = {"audit_id": "test", "url": "https://example.com", "mode": "quick", "generated_at": "now"}
    report_dir = write_audit_outputs("test", tmp_path, audit, [finding], scores, [AdapterResult("internal", "ok")])
    assert (report_dir / "audit.json").exists()
    assert (report_dir / "audit.md").exists()
    html = (report_dir / "audit.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html
    data = json.loads((report_dir / "audit.json").read_text(encoding="utf-8"))
    assert data["findings"][0]["evidence"]


def test_enterprise_report_suppresses_generic_score_for_low_coverage():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("SEO-CANONICAL-001", page, "Missing canonical URL", "warning", "medium", {"observed": "", "expected": "self canonical"}, "Add canonical", 3, 1, 1)
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }

    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("internal", "ok")])

    assert report["score_card"]["label"] == "readiness_matrix"
    assert report["score_card"]["score"] is None
    assert report["conclusion_eligibility"]["search_performance"]["status"] == "not_assessed"
    assert report["executive_decision"]["primary_action"]


def test_enterprise_html_renders_from_structured_json_and_escapes():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("XSS", page, "<script>", "failed", "low", {"observed": "<b>", "expected": "safe"}, "Fix <tag>", 1, 1, 1)
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("internal", "ok")])

    html = render_html_from_report(report)

    # New consulting-style report: sections, radar chart, severity tags, no empty appendix
    assert "Executive Summary" in html
    assert "Evidence Coverage" in html
    assert "Fix Roadmap" in html
    assert "Dimension Scores" in html
    assert "class=\"radar\"" in html  # SVG radar chart present
    assert "sev-tag" in html  # severity color tags present
    assert "grade-circle" in html  # cover grade circle present
    # XSS payload escaped
    assert "&lt;script&gt;" in html
    assert "Appendix" not in html
    assert '<script type="application/json" id="audit-data">' not in html
    assert "Priority Actions" in html
    assert "Fail" in html


def test_enterprise_html_surfaces_browser_evidence_status():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("SEO-CANONICAL-001", page, "Missing canonical URL", "warning", "medium", {"observed": "", "expected": "self canonical"}, "Add canonical", 3, 1, 1)
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "verified",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("internal", "ok")])
    report["browser_capture"] = {
        "can_capture_browser_evidence": True,
        "browser": "Chrome/120",
        "status_summary": [
            {"source": "gsc", "status": "ready", "detail": "Matched property"},
            {"source": "ga4", "status": "open", "detail": "Analytics tab detected"},
        ],
    }

    html = render_html_from_report(report)

    assert "Browser Evidence" in html
    assert "gsc" in html
    assert "Matched property" in html


def test_enterprise_markdown_is_reader_facing_and_structured():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("SEO-CANONICAL-001", page, "Missing canonical URL", "warning", "medium", {"observed": "", "expected": "self canonical"}, "Add canonical", 3, 1, 1)
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("internal", "ok")])
    report["browser_capture"] = {
        "stage_status": "browser_authorized_ready",
        "status_summary": [{"source": "gsc", "status": "ready", "detail": "Matched property"}],
    }

    markdown = render_markdown_from_report(report)

    assert "# Website SEO Audit Report" in markdown
    assert "## Audit Summary" in markdown
    assert "## Status Overview" in markdown
    assert "| Group | Items |" in markdown
    assert "## Browser Evidence" in markdown
    assert "SEO-CANONICAL-001" in markdown


def test_authorized_browser_adapter_unlocks_partial_performance_conclusions():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("BROWSER-GSC-001", page, "Search Console page was captured", "passed", "informational", {"observed": "captured", "expected": "visible evidence"}, "Export rows", 0, 1, 1, dimension="search_performance")
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "verified",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }

    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("authorized_browser", "ok")])

    assert report["conclusion_eligibility"]["search_performance"]["status"] == "eligible"
    assert report["conclusion_eligibility"]["organic_conversion"]["status"] == "eligible"


def test_ai_readiness_adapter_unlocks_ai_readiness_without_citation_provider():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("AI-LLMS-001", page, "llms.txt is available", "passed", "informational", {"observed": 200, "expected": "Readable /llms.txt"}, "Keep llms.txt current", 0, 1, 1, dimension="ai_visibility")
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "verified",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }

    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("ai_readiness", "ok"), AdapterResult("ai_citations", "unavailable", "credentials_missing", "AI citation visibility was not assessed")])

    assert report["conclusion_eligibility"]["ai_visibility"]["status"] == "eligible"
    assert "ai_citations" not in [item["source"] for item in report["blocked_or_not_assessed"]]


def test_html_radar_chart_renders_with_dimension_data():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("SEO-CANONICAL-001", page, "Missing canonical", "warning", "medium", {"observed": "", "expected": "c"}, "Fix", 3, 1, 1)
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("internal_crawler", "ok")])
    html = render_html_from_report(report)
    assert 'class="radar"' in html
    assert '<svg' in html
    assert 'polygon' in html


def test_aeo_geo_section_renders_when_findings_present():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    aeo = make_finding("AEO-FAQ-001", page, "FAQ structure detected", "passed", "informational", {"observed": "faq", "expected": "faq"}, "Keep", 0, 1, 1, dimension="content_answerability", category="aeo")
    geo = make_finding("GEO-ENTITY-ORG", page, "Organization entity is well-defined", "passed", "informational", {"observed": "org", "expected": "org"}, "Keep", 0, 1, 1, dimension="ai_visibility", category="geo")
    scores = score_findings([aeo, geo])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, [aeo, geo], scores, [AdapterResult("aeo_geo", "ok")])
    html = render_html_from_report(report)
    assert "AEO / GEO" in html
    assert "AEO Answerability" in html
    assert "GEO Entity" in html
    assert "AEO-FAQ-001" in html
    assert "GEO-ENTITY-ORG" in html


def test_cover_grade_circle_renders():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("SEO-CANONICAL-001", page, "Missing canonical", "warning", "medium", {"observed": "", "expected": "c"}, "Fix", 3, 1, 1)
    scores = score_findings([finding])
    audit = {
        "audit_id": "test",
        "url": "https://example.com",
        "mode": "quick",
        "generated_at": "now",
        "report_type": "Public Quick Scan",
        "target": {"selected": "https://example.com", "status": "confirmed", "confidence": "high", "candidates": []},
    }
    report = build_enterprise_report(audit, [finding], scores, [AdapterResult("internal_crawler", "ok")])
    html = render_html_from_report(report)
    assert "grade-circle" in html
