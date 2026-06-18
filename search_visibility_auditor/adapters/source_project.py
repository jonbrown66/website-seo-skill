from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from ..models import AdapterResult, Finding, utc_now
from .base import Adapter


SAFE_FILE_NAMES = {
    "package.json",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "vercel.json",
    "README.md",
    "readme.md",
}
SECRET_FILE_NAMES = {".env", ".env.local", ".env.production", ".env.development", ".npmrc"}
EXCLUDED_DIRS = {".git", ".next", "node_modules", "dist", "build", "coverage", ".turbo", ".vercel", "reports"}
EXCLUDED_SUFFIXES = {".map", ".lock"}
NON_TARGET_HOSTS = {
    "github.com",
    "img.shields.io",
    "nextjs.org",
    "react.dev",
    "supabase.com",
    "tailwindcss.com",
    "ui.shadcn.com",
    "www.w3.org",
}
URL_PATTERN = re.compile(r"https?://[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")


class SourceProjectAdapter(Adapter):
    name = "source_project"

    def run(self, context: dict) -> AdapterResult:
        source_path = Path(context["source_path"]).resolve()
        if not source_path.exists() or not source_path.is_dir():
            return AdapterResult(self.name, "error", reason="source_path_missing", impact=str(source_path))

        findings: list[Finding] = []
        raw = {
            "source_path": str(source_path),
            "framework": _detect_framework(source_path),
            "target_candidates": _target_candidates(source_path),
            "routes": _route_inventory(source_path),
            "public_assets": _public_assets(source_path),
            "inspected_at": utc_now(),
        }
        findings.extend(_metadata_findings(source_path, context, raw))
        findings.extend(_public_resource_findings(source_path, context))
        findings.extend(_asset_findings(source_path, context, raw["public_assets"]))
        return AdapterResult(self.name, "ok", findings=findings, raw=raw)


def _detect_framework(source_path: Path) -> str:
    package = _read_json(source_path / "package.json")
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})} if package else {}
    if "next" in deps or (source_path / "app").exists():
        return "nextjs"
    return "unknown"


def _target_candidates(source_path: Path) -> list[dict]:
    candidates: dict[str, set[str]] = {}
    for path in _safe_text_files(source_path):
        if not _is_target_signal_file(path, source_path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for url in URL_PATTERN.findall(text):
            normalized = url.rstrip(")'\"`,;")
            try:
                parsed = urlparse(normalized)
                hostname = (parsed.hostname or "").lower()
            except ValueError:
                continue
            if not hostname or "." not in hostname or hostname in NON_TARGET_HOSTS:
                continue
            if hostname.startswith(("api.", "cdn.", "fonts.", "test-api.")):
                continue
            if "localhost" in normalized or "127.0.0.1" in normalized:
                continue
            candidates.setdefault(normalized, set()).add(str(path.relative_to(source_path)))
    return [{"url": url, "sources": sorted(sources)} for url, sources in sorted(candidates.items())]


def _route_inventory(source_path: Path) -> list[str]:
    app_dir = source_path / "app"
    if not app_dir.exists():
        return []
    routes = []
    for file in app_dir.rglob("page.*"):
        if any(part.startswith("_") for part in file.parts):
            continue
        route = "/" + "/".join(file.relative_to(app_dir).parent.parts)
        routes.append(route.replace("\\", "/").replace("/page", "") or "/")
    return sorted(set(routes))


def _public_assets(source_path: Path) -> list[dict]:
    public_dir = source_path / "public"
    if not public_dir.exists():
        return []
    assets = []
    for path in public_dir.rglob("*"):
        if path.is_file():
            assets.append({"path": str(path.relative_to(source_path)), "bytes": path.stat().st_size})
    return sorted(assets, key=lambda item: item["bytes"], reverse=True)


def _metadata_findings(source_path: Path, context: dict, raw: dict) -> list[Finding]:
    findings: list[Finding] = []
    layout_files = list((source_path / "app").rglob("layout.*")) if (source_path / "app").exists() else []
    selected_url = str(context.get("url") or "").rstrip("/")
    for layout in layout_files:
        text = layout.read_text(encoding="utf-8", errors="ignore")
        rel = str(layout.relative_to(source_path))
        if "metadataBase" in text and "localhost:3000" in text:
            findings.append(_finding("SRC-META-BASE-001", rel, "metadataBase falls back to localhost", "warning", "medium", {"observed": "localhost fallback in metadataBase", "expected": "production public origin from deployment config"}, "Use a production-safe NEXT_PUBLIC_APP_URL fallback and validate deployment env.", 3, 1, "seo_foundation"))
        og_urls = [url.rstrip("\"'`,)") for url in URL_PATTERN.findall(text) if "localhost" not in url]
        if selected_url:
            mismatches = [url for url in og_urls if _origin(url) and _origin(url) != _origin(selected_url)]
            if mismatches:
                findings.append(_finding("SRC-OG-URL-001", rel, "Open Graph URL does not match selected production target", "failed", "high", {"observed": sorted(set(mismatches)), "expected": selected_url}, "Align Open Graph, canonical, and metadataBase with the confirmed production domain.", 4, 1, "seo_foundation"))
        if "localhost:3000" in text and ("openGraph" in text or "twitter" in text):
            findings.append(_finding("SRC-OG-IMAGE-001", rel, "Social image metadata references localhost", "failed", "high", {"observed": "localhost image URL", "expected": "absolute production URL or metadataBase-relative asset"}, "Remove localhost URLs from Open Graph/Twitter metadata.", 4, 1, "seo_foundation"))
        if "locales" in (source_path / "i18n" / "routing.ts").read_text(encoding="utf-8", errors="ignore") if (source_path / "i18n" / "routing.ts").exists() else False:
            if "alternates" not in text:
                findings.append(_finding("SRC-I18N-HREFLANG-001", rel, "Localized app lacks metadata alternates", "warning", "medium", {"observed": "i18n routing exists without alternates metadata", "expected": "alternates.languages or equivalent hreflang output"}, "Add locale alternates for public localized routes.", 3, 2, "seo_foundation"))
    if not layout_files:
        findings.append(_finding("SRC-META-001", "app/", "No App Router layout metadata found", "not_assessed", "informational", {"observed": "no layout files", "expected": "layout metadata when using Next.js App Router"}, "Confirm the framework and metadata source before scoring SEO metadata.", 0, 1, "seo_foundation"))
    return findings


def _public_resource_findings(source_path: Path, context: dict) -> list[Finding]:
    checks = [
        ("SRC-ROBOTS-001", ["public/robots.txt", "app/robots.ts", "app/robots.js"], "Missing robots resource", "Add app/robots.ts or public/robots.txt for launch crawl rules."),
        ("SRC-SITEMAP-001", ["public/sitemap.xml", "app/sitemap.ts", "app/sitemap.js"], "Missing sitemap resource", "Add app/sitemap.ts or public/sitemap.xml with public canonical routes."),
        ("SRC-LLMS-001", ["public/llms.txt"], "Missing llms.txt", "Add public/llms.txt if AI answer-engine readiness is a product goal."),
        ("SRC-MANIFEST-001", ["public/manifest.json", "app/manifest.ts", "app/manifest.js"], "Missing web manifest", "Add a manifest when the app should produce install/share metadata."),
    ]
    findings = []
    for rule_id, paths, title, recommendation in checks:
        if not any((source_path / path).exists() for path in paths):
            severity = "medium" if rule_id in {"SRC-ROBOTS-001", "SRC-SITEMAP-001"} else "low"
            findings.append(_finding(rule_id, "source", title, "warning", severity, {"observed": "missing", "expected": " or ".join(paths)}, recommendation, 3 if severity == "medium" else 1, 1, "seo_foundation" if severity == "medium" else "ai_visibility"))
    return findings


def _asset_findings(source_path: Path, context: dict, assets: list[dict]) -> list[Finding]:
    findings = []
    oversized = [asset for asset in assets if asset["bytes"] > 1_000_000 and asset["path"].lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    if oversized:
        findings.append(_finding("SRC-ASSET-001", "public/", "Large public image assets may hurt first-load performance", "warning", "medium", {"observed": oversized[:8], "expected": "Critical public images compressed and appropriately sized"}, "Compress or replace large public images, especially first-viewport artwork.", 3, 2, "ux_business_outcome", category="performance", evidence_type="verified"))
    return findings


def _finding(
    rule_id: str,
    source_path: str,
    title: str,
    status: str,
    severity: str,
    evidence: dict,
    recommendation: str,
    impact: float,
    effort: float,
    dimension: str,
    category: str = "source_readiness",
    evidence_type: str = "verified",
) -> Finding:
    return Finding(
        id=rule_id,
        rule_version="2.0.0",
        source="source_project",
        category=category,
        dimension=dimension,
        title=title,
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        confidence=0.95,
        evidence_type=evidence_type,  # type: ignore[arg-type]
        affected_urls=[source_path],
        evidence=evidence,
        impact=impact,
        effort=effort,
        reach=1,
        recommendation=recommendation,
        validation={"method": f"Re-run source rule {rule_id}", "expected_result": evidence.get("expected", "")},
        fix_prompt=f"Fix {rule_id} in {source_path}. Observed: {evidence.get('observed')}. Expected: {evidence.get('expected')}.",
    )


def _safe_text_files(source_path: Path) -> list[Path]:
    files = []
    for path in source_path.rglob("*"):
        if not path.is_file() or path.name in SECRET_FILE_NAMES:
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(source_path).parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if path.name in SAFE_FILE_NAMES or path.suffix in {".ts", ".tsx", ".js", ".jsx", ".md", ".json"}:
            if path.stat().st_size <= 250_000:
                files.append(path)
    return files


def _is_target_signal_file(path: Path, source_path: Path) -> bool:
    relative = path.relative_to(source_path)
    if path.name in {"README.md", "readme.md", "next.config.js", "next.config.mjs", "next.config.ts", "vercel.json"}:
        return True
    if path.name.startswith(("layout.", "sitemap.", "robots.", "manifest.")):
        return True
    if relative.parts and relative.parts[0] in {"app", "pages"} and path.name in {"layout.tsx", "layout.ts", "_document.tsx", "_app.tsx"}:
        return True
    return False


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _origin(url: str) -> str:
    match = re.match(r"^https?://[^/]+", url.rstrip("/"))
    return match.group(0).lower() if match else ""
