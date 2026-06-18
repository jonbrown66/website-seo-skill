from search_visibility_auditor.adapters.ai_readiness import AIReadinessAdapter


def test_ai_readiness_adapter_assesses_ai_visibility(monkeypatch):
    def fake_fetch(url, user_agent, timeout, max_bytes=2_000_000, retries=1):
        if url.endswith("/llms.txt"):
            return 200, url, "text/plain", "# Example\nUseful AI guidance"
        return 200, url, "text/html", '<html><head><title>Example</title><script type="application/ld+json">{"@context":"https://schema.org"}</script></head><body><h1>Example</h1><p>Enough public product content for AI readiness checks.</p></body></html>'

    monkeypatch.setattr("search_visibility_auditor.adapters.ai_readiness.fetch_url", fake_fetch)
    monkeypatch.setattr("search_visibility_auditor.adapters.ai_readiness.robots_allowed", lambda root, target, ua, timeout: (True, root + "/robots.txt"))

    result = AIReadinessAdapter().run({"url": "https://example.com", "timeout": 1, "user_agent": "test"})

    assert result.status == "ok"
    assert result.findings
    assert {finding.dimension for finding in result.findings} == {"ai_visibility"}
    assert any(finding.id == "AI-LLMS-001" and finding.status == "passed" for finding in result.findings)
