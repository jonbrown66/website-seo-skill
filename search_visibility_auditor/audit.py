from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .adapters.aeo_geo import AEOGeoAdapter
from .adapters.ai_citations import AICitationsAdapter
from .adapters.ai_readiness import AIReadinessAdapter
from .adapters.base import unavailable
from .adapters.internal_crawler import InternalCrawlerAdapter
from .adapters.pagespeed import PageSpeedAdapter
from .adapters.source_project import SourceProjectAdapter
from .models import AdapterResult, Finding
from .reporting import write_audit_outputs
from .scoring import score_findings
from .security import SecurityError, redact_secrets, validate_public_url
from .utils import read_config
from .models import utc_now

DEFAULT_USER_AGENT = "WebsiteSEOAudit/0.1"


def run_audit(options: dict) -> dict:
    config = read_config(Path(options["config"])) if options.get("config") else {}
    url = options.get("url") or config.get("domain") or config.get("url")
    source_path = options.get("source_path") or config.get("source_path")
    github = options.get("github") or config.get("github")
    if not url and not source_path and not github:
        raise ValueError("--url, --source-path, --github, or config.domain is required")
    public_crawl_blocked = False
    public_crawl_error = ""
    if url:
        try:
            url = validate_public_url(str(url))
        except SecurityError as exc:
            public_crawl_blocked = True
            public_crawl_error = str(exc)
            url = str(url)
    mode = options.get("mode") or "quick"
    context = {
        "url": url,
        "source_path": source_path,
        "github": github,
        "mode": mode,
        "max_pages": int(options.get("max_pages") or config.get("crawl", {}).get("max_pages") or 50),
        "timeout": int(options.get("timeout") or 10),
        "obey_robots": bool(config.get("crawl", {}).get("obey_robots", True)),
        "user_agent": os.getenv("WEBSITE_SEO_AUDIT_USER_AGENT")
        or os.getenv("SEARCH_VISIBILITY_USER_AGENT")
        or DEFAULT_USER_AGENT,
        "queries": config.get("queries", []),
        "country": options.get("country") or _first(config.get("target", {}).get("countries")),
        "language": options.get("language") or _first(config.get("target", {}).get("languages")),
    }
    adapters: list[AdapterResult] = []
    for adapter in _adapters_for_mode(mode, bool(url), bool(source_path), public_crawl_blocked):
        try:
            adapters.append(adapter.run(context))
        except Exception as exc:
            adapters.append(AdapterResult(adapter=adapter.name, status="error", reason=exc.__class__.__name__, impact=str(exc)))
    if public_crawl_blocked:
        adapters.insert(
            0,
            AdapterResult(
                adapter="target_resolution",
                status="blocked",
                reason="public_url_security_blocked",
                impact=public_crawl_error,
                findings=[_blocked_public_crawl_finding(str(url), public_crawl_error)],
            ),
        )
    if mode in {"verified", "full"}:
        adapters.extend(
            [
                unavailable("gsc", "credentials_missing", "Search Performance was not assessed"),
                unavailable("ga4", "credentials_missing", "Organic Conversion was not assessed"),
            ]
        )
    if mode == "full":
        adapters.extend(
            [
                unavailable("backlinks", "credentials_missing", "Authority and backlink gaps were not assessed"),
                unavailable("server_logs", "credentials_missing", "Bot crawl evidence was not assessed"),
            ]
        )
    findings = [finding for adapter in adapters for finding in adapter.findings]
    scores = score_findings(findings)
    audit_id = _audit_id(url or source_path or github or "source", mode)
    target = _target_metadata(str(url or ""), source_path, github, public_crawl_blocked, public_crawl_error, adapters)
    audit = {
        "audit_id": audit_id,
        "url": url,
        "source_path": source_path,
        "github": github,
        "mode": mode,
        "generated_at": utc_now(),
        "report_type": _report_type(bool(url), bool(source_path), bool(github), public_crawl_blocked),
        "public_crawl_blocked": public_crawl_blocked,
        "target": target,
        "scope": context,
        "implemented_scope": _implemented_scope(mode, bool(url), bool(source_path), bool(github)),
        "current_mode_boundary": _mode_boundary(mode),
        "not_implemented": [
            "JavaScript rendering",
            "real PageSpeed/CrUX metrics",
            "GSC API",
            "GA4 API",
            "backlinks",
            "server logs",
            "live AI citation providers",
            "competitor crawling",
            "historical storage",
            "native PDF rendering",
        ],
    }
    output_root = Path(options.get("output") or "reports")
    report_dir = write_audit_outputs(audit_id, output_root, redact_secrets(audit), findings, scores, adapters)
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    return {"audit": {**audit, "report": report}, "scores": scores, "report_dir": str(report_dir), "adapters": [adapter.to_dict() for adapter in adapters]}


def _adapters_for_mode(mode: str, has_url: bool = True, has_source: bool = False, public_crawl_blocked: bool = False):
    adapters = []
    if has_source:
        adapters.append(SourceProjectAdapter())
    if has_url and not public_crawl_blocked:
        adapters.append(InternalCrawlerAdapter())
    if has_url and mode in {"quick", "standard", "verified", "full"} and not public_crawl_blocked:
        adapters.append(PageSpeedAdapter())
    if has_url and not public_crawl_blocked:
        adapters.append(AIReadinessAdapter())
        adapters.append(AEOGeoAdapter())
    if mode in {"standard", "verified", "full"}:
        adapters.append(AICitationsAdapter())
    return adapters


def _implemented_scope(mode: str, has_url: bool, has_source: bool, has_github: bool) -> str:
    available = ["normalized findings", "coverage-aware scoring", "JSON/Markdown/HTML reports", "report validation", "score comparison"]
    if has_url:
        available.append("deterministic public URL readiness checks")
    if has_source or has_github:
        available.append("source readiness checks")
    if mode == "zero":
        available.append("fixed-profile browser evidence capture when CDP can read authorized pages")
    return "MVP readiness audit: " + ", ".join(available) + "."


def _mode_boundary(mode: str) -> dict:
    boundaries = {
        "quick": {
            "supported": "Public/source readiness checks from deterministic crawl and parsers.",
            "not_supported": "Rankings, traffic, conversions, Core Web Vitals, backlinks, and AI citation proof.",
        },
        "standard": {
            "supported": "Quick checks plus standard report envelope and citation placeholders.",
            "not_supported": "Competitor crawling and live AI citation execution.",
        },
        "verified": {
            "supported": "Readiness checks plus explicit not_assessed placeholders for missing authorized data.",
            "not_supported": "GSC API, GA4 API, and real PageSpeed/CrUX integration.",
        },
        "full": {
            "supported": "Broadest report envelope with unsupported modules marked not_assessed.",
            "not_supported": "Backlinks, logs, live AI providers, historical store, and native PDF rendering.",
        },
        "zero": {
            "supported": "Readiness checks plus browser/CDP evidence capture when signed-in pages are readable.",
            "not_supported": "API-grade exports unless downloaded or parsed as evidence.",
        },
    }
    return boundaries.get(mode, boundaries["quick"])


def _report_type(has_url: bool, has_source: bool, has_github: bool, public_crawl_blocked: bool) -> str:
    if public_crawl_blocked and has_source:
        return "Blocked Public Crawl Diagnostic + Source Readiness Review"
    if public_crawl_blocked:
        return "Blocked Public Crawl Diagnostic"
    if has_url and has_source:
        return "Public + Source Search Readiness Audit"
    if has_source:
        return "Pre-launch Source Readiness Review"
    if has_github:
        return "Repository Search Readiness Review"
    return "Public Quick Scan"


def _target_metadata(url: str, source_path: str | None, github: str | None, blocked: bool, blocked_reason: str, adapters: list[AdapterResult]) -> dict:
    candidates = []
    for adapter in adapters:
        if adapter.adapter == "source_project":
            candidates.extend(adapter.raw.get("target_candidates", []))
    return {
        "selected": url or "",
        "status": "blocked" if blocked else "confirmed" if url else "unconfirmed",
        "confidence": "high" if url and not blocked else "medium" if url else "low",
        "blocked_reason": blocked_reason,
        "source_path": source_path,
        "github": github,
        "candidates": candidates,
    }


def _blocked_public_crawl_finding(url: str, reason: str) -> Finding:
    return Finding(
        id="TARGET-CRAWL-001",
        rule_version="2.0.0",
        source="target_resolution",
        category="target_resolution",
        dimension="seo_foundation",
        title="Public URL could not be safely crawled",
        status="not_assessed",
        severity="informational",
        confidence=1.0,
        evidence_type="verified",
        affected_urls=[url],
        evidence={"observed": reason, "expected": "public URL resolves to crawlable public IP ranges"},
        impact=0,
        effort=1,
        reach=1,
        recommendation="Verify DNS/network policy from a public crawler or run the audit from an environment that resolves the production host normally.",
        validation={"method": "Resolve and fetch public URL from an allowed network", "expected_result": "HTTP crawl completes without SSRF guard blocking"},
        fix_prompt="Validate production DNS and rerun public crawl from an allowed network before making public visibility conclusions.",
    )


def _audit_id(url: str, mode: str) -> str:
    digest = hashlib.sha1(f"{url}|{mode}|{utc_now()}".encode("utf-8")).hexdigest()[:10]
    return f"{mode}-{digest}"


def _first(value):
    if isinstance(value, list) and value:
        return value[0]
    return value or ""
