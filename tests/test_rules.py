from search_visibility_auditor.crawler import parse_page
from search_visibility_auditor.rules import evaluate_pages


def test_rules_emit_evidence_for_failures():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><p>Thin</p>")
    findings = evaluate_pages([page], {"blocked": []})
    failed = [finding for finding in findings if finding.status in {"failed", "warning"}]
    assert failed
    assert all(finding.evidence for finding in failed)

