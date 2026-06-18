from __future__ import annotations

import json
from pathlib import Path

from .models import AdapterResult, Finding
from .rules import aggregate_by_rule
from .security import escape_html, redact_secrets, safe_join
from .utils import write_json


REPORT_SECTIONS = [
    "Cover",
    "Audit Scope",
    "Executive Summary",
    "Overall Score",
    "Data Coverage",
    "Confidence Level",
    "Six Dimension Scores",
    "Top 5 Critical Opportunities",
    "Technical SEO",
    "Content & AEO",
    "GEO & AI Readiness",
    "AI Citation Visibility",
    "Search Performance",
    "Authority & Entity",
    "UX & Conversion",
    "Competitor Comparison",
    "Page-level Findings",
    "30-day Plan",
    "60-day Plan",
    "90-day Plan",
    "Fix Prompts",
    "Methodology",
    "Data Sources",
    "Limitations",
]


def write_audit_outputs(audit_id: str, output_root: Path, audit: dict, findings: list[Finding], scores: dict, adapters: list[AdapterResult]) -> Path:
    report_dir = safe_join(output_root, audit_id)
    raw_dir = safe_join(report_dir, "raw")
    evidence_dir = safe_join(report_dir, "evidence")
    raw_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    findings_data = [finding.to_dict() for finding in sorted(findings, key=lambda f: f.priority_score, reverse=True)]
    enterprise_report = build_enterprise_report(audit, findings, scores, adapters)
    audit_data = redact_secrets({**audit, "scores": scores, "findings": findings_data, "adapters": [adapter.to_dict() for adapter in adapters], "report": enterprise_report})
    write_json(safe_join(report_dir, "audit.json"), audit_data)
    write_json(safe_join(report_dir, "report.json"), enterprise_report)
    write_json(safe_join(report_dir, "findings.json"), redact_secrets(findings_data))
    write_json(safe_join(report_dir, "scores.json"), redact_secrets(scores))
    write_json(safe_join(report_dir, "summary.json"), build_summary(audit, findings, scores, adapters))
    for adapter in adapters:
        write_json(safe_join(raw_dir, f"{adapter.adapter}.json"), redact_secrets(adapter.raw or adapter.to_dict()))
    safe_join(report_dir, "fix-prompts.md").write_text(render_fix_prompts(findings), encoding="utf-8")
    safe_join(report_dir, "audit.md").write_text(render_markdown_from_report(enterprise_report), encoding="utf-8")
    html_content = render_html_from_report(enterprise_report)
    safe_join(report_dir, "audit.html").write_text(html_content, encoding="utf-8")
    _write_pdf(safe_join(report_dir, "audit.pdf"), html_content)
    return report_dir


def _write_pdf(pdf_path: Path, html_content: str) -> None:
    """Render audit.pdf from the HTML report using weasyprint.

    Falls back to a plain-text notice if the optional dependency is missing
    or its native libraries are unavailable (common on Windows without GTK3).
    """
    try:
        from weasyprint import HTML  # noqa: F811
    except (ImportError, OSError) as exc:
        pdf_path.write_text(
            f"PDF generation requires weasyprint with native libraries.\n"
            f"Install: pip install website-seo-audit[pdf]\n"
            f"On Windows you may also need GTK3: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows\n"
            f"Error: {exc}\n",
            encoding="utf-8",
        )
        return
    try:
        HTML(string=html_content).write_pdf(pdf_path)
    except Exception as exc:
        pdf_path.write_text(f"PDF generation failed: {exc}\n", encoding="utf-8")


def build_enterprise_report(audit: dict, findings: list[Finding], scores: dict, adapters: list[AdapterResult]) -> dict:
    ordered = sorted(findings, key=lambda f: f.priority_score, reverse=True)
    actionable = [f for f in ordered if f.status in {"failed", "warning", "error"}]
    aggregated = aggregate_by_rule(actionable)
    blocked = _blocked_items(adapters, findings)
    target = audit.get("target") or {"selected": audit.get("url", ""), "status": "confirmed", "confidence": "medium", "candidates": []}
    score_card = _score_card(scores)
    eligibility = _conclusion_eligibility(audit, adapters)
    report_type = audit.get("report_type") or _report_type(audit, adapters)
    top_fixes = [_finding_card(f) for f in aggregated[:6]]
    primary_action = _primary_action(top_fixes, blocked, score_card)
    data_sources = [
        {
            "name": adapter.adapter,
            "status": adapter.status,
            "reason": adapter.reason,
            "impact": adapter.impact,
            "findings": len(adapter.findings),
        }
        for adapter in adapters
    ]
    report = {
        "schema_version": "2.0.0",
        "audit_id": audit["audit_id"],
        "generated_at": audit.get("generated_at", ""),
        "report_type": report_type,
        "mode": audit.get("mode", ""),
        "target": target,
        "executive_decision": {
            "primary_action": primary_action,
            "score_status": score_card["status"],
            "target_confidence": target.get("confidence", "unknown"),
            "top_fix_ids": list(dict.fromkeys(item["id"] for item in top_fixes)),
            "blocker_count": len(blocked),
        },
        "score_card": score_card,
        "evidence_coverage": {
            "data_coverage": scores.get("data_coverage"),
            "confidence": scores.get("confidence"),
            "verified_evidence_ratio": scores.get("verified_evidence_ratio"),
            "inferred_evidence_ratio": scores.get("inferred_evidence_ratio"),
            "unknown_ratio": scores.get("unknown_ratio"),
            "assessed_dimensions": [name for name, item in scores.get("dimensions", {}).items() if item.get("assessed")],
            "not_assessed_dimensions": [name for name, item in scores.get("dimensions", {}).items() if not item.get("assessed")],
            "blocked": blocked,
        },
        "conclusion_eligibility": eligibility,
        "data_sources": data_sources,
        "dimension_scores": _dimension_view(scores),
        "top_opportunities": top_fixes,
        "verified_findings": [_finding_card(f) for f in ordered if f.evidence_type == "verified"],
        "inferred_opportunities": [_finding_card(f) for f in ordered if f.evidence_type == "inferred"],
        "blocked_or_not_assessed": blocked,
        "fix_roadmap": _roadmap(aggregated),
        "all_findings": [_finding_card(f) for f in ordered],
        "aggregated_findings": [_finding_card(f) for f in aggregated],
        "limitations": _limitations(audit, adapters, score_card, eligibility),
    }
    return redact_secrets(report)  # type: ignore[return-value]


def _report_type(audit: dict, adapters: list[AdapterResult]) -> str:
    if audit.get("public_crawl_blocked"):
        return "Blocked Public Crawl Diagnostic"
    if audit.get("source_path") and audit.get("url"):
        return "Public + Source Search Readiness Audit"
    if audit.get("source_path"):
        return "Pre-launch Source Readiness Review"
    if any(adapter.adapter in {"gsc", "ga4"} and adapter.status == "ok" for adapter in adapters):
        return "Verified Search Performance Audit"
    return "Public Quick Scan"


def _score_card(scores: dict) -> dict:
    coverage = float(scores.get("data_coverage") or 0)
    raw_score = scores.get("overall_score")
    if coverage >= 80:
        return {"label": "readiness_score", "score": raw_score, "status": "eligible", "explanation": "Coverage is high enough to show a scored readiness view."}
    if coverage >= 60:
        return {"label": "provisional_readiness_score", "score": raw_score, "status": "provisional", "explanation": "Coverage is partial; treat the score as directional only."}
    return {"label": "readiness_matrix", "score": None, "status": "blocked", "explanation": "Coverage is too low for a responsible overall score. Review blockers and assessed findings first."}


DIMENSION_LABELS = {
    "seo_foundation": "SEO Foundation",
    "content_answerability": "Content & Answerability",
    "authority_entity": "Authority & Entity",
    "search_performance": "Search Performance",
    "ai_visibility": "AI Visibility",
    "ux_business_outcome": "UX & Conversion",
}


def _dimension_view(scores: dict) -> list[dict]:
    """Flatten the six dimensions into a UI-friendly list with labels and
    assessment status, ordered by the canonical weight order."""
    order = ["seo_foundation", "content_answerability", "authority_entity", "search_performance", "ai_visibility", "ux_business_outcome"]
    dims = scores.get("dimensions", {})
    view = []
    for key in order:
        item = dims.get(key, {})
        score = item.get("score")
        view.append(
            {
                "key": key,
                "label": DIMENSION_LABELS.get(key, key),
                "weight": item.get("weight", 0),
                "score": score,
                "assessed": bool(item.get("assessed")),
                "findings": item.get("findings", 0),
            }
        )
    return view


def score_grade(score) -> str:
    """Letter grade for a 0-100 score, used on the cover."""
    if score is None:
        return "—"
    s = float(score)
    if s >= 90:
        return "A"
    if s >= 80:
        return "B"
    if s >= 70:
        return "C"
    if s >= 60:
        return "D"
    return "F"


def _conclusion_eligibility(audit: dict, adapters: list[AdapterResult]) -> dict:
    adapter_status = {adapter.adapter: adapter.status for adapter in adapters}
    crawler_ok = adapter_status.get("internal_crawler") == "ok"
    source_ok = adapter_status.get("source_project") == "ok"
    browser_ok = adapter_status.get("authorized_browser") == "ok"
    performance_ok = adapter_status.get("pagespeed") == "ok" or adapter_status.get("gsc") == "ok" or browser_ok
    conversion_ok = adapter_status.get("ga4") == "ok" or browser_ok
    ai_ok = adapter_status.get("ai_citations") == "ok" or adapter_status.get("ai_readiness") == "ok" or adapter_status.get("aeo_geo") == "ok"
    source_requested = bool(audit.get("source_path") or audit.get("github"))
    return {
        "crawlability": _eligibility(crawler_ok, "Public or rendered crawl completed", "Public crawl did not complete"),
        "indexability": _eligibility(crawler_ok, "Status, robots, canonical, and index directives were inspected", "Indexability requires a completed crawl"),
        "search_performance": _eligibility(performance_ok, "Authorized performance/search evidence was assessed through API or browser capture", "GSC, CrUX, PageSpeed, or equivalent data was not assessed"),
        "organic_conversion": _eligibility(conversion_ok, "Analytics or conversion evidence was assessed through API or browser capture", "GA4/product analytics was not assessed"),
        "ai_visibility": _eligibility(ai_ok, "AI access/readiness evidence was assessed; provider citation proof still requires live provider tests", "AI access/readiness or provider citation evidence was not assessed"),
        "source_readiness": {"status": "not_applicable", "reason": "No local/GitHub source was provided"} if not source_requested else _eligibility(source_ok, "Local/GitHub source inspected", "Source project was not inspected"),
    }


def _eligibility(ok: bool, eligible_reason: str, blocked_reason: str) -> dict:
    return {"status": "eligible" if ok else "not_assessed", "reason": eligible_reason if ok else blocked_reason}


def _blocked_items(adapters: list[AdapterResult], findings: list[Finding]) -> list[dict]:
    items = []
    authorized_browser_ok = any(adapter.adapter == "authorized_browser" and adapter.status == "ok" for adapter in adapters)
    ai_readiness_ok = any(adapter.adapter == "ai_readiness" and adapter.status == "ok" for adapter in adapters)
    for adapter in adapters:
        if authorized_browser_ok and adapter.adapter in {"gsc", "ga4"}:
            continue
        if ai_readiness_ok and adapter.adapter == "ai_citations":
            continue
        if adapter.status in {"unavailable", "error", "not_implemented", "blocked"}:
            items.append({"source": adapter.adapter, "status": adapter.status, "reason": adapter.reason, "impact": adapter.impact})
    for finding in findings:
        if finding.status == "not_assessed":
            items.append({"source": finding.source, "status": "not_assessed", "reason": finding.title, "impact": finding.recommendation, "finding_id": finding.id})
    return items


def _primary_action(top_fixes: list[dict], blocked: list[dict], score_card: dict) -> str:
    if score_card["status"] == "blocked" and blocked:
        return "Resolve evidence blockers before drawing growth conclusions."
    if top_fixes:
        return f"Prioritize {top_fixes[0]['id']}: {top_fixes[0]['title']}"
    return "No high-priority fixes were detected in the assessed scope."


def _finding_card(finding: Finding) -> dict:
    evidence = finding.evidence or {}
    affected_urls = finding.affected_urls or []
    page_count = evidence.get("page_count")
    if page_count is None:
        page_count = len({url for url in affected_urls if url})
    sample_urls = evidence.get("sample_urls") or affected_urls[:10]
    return {
        "id": finding.id,
        "title": finding.title,
        "status": finding.status,
        "severity": finding.severity,
        "dimension": finding.dimension,
        "category": finding.category,
        "confidence": finding.confidence,
        "evidence_type": finding.evidence_type,
        "affected_urls": affected_urls,
        "affected_count": page_count,
        "sample_urls": sample_urls,
        "evidence": evidence,
        "priority_score": finding.priority_score,
        "recommendation": finding.recommendation,
        "validation": finding.validation,
    }


def _roadmap(findings: list[Finding]) -> dict:
    stages = {"now": [], "next": [], "later": []}
    for finding in findings:
        card = _finding_card(finding)
        if finding.severity in {"critical", "high"} or finding.priority_score >= 6:
            stages["now"].append(card)
        elif finding.priority_score >= 2:
            stages["next"].append(card)
        else:
            stages["later"].append(card)
    return stages


def _limitations(audit: dict, adapters: list[AdapterResult], score_card: dict, eligibility: dict) -> list[str]:
    limitations = [
        "This report is based on collected evidence. N/A does not mean failure, but it lowers coverage and conclusion eligibility.",
        "This tool does not guarantee rankings, traffic, rich results, or AI citations.",
    ]
    if score_card["status"] == "blocked":
        limitations.append("Data coverage is below 60%, so the overall score is hidden and the report shows verified signals and blockers instead.")
    if audit.get("public_crawl_blocked"):
        limitations.append("Public crawling was blocked by local security or DNS policy, so public visibility, Core Web Vitals, search performance, and AI citation conclusions are unavailable.")
    for key, value in eligibility.items():
        if value["status"] == "not_assessed":
            limitations.append(f"{key}: {value['reason']}")
    return list(dict.fromkeys(limitations))


def build_summary(audit: dict, findings: list[Finding], scores: dict, adapters: list[AdapterResult]) -> dict:
    critical = [finding for finding in findings if finding.severity == "critical" and finding.status in {"failed", "warning"}]
    return redact_secrets(
        {
            "audit_id": audit["audit_id"],
            "mode": audit["mode"],
            "url": audit["url"],
            "overall_score": scores["overall_score"],
            "data_coverage": scores["data_coverage"],
            "confidence": scores["confidence"],
            "critical_findings": len(critical),
            "adapter_status": {adapter.adapter: adapter.status for adapter in adapters},
        }
    )


def render_fix_prompts(findings: list[Finding]) -> str:
    lines = ["# Fix Prompts", ""]
    for finding in sorted(findings, key=lambda f: f.priority_score, reverse=True):
        if finding.status not in {"failed", "warning"}:
            continue
        lines.extend([f"## {finding.id}: {finding.title}", "", finding.fix_prompt, ""])
    return "\n".join(lines)


def render_markdown_from_report(report: dict) -> str:
    score = report["score_card"]["score"]
    score_text = str(score) if score is not None else "N/A"
    assessed = ", ".join(_dim_label(name) for name in report["evidence_coverage"]["assessed_dimensions"]) or "None"
    not_assessed = ", ".join(_dim_label(name) for name in report["evidence_coverage"]["not_assessed_dimensions"]) or "None"
    critical = [f for f in report["top_opportunities"] if f.get("severity") in {"critical", "high"}]
    warnings = [f for f in report["top_opportunities"] if f.get("severity") in {"medium", "low"}]
    passing = [f for f in report.get("all_findings", []) if f.get("status") == "passed"][:8]
    lines = [
        f"# Website SEO Audit Report",
        "",
        f"**Report type:** {report['report_type']}",
        f"**URL:** {report['target'].get('selected', '')}",
        f"**Audit level:** `{report['mode']}`",
        f"**Created:** `{report['generated_at']}`",
        f"**Audit ID:** `{report['audit_id']}`",
        "",
        "## Audit Summary",
        "",
        report["executive_decision"]["primary_action"],
        "",
        "| Metric | Result | Notes |",
        "| --- | --- | --- |",
        f"| Score | `{score_text}` | {report['score_card']['label']} / {_status_label(report['score_card']['status'])} |",
        f"| Data coverage | `{report['evidence_coverage']['data_coverage']}%` | confidence: `{report['evidence_coverage']['confidence']}` |",
        f"| Target confidence | `{report['executive_decision']['target_confidence']}` | {_status_label(report['target'].get('status', 'unknown'))} |",
        f"| Blocked / not assessed | `{report['executive_decision']['blocker_count']}` | limits conclusions, not scored as failures |",
        "",
        "## Status Overview",
        "",
        "| Group | Items |",
        "| --- | --- |",
        f"| Critical | {_summary_cell(critical, 'None')} |",
        f"| Warnings | {_summary_cell(warnings, 'None')} |",
        f"| Passing | {_summary_cell(passing, 'None')} |",
        "",
        "## Assessed Scope",
        "",
        f"- Assessed dimensions: {assessed}",
        f"- Not assessed dimensions: {not_assessed}",
        "",
        "## Conclusion Eligibility",
        "",
        "| Conclusion | Status | Reason |",
        "| --- | --- | --- |",
    ]
    for name, item in report["conclusion_eligibility"].items():
        lines.append(f"| {_eligibility_label(name)} | `{_status_label(item['status'])}` | {item['reason']} |")
    browser = report.get("browser_capture")
    if browser:
        lines.extend(["", "## Browser Evidence", "", f"- Stage status: `{_status_label(browser.get('stage_status', 'unknown'))}` - {_browser_stage_label(browser.get('stage_status', 'unknown'))}"])
        for item in browser.get("status_summary", []):
            lines.append(f"- `{item.get('source')}`: `{_status_label(item.get('status'))}` - {item.get('detail')}")
    lines.extend(["", "## Priority Actions"])
    if not report["top_opportunities"]:
        lines.append("No failed or warning findings were detected in assessed data.")
    for finding in report["top_opportunities"]:
        count = finding.get("affected_count")
        scope = f" (affects {count} pages)" if count and count > 1 else ""
        lines.extend(
            [
                "",
                f"### {finding['id']} - {finding['title']} {scope}",
                "",
                f"- Status: `{_status_label(finding['status'])}` / severity `{finding['severity']}` / confidence `{finding['confidence']}`",
                f"- Evidence type: `{finding['evidence_type']}`",
                f"- Evidence: `{json.dumps(finding['evidence'], ensure_ascii=False)}`",
                f"- Fix: {finding['recommendation']}",
                f"- Acceptance: {finding['validation'].get('expected_result', '')}",
            ]
        )
    lines.extend(["", "## Blocked / Not Assessed"])
    if not report["blocked_or_not_assessed"]:
        lines.append("None.")
    for item in report["blocked_or_not_assessed"][:20]:
        lines.append(f"- {item.get('source')}: `{_status_label(item.get('status'))}` - {item.get('impact') or item.get('reason')}")
    # AEO/GEO signals
    aeo_geo = report.get("aggregated_findings", [])
    aeo = [f for f in aeo_geo if f.get("category") == "aeo" or f.get("id", "").startswith("AEO-")]
    geo = [f for f in aeo_geo if f.get("category") == "geo" or f.get("id", "").startswith("GEO-")]
    if aeo or geo:
        lines.extend(["", "## AEO / GEO Readiness Signals"])
        if aeo:
            lines.extend(["", "### AEO Answerability"])
            for f in aeo:
                lines.append(f"- `{f['id']}` {_status_label(f['status'])}: {f['title']} - {f.get('recommendation', '')}")
        if geo:
            lines.extend(["", "### GEO Entity & AI Readiness"])
            for f in geo:
                lines.append(f"- `{f['id']}` {_status_label(f['status'])}: {f['title']} - {f.get('recommendation', '')}")
    # Dimension scores
    dims = report.get("dimension_scores", [])
    if dims:
        lines.extend(["", "## Dimension Scores"])
        for dim in dims:
            s = "—" if dim.get("score") is None else str(dim["score"])
            lines.append(f"- `{dim['label']}`: {s} (weight {dim['weight']}, assessed={dim['assessed']})")
    lines.extend(["", "## Limitations"])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines)


def _summary_cell(items: list[dict], empty: str) -> str:
    if not items:
        return empty
    return "<br>".join(f"`{item.get('id', '')}` {item.get('title', '')}" for item in items[:6])


def _radar_chart_svg(dimension_scores: list[dict], size: int = 320) -> str:
    """Server-side SVG radar chart over the six dimensions. assessed dims draw
    a filled polygon scaled to their score; not_assessed dims pull toward 0
    and render as a dashed grey ring marker. No JS required."""
    import math

    n = len(dimension_scores)
    if n < 3:
        return ""
    center = size / 2
    radius = size / 2 - 54
    angles = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]

    rings = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = ",".join(
            f"{center + radius * frac * math.cos(angles[i]):.1f},{center + radius * frac * math.sin(angles[i]):.1f}"
            for i in range(n)
        )
        rings.append(f'<polygon points="{pts}" fill="none" stroke="#e4e7ec" stroke-width="1"/>')

    spokes = "".join(
        f'<line x1="{center:.1f}" y1="{center:.1f}" x2="{center + radius * math.cos(angles[i]):.1f}" y2="{center + radius * math.sin(angles[i]):.1f}" stroke="#e4e7ec" stroke-width="1"/>'
        for i in range(n)
    )

    data_pts = []
    for i, dim in enumerate(dimension_scores):
        score = dim.get("score")
        value = 0.05 if score is None else max(0.05, float(score) / 100)
        data_pts.append((center + radius * value * math.cos(angles[i]), center + radius * value * math.sin(angles[i])))

    polygon = "L".join(f"{x:.1f} {y:.1f}" for x, y in data_pts)
    area = f'<path d="M{polygon} Z" fill="rgba(29,78,216,0.18)" stroke="#1d4ed8" stroke-width="2"/>'

    dots = ""
    for i, dim in enumerate(dimension_scores):
        x, y = data_pts[i]
        if dim.get("score") is None:
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#fff" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="2 2"/>'
        else:
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#1d4ed8"/>'

    labels = ""
    for i, dim in enumerate(dimension_scores):
        lx = center + (radius + 22) * math.cos(angles[i])
        ly = center + (radius + 22) * math.sin(angles[i])
        anchor = "middle"
        if math.cos(angles[i]) > 0.3:
            anchor = "start"
        elif math.cos(angles[i]) < -0.3:
            anchor = "end"
        value_text = "—" if dim.get("score") is None else str(dim.get("score"))
        color = "#94a3b8" if dim.get("score") is None else "#172033"
        labels += f'<text x="{lx:.1f}" y="{ly - 4:.1f}" text-anchor="{anchor}" font-size="11" fill="#475467">{escape_html(dim["label"])}</text>'
        labels += f'<text x="{lx:.1f}" y="{ly + 10:.1f}" text-anchor="{anchor}" font-size="12" font-weight="700" fill="{color}">{escape_html(value_text)}</text>'

    return (
        f'<svg viewBox="0 0 {size} {size}" class="radar" role="img" aria-label="Dimension score radar chart">'
        f'{"".join(rings)}{spokes}{area}{dots}{labels}'
        f"</svg>"
    )


def _dimension_bars_html(dimension_scores: list[dict]) -> str:
    rows = []
    for dim in dimension_scores:
        score = dim.get("score")
        assessed = dim.get("assessed")
        if score is None:
            bar = '<div class="bar-track"><div class="bar-fill na" style="width:100%"></div><span class="bar-label">N/A</span></div>'
        else:
            width = max(2, float(score))
            tone = "good" if score >= 80 else "warn" if score >= 60 else "bad"
            bar = f'<div class="bar-track"><div class="bar-fill {tone}" style="width:{width:.1f}%"></div><span class="bar-label">{escape_html(str(score))}</span></div>'
        rows.append(
            f'<div class="dim-row"><div class="dim-name">{escape_html(dim["label"])}<span class="dim-weight">Weight {dim["weight"]}</span></div>{bar}</div>'
        )
    return "".join(rows)


def render_html_from_report(report: dict) -> str:
    score = report["score_card"]["score"]
    score_text = "N/A" if score is None else str(score)
    grade = score_grade(score)
    dimension_scores = report.get("dimension_scores", [])
    radar_svg = _radar_chart_svg(dimension_scores)
    dim_bars = _dimension_bars_html(dimension_scores)
    top_cards = "".join(_finding_html(item, index) for index, item in enumerate(report["top_opportunities"][:6], start=1))
    if not top_cards:
        top_cards = '<p class="empty">No Fail or Warning findings were detected in the assessed scope.</p>'
    critical_items = [item for item in report["top_opportunities"] if item.get("severity") in {"critical", "high"}]
    warning_items = [item for item in report["top_opportunities"] if item.get("severity") in {"medium", "low"}]
    passing_items = [item for item in report.get("all_findings", []) if item.get("status") == "passed"][:8]
    summary_groups = _summary_groups_html(critical_items, warning_items, passing_items)
    coverage_rows = "".join(
        f"<tr><td>{escape_html(item['name'])}</td><td><span class=\"status-badge {_status_class(item['status'])}\">{escape_html(_status_label(item['status']))}</span></td><td>{escape_html(item['impact'] or item['reason'])}</td></tr>"
        for item in report["data_sources"]
    )
    eligibility_rows = "".join(
        f"<tr><td>{escape_html(_eligibility_label(name))}</td><td><span class=\"status-badge {_status_class(item['status'])}\">{escape_html(_status_label(item['status']))}</span></td><td>{escape_html(item['reason'])}</td></tr>"
        for name, item in report["conclusion_eligibility"].items()
    )
    blocked_items = "".join(
        f"<li><strong>{escape_html(item.get('source'))}</strong> <span class=\"status-badge {_status_class(item.get('status'))}\">{escape_html(_status_label(item.get('status')))}</span><p>{escape_html(item.get('impact') or item.get('reason'))}</p></li>"
        for item in report["blocked_or_not_assessed"][:12]
    )
    roadmap_now = "".join(_compact_finding_html(item) for item in report["fix_roadmap"]["now"][:8]) or "<p class=\"empty\">No immediate P0/P1 fixes.</p>"
    roadmap_next = "".join(_compact_finding_html(item) for item in report["fix_roadmap"]["next"][:8]) or "<p class=\"empty\">No next-stage fixes.</p>"
    roadmap_later = "".join(_compact_finding_html(item) for item in report["fix_roadmap"]["later"][:6]) or "<p class=\"empty\">No later-stage optimizations.</p>"
    limitations = "".join(f"<li>{escape_html(item)}</li>" for item in report["limitations"])
    assessed = ", ".join(_dim_label(name) for name in report["evidence_coverage"]["assessed_dimensions"]) or "None"
    not_assessed = ", ".join(_dim_label(name) for name in report["evidence_coverage"]["not_assessed_dimensions"]) or "None"
    browser_section = _browser_capture_html(report.get("browser_capture", {}))
    aeo_geo_section = _aeo_geo_section_html(report)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape_html(report['report_type'])} · {escape_html(report['target'].get('selected', ''))}</title>
  <style>
    :root {{ color-scheme: light; --ink:#17191f; --muted:#626976; --muted2:#475569; --faint:#8c94a3; --line:#dfe3ea; --line2:#cbd5e1; --soft:#f8fafc; --soft2:#f1f5f9; --paper:#ffffff; --accent:#0f62fe; --accent2:#0b4fbb; --accent-soft:#eef4ff; --danger:#b42318; --warn:#a15c07; --ok:#137333; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--ink); background:#f5f6f8; line-height:1.6; font-size:15px; }}
    a {{ color:var(--accent); }}
    .layout {{ max-width:1160px; margin:0 auto; padding:0 28px; }}
    nav.toc {{ display:none; }}
    main.report {{ min-height:100vh; padding:0 0 56px; }}
    .cover {{ background:#fff; border:1px solid var(--line); border-radius:6px; margin-bottom:20px; padding:0; box-shadow:0 1px 2px rgba(16,24,40,.04); overflow:hidden; }}
    .cover .kicker {{ display:block; color:var(--accent); font-weight:750; letter-spacing:.07em; text-transform:uppercase; font-size:13px; padding:14px 20px; border-bottom:1px solid #e8e8e8; background:#f9fbff; margin:0; }}
    .cover-body {{ padding:20px; }}
    .cover h1 {{ margin:0 0 8px; font-size:26px; line-height:1.24; }}
    .cover .target {{ color:var(--muted2); font-size:14px; word-break:break-all; }}
    .cover .meta {{ color:var(--muted); font-size:13px; margin-top:10px; }}
    .cover-score {{ display:flex; align-items:flex-end; gap:18px; margin-top:24px; }}
    .grade-circle {{ width:92px; height:92px; border-radius:8px; display:grid; place-items:center; background:var(--accent); color:#fff; flex-shrink:0; }}
    .grade-circle b {{ font-size:42px; font-weight:800; line-height:1; }}
    .grade-circle.na {{ background:var(--line2); }}
    .cover-score .score-line b {{ font-size:34px; font-weight:800; }}
    .cover-score .score-line .label {{ color:var(--muted); font-size:12px; }}
    section.chapter {{ background:#fff; border:1px solid var(--line); border-radius:6px; margin-bottom:20px; padding:0; box-shadow:0 1px 2px rgba(16,24,40,.04); }}
    h2.section {{ font-size:13px; margin:0; font-weight:750; letter-spacing:.07em; text-transform:uppercase; color:var(--accent); padding:14px 20px; border-bottom:1px solid #e8e8e8; background:#f9fbff; }}
    h2.section .num {{ color:var(--accent); font-weight:800; margin-right:8px; }}
    .section-sub {{ color:var(--muted); font-size:13px; margin:0; padding:18px 20px 0; }}
    .chapter-body {{ padding:20px; overflow-x:auto; }}
    .decision {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; align-items:center; border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:6px; padding:16px 18px; background:var(--soft); }}
    .decision-title {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }}
    .decision-action {{ font-size:19px; font-weight:750; line-height:1.35; }}
    .kpi-row {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:18px 0 0; }}
    .kpi {{ border:1px solid var(--line); border-radius:6px; padding:14px; background:#fff; }}
    .kpi b {{ display:block; font-size:26px; font-weight:800; line-height:1.1; }}
    .kpi span {{ color:var(--muted); font-size:12px; }}
    .viz-grid {{ display:grid; grid-template-columns:340px minmax(0,1fr); gap:32px; align-items:center; }}
    svg.radar {{ width:340px; height:340px; }}
    .dim-row {{ margin-bottom:14px; }}
    .dim-name {{ display:flex; justify-content:space-between; font-weight:650; margin-bottom:6px; font-size:13px; }}
    .dim-weight {{ color:var(--muted); font-weight:400; font-size:11px; }}
    .bar-track {{ position:relative; height:24px; background:var(--soft2); border-radius:6px; overflow:hidden; }}
    .bar-fill {{ height:100%; border-radius:6px; }}
    .bar-fill.good {{ background:linear-gradient(90deg,#10b981,#059669); }}
    .bar-fill.warn {{ background:linear-gradient(90deg,#f59e0b,#d97706); }}
    .bar-fill.bad {{ background:linear-gradient(90deg,#ef4444,#dc2626); }}
    .bar-fill.na {{ background:repeating-linear-gradient(45deg,#e2e8f0,#e2e8f0 8px,#f1f5f9 8px,#f1f5f9 16px); }}
    .bar-label {{ position:absolute; right:10px; top:0; line-height:24px; font-size:12px; font-weight:700; color:#fff; text-shadow:0 1px 2px rgba(0,0,0,.25); }}
    .split {{ display:grid; grid-template-columns:1.05fr .95fr; gap:20px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th {{ text-align:left; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; padding:8px 10px; border-bottom:2px solid var(--line2); }}
    td {{ padding:11px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
    tr:last-child td {{ border-bottom:0; }}
    .status-badge {{ display:inline-flex; align-items:center; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:650; }}
    .badge-ok {{ background:#d1fae5; color:#065f46; }}
    .badge-bad {{ background:#fee2e2; color:#991b1b; }}
    .badge-warn {{ background:#fef3c7; color:#92400e; }}
    .badge-info {{ background:#dbeafe; color:#1e40af; }}
    .badge-muted {{ background:#f1f5f9; color:#475569; }}
    .summary-groups {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
    .summary-group {{ border-radius:5px; padding:12px 14px; }}
    .summary-group.critical {{ background:#fff0f0; border:1px solid #fcd0d0; }}
    .summary-group.warnings {{ background:#fffbea; border:1px solid #f0e08a; }}
    .summary-group.passing {{ background:#f0faf3; border:1px solid #b8e8c8; }}
    .summary-group-label {{ font-size:11px; font-weight:750; text-transform:uppercase; letter-spacing:.07em; margin-bottom:8px; }}
    .summary-group.critical .summary-group-label {{ color:#c0392b; }}
    .summary-group.warnings .summary-group-label {{ color:#856404; }}
    .summary-group.passing .summary-group-label {{ color:#1a6b35; }}
    .summary-group ul {{ list-style:none; padding:0; margin:0; }}
    .summary-group li {{ font-size:13px; color:#333; padding:3px 0; border-bottom:1px solid rgba(0,0,0,.05); line-height:1.45; }}
    .summary-group li:last-child {{ border-bottom:0; }}
    .summary-empty {{ color:#8c94a3; font-style:italic; }}
    .finding {{ display:grid; grid-template-columns:40px minmax(0,1fr); gap:14px; border:1px solid var(--line); border-radius:6px; padding:14px 16px; margin-bottom:12px; background:#fff; }}
    .finding:hover {{ border-color:var(--line2); }}
    .rank {{ width:32px; height:32px; border-radius:50%; display:grid; place-items:center; background:var(--soft2); color:var(--accent); font-weight:800; font-size:14px; }}
    .finding h3 {{ margin:0 0 4px; font-size:14px; }}
    .finding .sev-tag {{ display:inline-block; padding:1px 8px; border-radius:5px; font-size:11px; font-weight:700; color:#fff; vertical-align:middle; }}
    .sev-tag.critical {{ background:#b91c1c; }} .sev-tag.high {{ background:#ea580c; }} .sev-tag.medium {{ background:#d97706; }} .sev-tag.low {{ background:#64748b; }} .sev-tag.informational {{ background:#94a3b8; }}
    .finding .fid {{ color:var(--muted2); font-weight:650; }}
    .finding .scope {{ margin:8px 0 0; font-size:13px; }}
    .finding .scope b {{ color:var(--accent2); }}
    .finding .urls {{ margin-top:8px; }}
    .finding .urls ul {{ margin:6px 0 0; padding-left:18px; font-size:12px; color:var(--muted2); word-break:break-all; }}
    .finding code {{ display:block; white-space:pre-wrap; word-break:break-word; background:var(--soft); border-radius:6px; padding:8px; margin-top:10px; font-size:11px; }}
    .roadmap-cols {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }}
    .roadmap-col h3 {{ font-size:13px; margin:0 0 10px; display:flex; align-items:center; gap:8px; }}
    .roadmap-col .dot {{ width:10px; height:10px; border-radius:50%; }}
    .roadmap-col.now .dot {{ background:#b91c1c; }} .roadmap-col.next .dot {{ background:#d97706; }} .roadmap-col.later .dot {{ background:#64748b; }}
    .mini-card {{ border:1px solid var(--line); border-radius:8px; padding:12px; margin-bottom:10px; }}
    .mini-card h4 {{ margin:0 0 4px; font-size:13px; }} .mini-card p {{ margin:0; font-size:12px; color:var(--muted2); }}
    ul.clean {{ list-style:none; padding:0; margin:0; }}
    ul.clean li {{ border-bottom:1px solid var(--line); padding:12px 0; }}
    ul.clean li:last-child {{ border-bottom:0; }}
    .empty {{ color:var(--muted); padding:12px 0; font-size:13px; }}
    .aeo-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
    .aeo-card {{ border:1px solid var(--line); border-radius:6px; padding:14px; background:#fff; }}
    .aeo-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:10px; }}
    .aeo-head h3 {{ margin:0; font-size:14px; }}
    .aeo-stat {{ color:var(--muted); font-size:12px; white-space:nowrap; }}
    .aeo-stat b {{ color:var(--ink); font-size:18px; }}
    .aeo-score-bar {{ height:8px; border-radius:999px; background:var(--soft2); overflow:hidden; margin-bottom:10px; }}
    .aeo-score-bar .fill {{ height:100%; background:var(--accent); border-radius:999px; }}
    .signal-list {{ list-style:none; padding:0; margin:0; }}
    .signal-list li {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; padding:9px 0; border-bottom:1px solid var(--line); }}
    .signal-list li:last-child {{ border-bottom:0; }}
    .signal-list .name {{ flex:1; font-size:13px; }} .signal-list .name small {{ color:var(--muted); display:block; }}
    @media (max-width: 960px) {{ .layout {{ padding:0 16px; }} .viz-grid,.split,.kpi-row,.roadmap-cols,.aeo-grid,.summary-groups {{ grid-template-columns:1fr; }} svg.radar {{ width:100%; height:auto; }} .decision {{ grid-template-columns:1fr; }} }}
    @media print {{ body {{ background:#fff; }} nav.toc {{ display:none; }} .layout {{ grid-template-columns:1fr; max-width:none; }} main.report {{ box-shadow:none; padding:0 24px; }} .cover {{ break-after:page; }} section.chapter {{ break-inside:avoid; }} .finding,.mini-card {{ break-inside:avoid; }} }}
  </style>
</head>
<body>
<div class="layout">
  <main class="report">
    <header class="cover">
      <p class="kicker">{escape_html(report['report_type'])}</p>
      <div class="cover-body">
      <h1>Website SEO Audit Report</h1>
      <p class="target">{escape_html(report['target'].get('selected', ''))}</p>
      <p class="meta">Audit ID: {escape_html(report['audit_id'])} · Mode: {escape_html(report['mode'])} · {escape_html(report['generated_at'])}</p>
      <div class="cover-score">
        <div class="grade-circle {'na' if score is None else ''}"><b>{escape_html(grade)}</b></div>
        <div class="score-line">
          <b>{escape_html(score_text)}</b>
          <div class="label">{escape_html(report['score_card']['label'])} · {escape_html(_status_label(report['score_card']['status']))}</div>
          <div class="label" style="margin-top:4px">{escape_html(report['score_card']['explanation'])}</div>
        </div>
      </div>
      </div>
    </header>

    <section class="chapter" id="executive">
      <h2 class="section"><span class="num">01</span>Executive Summary</h2>
      <p class="section-sub">Decision summary and key metrics.</p>
      <div class="chapter-body">
      <div class="decision">
        <div>
          <p class="decision-title">Primary Action</p>
          <p class="decision-action">{escape_html(report['executive_decision']['primary_action'])}</p>
          <p class="muted" style="margin-top:8px">Target confidence: {escape_html(report['executive_decision']['target_confidence'])} · Blocked / N/A: {escape_html(str(report['executive_decision']['blocker_count']))}</p>
        </div>
        <div class="grade-circle {'na' if score is None else ''}"><b>{escape_html(grade)}</b></div>
      </div>
      <div class="kpi-row">
        <div class="kpi"><b>{escape_html(report['evidence_coverage']['data_coverage'])}%</b><span>Data Coverage</span></div>
        <div class="kpi"><b>{escape_html(report['evidence_coverage']['confidence'])}</b><span>Confidence</span></div>
        <div class="kpi"><b>{escape_html(str(report['executive_decision']['blocker_count']))}</b><span>Blocked / N/A</span></div>
        <div class="kpi"><b>{escape_html(str(len(report['top_opportunities'])))}</b><span>Priority Actions</span></div>
      </div>
      </div>
    </section>

    <section class="chapter" id="summary">
      <h2 class="section"><span class="num">02</span>Audit Summary</h2>
      <p class="section-sub">Grouped for fast scanning: Critical, Warnings, and Passing signals.</p>
      <div class="chapter-body">
        {summary_groups}
      </div>
    </section>

    <section class="chapter" id="dimensions">
      <h2 class="section"><span class="num">03</span>Dimension Scores</h2>
      <p class="section-sub">SEO Foundation · Content & Answerability · Authority & Entity · Search Performance · AI Visibility · UX & Conversion</p>
      <div class="chapter-body">
      <div class="viz-grid">
        <div>{radar_svg or '<p class="empty">Insufficient dimension data to render a radar chart.</p>'}</div>
        <div>{dim_bars}</div>
      </div>
      </div>
    </section>

    <section class="chapter" id="eligibility">
      <h2 class="section"><span class="num">04</span>Conclusion Eligibility</h2>
      <p class="section-sub">Whether each conclusion type has enough supporting evidence.</p>
      <div class="chapter-body">
      <table><thead><tr><th>Conclusion</th><th>Status</th><th>Basis</th></tr></thead><tbody>{eligibility_rows}</tbody></table>
      </div>
    </section>

    <section class="chapter" id="coverage">
      <h2 class="section"><span class="num">05</span>Evidence Coverage</h2>
      <p class="section-sub">Assessed: {escape_html(assessed)} · N/A: {escape_html(not_assessed)}</p>
      <div class="chapter-body">
      <table><thead><tr><th>Data Source</th><th>Status</th><th>Impact</th></tr></thead><tbody>{coverage_rows}</tbody></table>
      </div>
    </section>

    {browser_section}

    <section class="chapter" id="opportunities">
      <h2 class="section"><span class="num">06</span>Priority Actions</h2>
      <p class="section-sub">Actionable findings are grouped by rule and sorted by impact.</p>
      <div class="chapter-body">
      {top_cards}
      </div>
    </section>

    <section class="chapter" id="roadmap">
      <h2 class="section"><span class="num">07</span>Fix Roadmap</h2>
      <p class="section-sub">Sequenced by priority, evidence strength, and likely effort.</p>
      <div class="chapter-body">
      <div class="roadmap-cols">
        <div class="roadmap-col now"><h3><span class="dot"></span>Now</h3>{roadmap_now}</div>
        <div class="roadmap-col next"><h3><span class="dot"></span>Next</h3>{roadmap_next}</div>
        <div class="roadmap-col later"><h3><span class="dot"></span>Later</h3>{roadmap_later}</div>
      </div>
      </div>
    </section>

    {aeo_geo_section}

    <section class="chapter" id="blocked">
      <h2 class="section"><span class="num">09</span>Blocked / N/A</h2>
      <p class="section-sub">These items are not scored as failures, but they limit what the audit can conclude.</p>
      <div class="chapter-body">
      <ul class="clean">{blocked_items or '<li class="empty">No blocked or N/A items.</li>'}</ul>
      </div>
    </section>

    <section class="chapter" id="limitations">
      <h2 class="section"><span class="num">10</span>Limitations</h2>
      <div class="chapter-body">
      <ul style="padding-left:18px">{limitations or '<li class="empty">None.</li>'}</ul>
      </div>
    </section>

  </main>
</div>
</body>
</html>"""


def _nav_html() -> str:
    items = [
        ("executive", "01 Executive Summary"),
        ("dimensions", "02 Dimension Scores"),
        ("eligibility", "03 Conclusion Eligibility"),
        ("coverage", "04 Evidence Coverage"),
        ("opportunities", "05 Priority Actions"),
        ("roadmap", "06 Fix Roadmap"),
        ("aeo-geo", "07 AEO / GEO"),
        ("blocked", "08 Blocked / N/A"),
        ("limitations", "09 Limitations"),
    ]
    return "\n".join(f'<a href="#{key}">{escape_html(label)}</a>' for key, label in items)


def _summary_groups_html(critical: list[dict], warnings: list[dict], passing: list[dict]) -> str:
    return (
        '<div class="summary-groups">'
        f'{_summary_group_html("critical", "Critical", critical, "None")}'
        f'{_summary_group_html("warnings", "Warnings", warnings, "None")}'
        f'{_summary_group_html("passing", "Passing", passing, "None")}'
        "</div>"
    )


def _summary_group_html(css_class: str, label: str, items: list[dict], empty: str) -> str:
    if items:
        rows = "".join(
            f"<li><strong>{escape_html(item.get('id', ''))}</strong> {escape_html(item.get('title', ''))}</li>"
            for item in items[:8]
        )
    else:
        rows = f'<li class="summary-empty">{escape_html(empty)}</li>'
    return f'<div class="summary-group {css_class}"><div class="summary-group-label">{escape_html(label)}</div><ul>{rows}</ul></div>'


def _source_status_class(status: str) -> str:
    return _status_class(status)


def _eligibility_class(status: str) -> str:
    return _status_class(status)


def _status_label(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    labels = {
        "passed": "Pass",
        "ok": "Pass",
        "eligible": "Pass",
        "ready": "Pass",
        "open": "Pass",
        "captured": "Pass",
        "confirmed": "Pass",
        "browser_authorized_ready": "Pass",
        "failed": "Fail",
        "error": "Fail",
        "blocked": "Fail",
        "wrong_property": "Fail",
        "warning": "Warning",
        "provisional": "Warning",
        "browser_open_needs_export": "Warning",
        "unconfirmed": "Warning",
        "not_assessed": "N/A",
        "not_applicable": "N/A",
        "unavailable": "N/A",
        "not_implemented": "N/A",
        "not_open": "N/A",
        "not_run": "N/A",
        "empty": "N/A",
        "browser_not_ready": "N/A",
        "unknown": "N/A",
        "": "N/A",
    }
    return labels.get(normalized, "N/A")


def _status_class(status: str | None) -> str:
    label = _status_label(status)
    if label == "Pass":
        return "badge-ok"
    if label == "Fail":
        return "badge-bad"
    if label == "Warning":
        return "badge-warn"
    return "badge-muted"


_ELIGIBILITY_LABELS = {
    "crawlability": "Crawlability",
    "indexability": "Indexability",
    "search_performance": "Search Performance",
    "organic_conversion": "Organic Conversion",
    "ai_visibility": "AI Visibility",
    "source_readiness": "Source Readiness",
}


def _eligibility_label(name: str) -> str:
    return _ELIGIBILITY_LABELS.get(name, name.replace("_", " "))


def _eligibility_status_label(status: str) -> str:
    return _status_label(status)


def _dim_label(name: str) -> str:
    return DIMENSION_LABELS.get(name, name.replace("_", " "))


def _aeo_geo_section_html(report: dict) -> str:
    # Read from all_findings so passed signals (e.g. a complete Organization
    # entity) show up too; aggregated_findings only keeps problem items.
    findings = report.get("all_findings", []) or report.get("aggregated_findings", [])
    aeo = [f for f in findings if f.get("id", "").startswith("AEO-")]
    geo = [f for f in findings if f.get("id", "").startswith("GEO-")]
    if not aeo and not geo:
        return ""

    def _summary(items):
        passed = sum(1 for f in items if f.get("status") == "passed")
        total = len(items)
        return passed, total

    aeo_pass, aeo_total = _summary(aeo)
    geo_pass, geo_total = _summary(geo)
    aeo_score = round(aeo_pass / aeo_total * 100) if aeo_total else 0
    geo_score = round(geo_pass / geo_total * 100) if geo_total else 0

    return f"""
    <section class="chapter" id="aeo-geo">
      <h2 class="section"><span class="num">08</span>AEO / GEO Readiness Signals</h2>
      <p class="section-sub">Deterministic answer-engine and generative-engine readiness signals from crawlable page content and structured data.</p>
      <div class="chapter-body">
      <div class="aeo-grid">
        <div class="aeo-card">
          <div class="aeo-head">
            <h3>AEO Answerability</h3>
            <div class="aeo-stat"><b>{aeo_pass}</b>/<span>{aeo_total}</span> Pass</div>
          </div>
          <div class="aeo-score-bar"><div class="fill" style="width:{aeo_score}%"></div></div>
          <ul class="signal-list">{_signal_list_html(aeo)}</ul>
        </div>
        <div class="aeo-card">
          <div class="aeo-head">
            <h3>GEO Entity & AI Readiness</h3>
            <div class="aeo-stat"><b>{geo_pass}</b>/<span>{geo_total}</span> Pass</div>
          </div>
          <div class="aeo-score-bar"><div class="fill" style="width:{geo_score}%"></div></div>
          <ul class="signal-list">{_signal_list_html(geo)}</ul>
        </div>
      </div>
      </div>
    </section>
    """


def _signal_list_html(findings: list) -> str:
    if not findings:
        return '<li class="empty">No signals.</li>'
    # passed first, then warnings, then problems
    order = {"passed": 0, "informational": 1, "warning": 2, "failed": 3, "error": 4, "not_assessed": 5}
    ordered = sorted(findings, key=lambda f: order.get(f.get("status"), 9))
    rows = []
    for f in ordered:
        status = f.get("status")
        badge = _status_class(status)
        label = _status_label(status)
        rec = f.get("recommendation", "")
        rows.append(
            f'<li><div class="name">{escape_html(f.get("id", ""))} · {escape_html(f.get("title", ""))}'
            f'<small>{escape_html(rec)}</small></div>'
            f'<span class="status-badge {badge}">{escape_html(label)}</span></li>'
        )
    return "".join(rows)


def _finding_html(item: dict, index: int) -> str:
    count = item.get("affected_count")
    if count and count > 1:
        scope = f'<p class="scope">Affects <b>{escape_html(str(count))}</b> pages</p>'
        urls = item.get("sample_urls") or []
        if urls:
            url_list = "".join(f"<li>{escape_html(url)}</li>" for url in urls[:10])
            scope += f'<details class="urls"><summary>View affected URLs ({escape_html(str(count))} total)</summary><ul>{url_list}</ul></details>'
    else:
        scope = ""
    severity = item.get("severity", "informational")
    sev_label = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "informational": "Info"}.get(severity, severity)
    return (
        f"<article class=\"finding\">"
        f"<div class=\"rank\">{escape_html(index)}</div>"
        f"<div>"
        f"<h3><span class=\"sev-tag {escape_html(severity)}\">{escape_html(sev_label)}</span> <span class=\"fid\">{escape_html(item['id'])}</span> · {escape_html(item['title'])}</h3>"
        f"<p class=\"muted\">{escape_html(_status_label(item.get('status')))} · {escape_html(item['evidence_type'])} evidence · confidence {escape_html(str(item['confidence']))} · Dimension {escape_html(_dim_label(item.get('dimension','')))}</p>"
        f"<p>{escape_html(item['recommendation'])}</p>"
        f"{scope}"
        f"<code>{escape_html(json.dumps(item['evidence'], ensure_ascii=False))}</code>"
        f"</div>"
        f"</article>"
    )


def _decision_tiles_html(report: dict) -> str:
    crawl = report.get("conclusion_eligibility", {}).get("crawlability", {}).get("status", "unknown")
    score = report.get("score_card", {})
    browser = report.get("browser_capture", {})
    browser_status = browser.get("stage_status", "not_run") if browser else "not_run"
    tiles = [
        ("Public Crawl", crawl, "Public page crawl completed" if crawl == "eligible" else "Public crawl did not complete"),
        ("Score Status", score.get("status", "unknown"), score.get("explanation", "")),
        ("Authorized Browser", browser_status, _browser_stage_label(browser_status)),
    ]
    return "".join(f"<div class=\"tile {_tile_class(status)}\"><strong>{escape_html(title)}</strong><p>{escape_html(_status_label(status))}</p><p class=\"muted\">{escape_html(detail)}</p></div>" for title, status, detail in tiles)


def _browser_capture_html(browser: dict) -> str:
    if not browser:
        return """
    <section class="chapter" id="browser">
      <h2 class="section"><span class="num">Browser</span>Browser Evidence</h2>
      <div class="chapter-body"><p class="empty">The browser evidence stage was not run for this audit.</p></div>
    </section>
"""
    rows = "".join(
        f"<tr><td>{escape_html(item.get('source'))}</td><td><span class=\"status-badge {_status_class(item.get('status'))}\">{escape_html(_status_label(item.get('status')))}</span></td><td>{escape_html(item.get('detail'))}</td></tr>"
        for item in browser.get("status_summary", [])
    )
    if not rows:
        rows = '<tr><td colspan="3" class="empty">No GSC, GA4, or Bing status was detected.</td></tr>'
    return f"""
    <section class="chapter" id="browser">
      <h2 class="section"><span class="num">Browser</span>Browser Evidence</h2>
      <p class="section-sub">Browser: {escape_html(browser.get('browser', ''))} · CDP: {escape_html(browser.get('cdp_url', ''))}</p>
      <div class="chapter-body">
        <table><thead><tr><th>Source</th><th>Status</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table>
      </div>
    </section>
"""


def _browser_stage_label(status: str) -> str:
    labels = {
        "browser_authorized_ready": "A matching authorized property was detected.",
        "browser_open_needs_export": "Authorized tools are open, but export data has not been added to the report.",
        "browser_not_ready": "Authorized browser evidence is not ready.",
        "not_run": "The browser evidence stage was not run.",
    }
    return labels.get(status, status)


def _tile_class(status: str) -> str:
    if status in {"eligible", "ready", "browser_authorized_ready"}:
        return "good"
    if status in {"blocked", "failed", "not_assessed", "browser_not_ready"}:
        return "bad"
    return "warn"


def _compact_finding_html(item: dict) -> str:
    severity = item.get("severity", "informational")
    count = item.get("affected_count")
    scope = f' <span class="mini-count">×{escape_html(str(count))}</span>' if count and count > 1 else ""
    return (
        f"<article class=\"mini-card sev-{escape_html(severity)}\">"
        f'<div class="mini-bar"></div>'
        f"<div class=\"mini-body\">"
        f"<h4>{escape_html(item['id'])}{scope}</h4>"
        f"<p>{escape_html(item['title'])}</p>"
        f'<p class="muted">{escape_html(item.get("recommendation",""))}</p>'
        f"</div>"
        f"</article>"
    )


def render_markdown(audit: dict, findings: list[Finding], scores: dict, adapters: list[AdapterResult]) -> str:
    top = [f for f in sorted(findings, key=lambda x: x.priority_score, reverse=True) if f.status in {"failed", "warning"}][:5]
    lines = [
        f"# Website SEO Audit: {audit['url']}",
        "",
        f"- Audit ID: `{audit['audit_id']}`",
        f"- Mode: `{audit['mode']}`",
        f"- Generated: `{audit['generated_at']}`",
        f"- Overall Score: `{scores['overall_score']}`",
        f"- Data Coverage: `{scores['data_coverage']}%`",
        f"- Confidence: `{scores['confidence']}`",
        "",
        "## Data Sources",
    ]
    for adapter in adapters:
        impact = f" - {adapter.impact}" if adapter.impact else ""
        lines.append(f"- `{adapter.adapter}`: `{adapter.status}`{impact}")
    lines.extend(["", "## Dimension Scores"])
    for dimension, data in scores["dimensions"].items():
        lines.append(f"- `{dimension}`: `{data['score']}` assessed={data['assessed']} unknown={data['unknown']}")
    lines.extend(["", "## Top 5 Critical Opportunities"])
    if not top:
        lines.append("No failed or warning findings were detected in assessed data.")
    for finding in top:
        lines.extend(
            [
                f"### {finding.id}: {finding.title}",
                f"- Severity: `{finding.severity}`",
                f"- Confidence: `{finding.confidence}`",
                f"- URL: `{', '.join(finding.affected_urls)}`",
                f"- Evidence: `{json.dumps(finding.evidence, ensure_ascii=False)}`",
                f"- Recommendation: {finding.recommendation}",
                f"- Validation: {finding.validation.get('expected_result', '')}",
            ]
        )
    lines.extend(["", "## Limitations", "- Quick Scan uses public deterministic checks only and is not a complete SEO/GEO audit."])
    lines.append("- Missing authorized data is marked as not assessed and is not scored as failure.")
    lines.append("- No optimization guarantees rankings, traffic, rich results, or AI citations.")
    return "\n".join(lines)


def render_html(audit: dict, findings: list[Finding], scores: dict, adapters: list[AdapterResult]) -> str:
    top = [f for f in sorted(findings, key=lambda x: x.priority_score, reverse=True) if f.status in {"failed", "warning"}][:20]
    rows = "\n".join(
        "<tr>"
        f"<td>{escape_html(f.id)}</td><td>{escape_html(f.title)}</td><td>{escape_html(f.severity)}</td>"
        f"<td>{escape_html(f.confidence)}</td><td>{escape_html(', '.join(f.affected_urls))}</td>"
        f"<td><code>{escape_html(json.dumps(f.evidence, ensure_ascii=False))}</code></td>"
        f"<td>{escape_html(f.recommendation)}</td><td>{escape_html(f.validation.get('expected_result', ''))}</td>"
        "</tr>"
        for f in top
    )
    adapter_items = "".join(f"<li><strong>{escape_html(a.adapter)}</strong>: {escape_html(a.status)} {escape_html(a.impact)}</li>" for a in adapters)
    dimension_items = "".join(f"<li><strong>{escape_html(k)}</strong>: {escape_html(v['score'])} (assessed: {escape_html(v['assessed'])})</li>" for k, v in scores["dimensions"].items())
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Website SEO Audit</title>
  <link rel="stylesheet" href="../../assets/report.css">
</head>
<body>
  <main>
    <section class="cover">
      <h1>Website SEO Audit</h1>
      <p>{escape_html(audit['url'])}</p>
      <p>Mode: {escape_html(audit['mode'])} | Audit ID: {escape_html(audit['audit_id'])}</p>
    </section>
    <section>
      <h2>Executive Summary</h2>
      <div class="score">{escape_html(scores['overall_score'])}</div>
      <p>Data coverage: {escape_html(scores['data_coverage'])}% | Confidence: {escape_html(scores['confidence'])}</p>
    </section>
    <section><h2>Data Sources</h2><ul>{adapter_items}</ul></section>
    <section><h2>Six Dimension Scores</h2><ul>{dimension_items}</ul></section>
    <section>
      <h2>Page-level Findings</h2>
      <table>
        <thead><tr><th>ID</th><th>Issue</th><th>Severity</th><th>Confidence</th><th>URL</th><th>Evidence</th><th>Fix</th><th>Acceptance</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Limitations</h2>
      <p>Quick Scan is public readiness analysis only. Missing authorized data is not assessed, not treated as failure. This report does not guarantee rankings or AI citations.</p>
    </section>
  </main>
</body>
</html>"""
