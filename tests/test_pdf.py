import pytest

from search_visibility_auditor.crawler import parse_page
from search_visibility_auditor.models import AdapterResult
from search_visibility_auditor.reporting import _write_pdf, build_enterprise_report, render_html_from_report
from search_visibility_auditor.rules import make_finding
from search_visibility_auditor.scoring import score_findings


def _weasyprint_works() -> bool:
    try:
        from weasyprint import HTML  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


@pytest.mark.skipif(not _weasyprint_works(), reason="weasyprint native libraries not available")
def test_pdf_generated_from_html_report(tmp_path):
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

    pdf_path = tmp_path / "audit.pdf"
    _write_pdf(pdf_path, html)

    assert pdf_path.exists()
    content = pdf_path.read_bytes()
    assert content.startswith(b"%PDF")
    assert len(content) > 500


def test_pdf_fallback_writes_notice(tmp_path, monkeypatch):
    import builtins
    original_import = builtins.__import__

    def block_weasyprint(name, *args, **kwargs):
        if name == "weasyprint":
            raise ImportError("No module named 'weasyprint'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", block_weasyprint)
    pdf_path = tmp_path / "audit.pdf"
    _write_pdf(pdf_path, "<html></html>")
    text = pdf_path.read_text(encoding="utf-8")
    assert "weasyprint" in text.lower() or "pip install" in text.lower()