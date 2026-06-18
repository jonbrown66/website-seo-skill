from search_visibility_auditor.browser_cdp import (
    BrowserAttachResult,
    browser_evidence_status,
    browser_evidence_findings,
    build_chrome_attach_command,
    launch_urls,
    plan_zero_config_capture,
    profile_health,
)


def test_build_chrome_attach_command_uses_fixed_profile():
    command = build_chrome_attach_command("E:\\browser-profiles\\website-seo-audit", 9222)

    assert "--remote-debugging-port=9222" in command
    assert '--user-data-dir="E:\\browser-profiles\\website-seo-audit"' in command


def test_launch_urls_include_target_and_evidence_destinations():
    urls = launch_urls("https://example.com")

    assert "https://example.com" in urls
    assert "https://search.google.com/search-console" in urls
    assert "https://analytics.google.com/analytics/web/" in urls
    assert "https://www.bing.com/webmasters/" in urls


def test_zero_config_plan_defaults_to_launch_once_when_cdp_missing():
    result = BrowserAttachResult(available=False, cdp_url="http://127.0.0.1:9222", browser="", tabs=[], error="connection refused")

    plan = plan_zero_config_capture(result, "https://example.com", browser_mode="launch-once", launched=True)

    assert plan["browser_mode"] == "launch-once"
    assert plan["can_capture_browser_evidence"] is False
    assert plan["will_launch_browser"] is True
    assert plan["browser_launch"]["attempted"] is True


def test_zero_config_plan_reuses_existing_tabs_when_cdp_available():
    result = BrowserAttachResult(
        available=True,
        cdp_url="http://127.0.0.1:9222",
        browser="Chrome/120",
        tabs=[{"url": "https://search.google.com/search-console", "title": "Search Console"}],
        error="",
    )

    plan = plan_zero_config_capture(result, "https://example.com", browser_mode="launch-once", launched=False)

    assert plan["can_capture_browser_evidence"] is True
    assert plan["will_launch_browser"] is False
    assert plan["tabs"][0]["url"] == "https://search.google.com/search-console"


def test_zero_config_plan_can_be_attach_only():
    result = BrowserAttachResult(available=False, cdp_url="http://127.0.0.1:9222", browser="", tabs=[], error="connection refused")

    plan = plan_zero_config_capture(result, "https://example.com", browser_mode="attach", launched=False)

    assert plan["browser_mode"] == "attach"
    assert plan["will_launch_browser"] is False
    assert "chrome" in plan["required_user_action"].lower()


def test_profile_health_reports_cookie_presence_without_reading_values(tmp_path):
    cookie_file = tmp_path / "Default" / "Network" / "Cookies"
    cookie_file.parent.mkdir(parents=True)
    cookie_file.write_bytes(b"sqlite header")
    (tmp_path / "Default" / "Preferences").write_text("{}", encoding="utf-8")

    health = profile_health(str(tmp_path))

    assert health["profile_exists"] is True
    assert health["cookie_store_exists"] is True
    assert health["cookie_store_bytes"] == len(b"sqlite header")


def test_browser_evidence_status_detects_matching_gsc_property():
    result = BrowserAttachResult(
        available=True,
        cdp_url="http://127.0.0.1:9222",
        browser="Chrome/120",
        tabs=[
            {
                "url": "https://search.google.com/search-console?resource_id=https://remotekat.com/",
                "title": "Search Console",
                "type": "page",
            },
            {"url": "https://analytics.google.com/analytics/web/", "title": "GA4", "type": "page"},
            {"url": "https://www.bing.com/webmasters/", "title": "Bing", "type": "page"},
        ],
    )

    statuses = browser_evidence_status(result, "https://remotekat.com/")

    assert statuses[0]["source"] == "gsc"
    assert statuses[0]["status"] == "ready"
    assert statuses[1]["status"] == "open"


def test_browser_evidence_findings_turn_captured_pages_into_verified_findings():
    captures = [
        {
            "source": "gsc",
            "status": "captured",
            "title": "Search Console",
            "url": "https://search.google.com/search-console?resource_id=https://remotekat.com/",
            "textLength": 1200,
            "textExcerpt": "Clicks Impressions Queries Pages",
            "signals": {"has_clicks": True, "has_impressions": True},
        },
        {
            "source": "ga4",
            "status": "captured",
            "title": "Google Analytics",
            "url": "https://analytics.google.com/analytics/web/",
            "textLength": 900,
            "textExcerpt": "Users Sessions Landing page",
            "signals": {"has_users": True, "has_sessions": True},
        },
    ]

    findings = browser_evidence_findings(captures, "https://remotekat.com/")

    assert [finding.id for finding in findings] == ["BROWSER-GSC-001", "BROWSER-GA4-001"]
    assert findings[0].dimension == "search_performance"
    assert findings[1].dimension == "ux_business_outcome"
    assert all(finding.status == "passed" for finding in findings)
