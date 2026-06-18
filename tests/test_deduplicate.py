from search_visibility_auditor.crawler import parse_page
from search_visibility_auditor.rules import deduplicate_findings, make_finding


def test_deduplicate_keeps_one_rule_url_pair():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    first = make_finding("X-1", page, "Issue", "failed", "low", {"observed": "a", "expected": "b"}, "Fix it", 1, 1, 1)
    second = make_finding("X-1", page, "Issue", "failed", "low", {"observed": "a", "expected": "b"}, "Fix it", 1, 1, 1)
    assert len(deduplicate_findings([first, second])) == 1

