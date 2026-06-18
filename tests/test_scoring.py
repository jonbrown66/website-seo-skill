from search_visibility_auditor.crawler import parse_page
from search_visibility_auditor.rules import make_finding
from search_visibility_auditor.scoring import add_priority_scores, score_findings


def test_missing_data_does_not_zero_score():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    passed = make_finding("OK", page, "OK", "passed", "informational", {"observed": 200, "expected": 200}, "None", 0, 1, 1)
    unknown = make_finding("NA", page, "Not assessed", "not_assessed", "informational", {"observed": "missing", "expected": "api"}, "Connect API", 0, 1, 1, dimension="search_performance", evidence_type="unknown")
    scores = score_findings([passed, unknown])
    assert scores["overall_score"] == 100
    assert scores["data_coverage"] < 100


def test_priority_formula_assigns_higher_score_to_critical():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    finding = make_finding("CRIT", page, "Critical", "failed", "critical", {"observed": "x", "expected": "y"}, "Fix", 5, 1, 1)
    add_priority_scores([finding])
    assert finding.priority_score == 25


def test_same_rule_across_many_pages_does_not_zero_dimension():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    # 50 pages each missing a description (SEO-DESC-001, medium, impact 3)
    findings = [
        make_finding("SEO-DESC-001", page, "Missing meta description", "failed", "medium", {"observed": "", "expected": "desc"}, "Add description", 3, 1, 1 / 50)
        for _ in range(50)
    ]
    scores = score_findings(findings)
    # Before rule aggregation this summed 50 penalties -> 0. Now it counts once.
    assert scores["dimensions"]["seo_foundation"]["score"] > 80
    assert scores["rubric_version"] == "2.0.0"
    assert scores["scoring_method"] == "rule_aggregated"


def test_distinct_rules_still_compound():
    page = parse_page("https://example.com", 200, "https://example.com", "text/html", "<title>A</title><h1>A</h1>")
    findings = [
        make_finding("SEO-DESC-001", page, "Missing desc", "failed", "medium", {"observed": "", "expected": "d"}, "Fix", 3, 1, 1),
        make_finding("SEO-TITLE-001", page, "Missing title", "failed", "high", {"observed": "", "expected": "t"}, "Fix", 4, 1, 1),
        make_finding("SEO-CANONICAL-001", page, "Missing canonical", "failed", "medium", {"observed": "", "expected": "c"}, "Fix", 3, 1, 1),
    ]
    scores = score_findings(findings)
    # Three distinct rules each deduct once; score should be well below 100 but above 0.
    score = scores["dimensions"]["seo_foundation"]["score"]
    assert 0 < score < 100

