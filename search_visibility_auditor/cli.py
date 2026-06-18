from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import run_audit
from .browser_cdp import DEFAULT_CDP_URL, DEFAULT_PROFILE_DIR, browser_evidence_findings, ensure_cdp, plan_zero_config_capture
from .compare import compare_scores
from .models import AdapterResult, Finding
from .reporting import build_enterprise_report, render_html_from_report, render_markdown_from_report
from .scoring import score_findings
from .validation import validate_audit_json
from .utils import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="website-seo-audit")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--url")
    audit.add_argument("--source-path")
    audit.add_argument("--github")
    audit.add_argument("--config")
    audit.add_argument("--mode", choices=["quick", "standard", "verified", "full"], default="quick")
    audit.add_argument("--max-pages", type=int, default=50)
    audit.add_argument("--render-js", action="store_true")
    audit.add_argument("--country")
    audit.add_argument("--language")
    audit.add_argument("--format", default="json,markdown,html")
    audit.add_argument("--output", default="reports")
    audit.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    audit.add_argument("--timeout", type=int, default=10)
    audit.add_argument("--concurrency", type=int, default=4)
    audit.add_argument("--baseline")
    audit.add_argument("--verbose", action="store_true")

    audit_zero = sub.add_parser("audit-zero")
    audit_zero.add_argument("--url", required=True)
    audit_zero.add_argument("--source-path")
    audit_zero.add_argument("--github")
    audit_zero.add_argument("--output", default="reports")
    audit_zero.add_argument("--mode", choices=["quick", "standard", "verified", "full"], default="verified")
    audit_zero.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    audit_zero.add_argument("--browser-mode", choices=["launch-once", "attach"], default="launch-once")
    audit_zero.add_argument("--browser-profile", default=DEFAULT_PROFILE_DIR)
    audit_zero.add_argument("--max-pages", type=int, default=50)
    audit_zero.add_argument("--timeout", type=int, default=10)

    compare = sub.add_parser("compare")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--current", required=True)
    compare.add_argument("--output")

    validate = sub.add_parser("validate")
    validate.add_argument("--report", required=True)

    report = sub.add_parser("report")
    report.add_argument("--report", required=True)

    citations = sub.add_parser("citations")
    citations.add_argument("--config")

    history = sub.add_parser("history")
    history.add_argument("--reports", default="reports")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "audit":
        result = run_audit(vars(args))
        report = result["audit"].get("report", {})
        print(
            json.dumps(
                {
                    "report_dir": result["report_dir"],
                    "report_type": report.get("report_type"),
                    "target": report.get("target"),
                    "score_card": report.get("score_card"),
                    "evidence_coverage": report.get("evidence_coverage"),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        if args.fail_on and _has_fail_on(result, args.fail_on):
            return 2
        return 0
    if args.command == "audit-zero":
        result = run_audit(vars(args))
        browser, launched, launch_error = ensure_cdp(args.cdp_url, args.browser_profile, args.browser_mode, target_url=args.url)
        plan = plan_zero_config_capture(browser, args.url, browser_mode=args.browser_mode, launched=launched, launch_error=launch_error)
        report_dir = Path(result["report_dir"])
        evidence_dir = report_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        write_json(evidence_dir / "browser-capture-plan.json", plan)
        report = result["audit"].get("report", {})
        if report:
            browser_findings = browser_evidence_findings(plan.get("extracted_evidence", []), args.url)
            audit_json_path = report_dir / "audit.json"
            audit_json = json.loads(audit_json_path.read_text(encoding="utf-8")) if audit_json_path.exists() else {}
            existing_findings = [_finding_from_dict(item) for item in audit_json.get("findings", [])]
            all_findings = existing_findings + browser_findings
            scores = score_findings(all_findings)
            adapters = _adapter_results_from_audit(audit_json)
            if browser_findings:
                adapters.append(
                    AdapterResult(
                        adapter="authorized_browser",
                        status="ok",
                        reason="cdp_visible_page_capture",
                        impact="GSC/GA4/Bing visible browser evidence was captured without API keys",
                        findings=browser_findings,
                        raw={"browser_capture": plan},
                    )
                )
            audit_for_report = {
                **result["audit"],
                "report_type": "Verified Evidence Audit" if browser_findings else result["audit"].get("report_type"),
                "scores": scores,
                "findings": [finding.to_dict() for finding in all_findings],
                "adapters": [adapter.to_dict() for adapter in adapters],
            }
            report = build_enterprise_report(audit_for_report, all_findings, scores, adapters)
            report["browser_capture"] = plan
            audit_json_path = report_dir / "audit.json"
            report_json_path = report_dir / "report.json"
            if audit_json_path.exists():
                audit_json = json.loads(audit_json_path.read_text(encoding="utf-8"))
                audit_json["scores"] = scores
                audit_json["findings"] = [finding.to_dict() for finding in all_findings]
                audit_json["adapters"] = [adapter.to_dict() for adapter in adapters]
                audit_json["report"] = report
                write_json(audit_json_path, audit_json)
            write_json(report_dir / "findings.json", [finding.to_dict() for finding in all_findings])
            write_json(report_dir / "scores.json", scores)
            write_json(report_json_path, report)
            (report_dir / "audit.md").write_text(render_markdown_from_report(report), encoding="utf-8")
            (report_dir / "audit.html").write_text(render_html_from_report(report), encoding="utf-8")
        print(
            json.dumps(
                {
                    "report_dir": result["report_dir"],
                    "report_type": report.get("report_type"),
                    "score_card": report.get("score_card"),
                    "browser_capture": _browser_capture_summary(plan),
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0
    if args.command == "compare":
        result = compare_scores(Path(args.baseline), Path(args.current), Path(args.output) if args.output else None)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "validate":
        result = validate_audit_json(Path(args.report))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["valid"] else 1
    if args.command == "report":
        print(Path(args.report).read_text(encoding="utf-8"))
        return 0
    if args.command == "citations":
        print(json.dumps({"status": "not_implemented", "reason": "phase_two"}, indent=2))
        return 0
    if args.command == "history":
        reports = sorted(Path(args.reports).glob("*/summary.json"))
        print(json.dumps({"reports": [str(path) for path in reports]}, indent=2))
        return 0
    return 1


def _has_fail_on(result: dict, threshold: str) -> bool:
    order = ["informational", "low", "medium", "high", "critical"]
    min_index = order.index(threshold)
    for adapter in result["adapters"]:
        for finding in adapter.get("findings", []):
            if finding["status"] in {"failed", "warning"} and order.index(finding["severity"]) >= min_index:
                return True
    return False


def _finding_from_dict(data: dict) -> Finding:
    fields = Finding.__dataclass_fields__
    return Finding(**{key: data[key] for key in fields if key in data})


def _adapter_results_from_audit(audit_json: dict) -> list[AdapterResult]:
    adapters = []
    for item in audit_json.get("adapters", []):
        findings = [_finding_from_dict(finding) for finding in item.get("findings", [])]
        adapters.append(
            AdapterResult(
                adapter=item.get("adapter", ""),
                status=item.get("status", ""),
                reason=item.get("reason", ""),
                impact=item.get("impact", ""),
                findings=findings,
                raw=item.get("raw", {}),
            )
        )
    return adapters


def _browser_capture_summary(plan: dict) -> dict:
    return {
        "can_capture_browser_evidence": plan.get("can_capture_browser_evidence"),
        "stage_status": plan.get("stage_status"),
        "status_summary": plan.get("status_summary", []),
        "extracted_evidence": [
            {
                "source": item.get("source"),
                "status": item.get("status"),
                "title": item.get("title"),
                "url": item.get("url"),
                "textLength": item.get("textLength"),
                "signals": item.get("signals", {}),
            }
            for item in plan.get("extracted_evidence", [])
        ],
    }
