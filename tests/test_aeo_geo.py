from search_visibility_auditor.adapters.aeo_geo import AEOGeoAdapter

FAQ_HTML = """<html><head>
<title>Remote Work Tools Guide</title>
<meta name="description" content="A guide to remote work tools.">
<meta property="og:title" content="Remote Work Tools Guide">
<meta property="og:description" content="A guide to remote work tools.">
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"Organization","name":"Acme","url":"https://acme.com","logo":"https://acme.com/logo.png","sameAs":["https://twitter.com/acme"]},
  {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"What is a remote work tool?","acceptedAnswer":{"@type":"Answer","text":"A remote work tool is software that helps teams collaborate across locations."}}]},
  {"@type":"Article","author":{"@type":"Person","name":"Jane Doe"},"datePublished":"2026-01-01","dateModified":"2026-06-01"}
]}
</script>
</head><body>
<h1>Remote Work Tools Guide</h1>
<h2>What is a remote work tool?</h2>
<p>A remote work tool is software that helps distributed teams communicate and collaborate across different locations and time zones effectively.</p>
<p>Choosing the right remote work tools requires understanding your team workflows, communication preferences, security needs, and budget constraints before committing to a platform that will shape daily collaboration.</p>
<p>Remote work has transformed how modern organizations operate, enabling employees to contribute from anywhere while maintaining productivity and team cohesion across multiple time zones and geographic boundaries.</p>
<p>Many companies now adopt hybrid models that combine in-office presence with flexible remote arrangements to attract top talent and reduce overhead costs associated with maintaining large physical office spaces in expensive metropolitan areas.</p>
<h2>Why does this matter?</h2>
<table><tr><th>Tool</th><td>Use</td></tr></table>
<ol><li>First</li><li>Second</li></ol>
</body></html>"""

SPARSE_HTML = """<html><head><title>Page</title></head>
<body><h1>Page</h1><p>Short.</p></body></html>"""


def _patch(monkeypatch, html):
    def fake_fetch(url, user_agent, timeout, max_bytes=2_000_000, retries=0):
        return 200, url, "text/html", html
    monkeypatch.setattr("search_visibility_auditor.adapters.aeo_geo.fetch_url", fake_fetch)


def test_aeo_geo_detects_answerable_signals(monkeypatch):
    _patch(monkeypatch, FAQ_HTML)
    result = AEOGeoAdapter().run({"url": "https://example.com", "timeout": 1, "user_agent": "test"})

    assert result.status == "ok"
    by_id = {f.id: f for f in result.findings}
    assert by_id["AEO-FAQ-001"].status == "passed"
    assert by_id["AEO-STRUCTURE-001"].status == "passed"
    assert by_id["AEO-PASSAGE-001"].status == "warning"  # no 40-60 word paragraphs
    assert by_id["AEO-SCHEMA-001"].status == "passed"


def test_aeo_geo_reports_geo_entity_strengths(monkeypatch):
    _patch(monkeypatch, FAQ_HTML)
    result = AEOGeoAdapter().run({"url": "https://example.com", "timeout": 1, "user_agent": "test"})
    by_id = {f.id: f for f in result.findings}

    assert by_id["GEO-ENTITY-ORG"].status == "passed"
    assert by_id["GEO-ENTITY-AUTHOR"].status == "passed"
    assert by_id["GEO-DATE"].status == "passed"
    assert by_id["GEO-OG-CONSISTENT"].status == "passed"


def test_aeo_geo_flags_sparse_page(monkeypatch):
    _patch(monkeypatch, SPARSE_HTML)
    result = AEOGeoAdapter().run({"url": "https://example.com", "timeout": 1, "user_agent": "test"})
    by_id = {f.id: f for f in result.findings}

    assert by_id["AEO-FAQ-001"].status == "warning"
    assert by_id["GEO-ENTITY-ORG"].status == "warning"
    assert by_id["GEO-OG-CONSISTENT"].status == "warning"


def test_aeo_geo_findings_split_across_dimensions(monkeypatch):
    _patch(monkeypatch, FAQ_HTML)
    result = AEOGeoAdapter().run({"url": "https://example.com", "timeout": 1, "user_agent": "test"})
    dims = {f.dimension for f in result.findings}
    assert dims == {"content_answerability", "ai_visibility"}
    # All findings must be verified (no API key, pure parse)
    assert all(f.evidence_type == "verified" for f in result.findings)
