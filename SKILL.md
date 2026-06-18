---
name: website-seo-audit
description: Use when auditing a public website, local project, or existing report for SEO, technical SEO, AEO, GEO, AI search readiness, source readiness, search performance evidence, organic conversion evidence, competitor comparison, or SEO report generation.
---

# Website SEO Audit

Run evidence-based website SEO reviews without overstating what was verified. Classify the input first, run the smallest supported audit, then label conclusions by evidence quality.

## Non-Negotiables

1. Resolve the target before auditing. Do not promote a source-code URL candidate to production unless the user supplied or confirmed it.
2. Collect deterministic facts before model judgment.
3. Mark unavailable integrations as `not_assessed`; never score missing GSC, GA4, PageSpeed, backlinks, logs, AI providers, or public crawl data as failures.
4. Separate readiness from visibility. Titles, schema, `llms.txt`, bot access, and answerable copy are readiness signals, not proof of rankings, traffic, or AI citations.
5. Cite Finding IDs behind every score deduction, recommendation, and fix prompt.
6. Downgrade the report name when crawlability, target identity, or data coverage is weak.
7. Do not promise rankings, rich results, traffic, conversions, or AI citations.
8. Never include secrets, tokens, cookies, private URLs, or credential values in reports.

## Input Triage

| Input | Default output |
| --- | --- |
| Public `http` or `https` URL | Public Quick Scan |
| Local project path | Pre-launch Source Readiness Review |
| GitHub/repository path | Repository Search Readiness Review |
| URL plus source path | Public + Source Search Readiness Audit |
| Authorized exports/API evidence | Verified Search Performance Audit only for supplied evidence |
| Browser-authenticated GSC/GA4/Bing evidence | Verified Evidence Audit only after readable evidence is captured |
| Existing audit/report | Audit Interpretation |
| Unclear input | Ask only the missing question needed to proceed |

## Current Implementation Boundary

The current CLI is a production-oriented MVP. It supports deterministic public/source readiness checks, normalized findings, coverage-aware scoring, report generation, validation, comparison, and zero-config browser evidence capture when CDP can read authorized pages.

Not fully implemented yet: JavaScript rendering, real PageSpeed/CrUX metrics, GSC API, GA4 API, backlinks, server logs, live AI citation providers, competitor crawling, historical storage, and native PDF rendering. If a user asks for those, run the best supported mode and report the module as `not_assessed` unless they provide verified exports that the tool can parse.

## Reference Routing

Load only what the task needs:

| Need | Read |
| --- | --- |
| End-to-end workflow, report names, modes, evidence rules | `references/operating-guide.md` |
| SEO crawl rules, metadata, canonical, sitemap, robots | `references/seo-rules.md` |
| Answerability, featured-answer, FAQ, structured answer checks | `references/aeo-rules.md` |
| GEO, LLM access, AI search readiness, `llms.txt` | `references/geo-rules.md` |
| Evidence status, confidence, adapter degradation | `references/evidence-methodology.md` |
| Score math, dimensions, coverage handling | `references/scoring-methodology.md` |
| AI citation testing and visibility claims | `references/citation-methodology.md` |
| User-facing caveats and report limitations | `references/limitations.md` |

## CLI Workflow

From this repository root:

```bash
python -m search_visibility_auditor audit --url https://example.com --mode quick --max-pages 100 --output ./reports
python -m search_visibility_auditor audit-zero --url https://example.com --source-path ./site --output ./reports
python -m search_visibility_auditor compare --baseline ./reports/a/scores.json --current ./reports/b/scores.json --output ./reports/compare.json
python -m search_visibility_auditor validate --report ./reports/latest/audit.json
```

Supported commands: `audit`, `audit-zero`, `compare`, `validate`, `report`, `citations`, `history`.

When the user asks for a website audit, run `audit` first unless they explicitly ask only for planning, rubric review, or report interpretation. Validate existing reports before drawing conclusions from them.

## Acceptance Checklist

- JSON report validates against the report schema.
- Markdown includes executive decision, status table, conclusion eligibility, priority fixes, blockers, and limitations.
- HTML renders from structured JSON as a compact dashboard.
- Target type, report type, target confidence, coverage, and conclusion eligibility are stated before conclusions.
- Low-coverage reports avoid full-audit language and avoid generic overall-score claims.
- `not_assessed` items affect coverage/confidence, not score penalties.
- Recommendations cite affected URLs or files and explain validation steps.
- Candidate domains are listed when target domain is unconfirmed.
- Secrets and raw credentials are absent from logs and reports.
