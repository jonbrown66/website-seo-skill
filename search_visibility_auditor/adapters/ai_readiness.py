from __future__ import annotations

from urllib.parse import urljoin

from ..crawler import fetch_url, parse_page, robots_allowed
from ..models import AdapterResult, Finding, utc_now
from .base import Adapter


AI_USER_AGENTS = ["GPTBot", "Google-Extended", "ClaudeBot", "PerplexityBot", "CCBot"]
DEFAULT_USER_AGENT = "WebsiteSEOAudit/0.1"


class AIReadinessAdapter(Adapter):
    name = "ai_readiness"

    def run(self, context: dict) -> AdapterResult:
        url = context["url"]
        timeout = context.get("timeout", 10)
        user_agent = context.get("user_agent", DEFAULT_USER_AGENT)
        findings: list[Finding] = []
        raw: dict = {"ai_user_agents": AI_USER_AGENTS}

        llms_url = urljoin(url, "/llms.txt")
        try:
            status, final_url, content_type, body = fetch_url(llms_url, user_agent, timeout, max_bytes=500_000, retries=0)
            raw["llms_txt"] = {"status": status, "url": final_url, "content_type": content_type, "bytes": len(body.encode("utf-8"))}
            if 200 <= status < 300 and body.strip():
                findings.append(_finding("AI-LLMS-001", "llms.txt is available", "passed", "informational", url, {"observed": {"status": status, "bytes": len(body.encode("utf-8"))}, "expected": "Readable /llms.txt"}, "Keep llms.txt concise, accurate, and aligned with indexable product content."))
            else:
                findings.append(_finding("AI-LLMS-001", "llms.txt is not available", "warning", "low", url, {"observed": status, "expected": "Readable /llms.txt"}, "Add /llms.txt with concise product, audience, and key page guidance for AI crawlers.", confidence=0.8))
        except Exception as exc:
            raw["llms_txt"] = {"error": str(exc)}
            findings.append(_finding("AI-LLMS-001", "llms.txt could not be fetched", "warning", "low", url, {"observed": exc.__class__.__name__, "expected": "Readable /llms.txt"}, "Add or expose /llms.txt if AI crawler guidance is part of the strategy.", confidence=0.7))

        bot_results = []
        for bot in AI_USER_AGENTS:
            allowed, robots_url = robots_allowed(url, url, bot, timeout)
            bot_results.append({"user_agent": bot, "allowed": allowed, "robots_url": robots_url})
        raw["robots_ai_access"] = bot_results
        blocked = [item["user_agent"] for item in bot_results if not item["allowed"]]
        if blocked:
            findings.append(_finding("AI-ROBOTS-001", "Robots rules block some AI crawlers", "warning", "medium", url, {"observed": blocked, "expected": "Important public pages allow intended AI crawlers"}, "Review robots.txt and unblock AI crawlers that are part of the visibility strategy.", confidence=0.9))
        else:
            findings.append(_finding("AI-ROBOTS-001", "Robots rules allow tested AI crawlers", "passed", "informational", url, {"observed": [item["user_agent"] for item in bot_results], "expected": "Important public pages allow intended AI crawlers"}, "No action required."))

        try:
            status, final_url, content_type, body = fetch_url(url, user_agent, timeout, max_bytes=2_000_000, retries=0)
            page = parse_page(url, status, final_url, content_type, body)
            raw["homepage_ai_readiness"] = {"status": status, "word_count": page.word_count, "schema_blocks": len(page.schema_blocks), "title": page.title}
            if page.schema_blocks:
                findings.append(_finding("AI-SCHEMA-001", "Structured data is available for machine interpretation", "passed", "informational", url, {"observed": len(page.schema_blocks), "expected": "Valid JSON-LD where relevant"}, "Keep schema aligned with visible page content."))
            else:
                findings.append(_finding("AI-SCHEMA-001", "No structured data found on the homepage", "warning", "low", url, {"observed": 0, "expected": "Relevant JSON-LD where useful"}, "Add accurate Organization, WebSite, Product, SoftwareApplication, FAQ, or Breadcrumb schema only where it matches visible content.", confidence=0.75))
        except Exception as exc:
            raw["homepage_ai_readiness"] = {"error": str(exc)}
            findings.append(_finding("AI-HOMEPAGE-001", "Homepage AI readiness could not be checked", "error", "low", url, {"observed": exc.__class__.__name__, "expected": "Fetchable public homepage"}, "Rerun after homepage fetch succeeds.", confidence=0.5))

        return AdapterResult(adapter=self.name, status="ok", findings=findings, raw=raw)


def _finding(rule_id: str, title: str, status: str, severity: str, url: str, evidence: dict, recommendation: str, confidence: float = 1.0) -> Finding:
    return Finding(
        id=rule_id,
        rule_version="2.0.0",
        source="ai_readiness",
        category="geo_ai_readiness",
        dimension="ai_visibility",
        title=title,
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,
        evidence_type="verified",
        affected_urls=[url],
        evidence=evidence,
        impact=2 if status in {"warning", "error"} else 0,
        effort=1,
        reach=1,
        recommendation=recommendation,
        validation={"method": f"Re-run {rule_id}", "expected_result": evidence.get("expected", "")},
        fix_prompt=f"Address {rule_id}: {recommendation}",
        detected_at=utc_now(),
    )
