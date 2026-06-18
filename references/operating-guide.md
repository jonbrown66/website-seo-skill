# Operating Guide

Use this reference for end-to-end audit routing, mode selection, evidence labels, scoring constraints, browser evidence, report structure, and security rules.

## Core Outcome

Produce a report that a user can act on without overstating what was verified. Every report must make clear:

- What the target is and how confident target identification is.
- What was assessed, what was not assessed, and why.
- Which conclusions are eligible from the evidence.
- Which findings changed scores.
- Which recommendations are supported by verified or inferred evidence.

If the target, data coverage, or crawlability is uncertain, downgrade the report type before writing conclusions.

## Target Resolution Gate

1. Prefer the explicit URL/domain from the user's message.
2. For a local or GitHub project, collect domain candidates from safe sources: deployment config, public base URL keys, canonical metadata, Open Graph URL, sitemap or robots config, README production URL, and package/app metadata.
3. Redact values unless already public and non-secret.
4. If candidates conflict or only localhost/test/mock domains exist, set `target_domain_status: unconfirmed`.
5. If `target_domain_status` is `unconfirmed`, do not run or label a public audit. Run source readiness only and list candidate domains.
6. If DNS resolves to private, reserved, link-local, localhost, or blocked addresses, set public crawl to `not_assessed` and create a blocked-crawl diagnostic finding.

Never silently promote a domain found in source code to the production target when the user provided only a local path or repository.

## Report Type Gate

| Evidence state | Allowed report name |
| --- | --- |
| Public URL reachable and crawl completed | Public Quick Scan |
| Local source only | Pre-launch Source Readiness Review |
| GitHub/repository only | Repository Search Readiness Review |
| Public crawl blocked | Blocked Public Crawl Diagnostic |
| Public URL plus source validation | Public + Source Search Readiness Audit |
| Authorized search/performance data included | Verified Search Performance Audit |
| Browser-exported authorized evidence captured | Verified Evidence Audit |
| AI provider citation evidence captured | AI Visibility / GEO Audit |

If public crawl, rendered HTML, robots, sitemap, live status, or canonical tags are not verified, do not use "full audit", "public visibility score", "ranking", "traffic", or "AI citation visibility" language except as `not_assessed`.

## Audit Modes

Choose the smallest reliable mode:

| Mode | Use | Current boundary |
| --- | --- | --- |
| `source` | Local/GitHub project review | Source, config, route inventory, public assets, selected framework signals |
| `quick` | Public URL checks, launch review, first pass | Public crawl, robots/sitemap discovery, meta, canonical, headings, links, schema syntax, basic content, AI readiness |
| `standard` | Brand/query/competitor interpretation | Quick data plus citation module placeholder; competitor crawling is not implemented |
| `verified` | Authorized performance/search review | Quick/standard plus unavailable GSC/GA4 placeholders unless evidence is captured through browser/export |
| `full` | Program audit request | Highest requested envelope, but PageSpeed, backlinks, logs, and live AI citation providers remain `not_assessed` until implemented |
| `zero` | No-key authorized browser capture | Public/source checks plus CDP-captured GSC, GA4, or Bing page evidence when available |

If a requested mode lacks required data, run the highest supported mode, mark missing modules as `not_assessed`, and explain the limitation in the report.

## Evidence Model

All adapters normalize output into Findings with statuses:

`passed`, `failed`, `warning`, `not_assessed`, `error`

Evidence types:

`verified`, `inferred`, `unknown`

Only `failed` and `warning` reduce scores. `not_assessed` reduces data coverage and confidence, not the score numerator.

Before scoring, deduplicate findings by URL, rule ID, normalized target, and observed value. Preserve separate findings only when they require different fixes or affect different pages.

## Conclusion Eligibility

Every report must include a conclusion eligibility block:

| Conclusion | Eligible when |
| --- | --- |
| Crawlability | Public crawl or rendered local crawl completed |
| Indexability | Crawl plus robots, status, meta robots, canonical assessed |
| Search performance | GSC/CrUX/PageSpeed or equivalent authorized data assessed |
| Organic conversion | GA4/product analytics or equivalent assessed |
| AI visibility | AI provider citation/answer testing assessed across multiple prompts/providers |
| Source readiness | Local/GitHub source inspected |

If a conclusion is not eligible, say `not_assessed` and do not score or imply it.

## Scoring Rules

Default dimensions:

| Dimension | Weight |
| --- | ---: |
| SEO Foundation | 25 |
| Content & Answerability | 20 |
| Authority & Entity | 15 |
| Search Performance | 15 |
| AI Visibility | 15 |
| UX & Business Outcome | 10 |

Overall score:

```text
sum(dimension_score * assessed_weight) / sum(assessed_weight)
```

Always output `data_coverage`, `verified_evidence_ratio`, `inferred_evidence_ratio`, `unknown_ratio`, `confidence`, and `rubric_version`.

Coverage thresholds:

- `data_coverage >= 80%`: full score language is allowed only when evidence supports the requested conclusion type.
- `60% <= data_coverage < 80%`: use provisional readiness score language.
- `data_coverage < 60%`: do not show a single overall score; show a readiness matrix and blockers instead.
- If public crawl fails, public visibility, rankings, AI citations, Core Web Vitals, and traffic must be `not_assessed`.

Use precise score labels: `readiness_score`, `provisional_readiness_score`, `public_visibility_score`, or `verified_performance_score`. Do not use a generic score label in reader-facing copy when evidence is partial.

## Priority Rules

Use deterministic priority before LLM narrative:

```text
priority = severity_weight * impact * confidence * reach / effort
```

Hard rules: all-site `noindex`, robots blocking core pages, persistent core-page `5xx` are critical; wrong canonical, many broken internal links, and schema/content mismatch are high. Missing `llms.txt` is informational or low. Missing FAQ Schema is not a default deduction.

Priority must not override evidence quality. A high-impact hypothesis with inferred or unknown evidence should become a validation task, not a confident fix recommendation.

## Zero-Config Browser Evidence

Use `audit-zero` when the user wants verified evidence without API keys, OAuth setup, service accounts, env files, or YAML configuration.

Hard rule: never open a random browser profile. Use a fixed audit browser profile and CDP endpoint.

```text
CDP endpoint: http://127.0.0.1:9222
Profile: E:\browser-profiles\website-seo-audit
```

Attach workflow:

1. Inspect `http://127.0.0.1:9222/json/version`.
2. If available, attach to the existing fixed audit browser.
3. Reuse existing GSC, GA4, or Bing tabs before opening new tabs.
4. If unavailable and `browser_mode=launch-once`, start the fixed audit browser and open the target URL, GSC, GA4, and Bing Webmaster tabs.
5. If unavailable and `browser_mode=attach`, do not launch Chrome; write a browser capture plan.
6. Browser-exported CSV/JSON evidence goes under `reports/{audit_id}/evidence/`.
7. Cookies, tokens, passwords, and browser profile files must never be copied into reports.

Report browser evidence as `verified` only after the skill captures readable page evidence through CDP or parses downloaded CSV/JSON. A connected browser tab alone is not verified search performance evidence.

When CDP is available, `audit-zero` must do more than list tabs: capture visible page title, URL, text length, text excerpt, headings/buttons, and search/analytics signal flags; convert captured pages into `authorized_browser` findings; recalculate scores and conclusion eligibility.

AI citation provider proof remains separate. If no provider/browser citation test is available, say citation proof is not proven, but do not mark deterministic AI readiness as unassessed when readiness checks ran.

## Local Project Source Checks

For Next.js App Router projects, inspect:

- `app/layout.*`, nested layouts, page-level metadata, and `generateMetadata`
- `app/robots.*`, `app/sitemap.*`, `public/robots.txt`, `public/sitemap.xml`
- canonical and `alternates.languages` for localized routes
- Open Graph and Twitter metadata
- JSON-LD presence, syntax, and schema types
- `public/llms.txt`
- `app/manifest.*` or `public/manifest.json`
- route inventory and indexable vs authenticated routes
- localized messages and first-viewport landing copy
- image sizes, priority images, and public asset weight
- build/lint/typecheck output when available
- rendered HTML only if a local or public server can be safely run

Source findings are implementation readiness signals. They do not prove live crawlability, rankings, impressions, traffic, Core Web Vitals, or AI citations.

## Reporting

Generate machine-readable JSON first when running the CLI, then Markdown and HTML. Reports must include audit scope, target confidence, data coverage, conclusion eligibility, confidence, allowed scores, top opportunities, page-level or source-level findings, fix prompts, methodology, data sources, and limitations.

Markdown must start with a one-sentence decision, then a compact status table, conclusion eligibility, browser/authorized evidence when present, priority fixes, blockers, and limitations.

HTML must render from structured JSON and be readable on first load: executive decision, score/coverage/confidence metrics, decision tiles, browser evidence, top opportunities, roadmap, blockers, limitations, and embedded JSON appendix. Do not produce a large unprioritized table as the primary HTML experience.

Report language must distinguish:

- `verified`: directly observed by crawler, parser, validator, or authorized integration.
- `inferred`: reasoned from available signals and clearly labeled as model judgment.
- `not_assessed`: unavailable because credentials, providers, crawl access, or rendering support were missing.

For local source reviews, use phrases like "implementation readiness", "source signal", and "pre-launch blocker". Do not imply the live site has the same behavior unless rendered live HTML was assessed.

## Security

Before fetching, enforce SSRF protection: allow only `http` and `https`, reject localhost, private IPs, reserved ranges, link-local IPs, cloud metadata addresses, oversized responses, path traversal outputs, and secrets in logs or reports. Respect robots when configured.

Secret safety for local and GitHub projects:

- Read `.env.example` and documented config files when needed.
- Do not read `.env.local`, `.env.production`, `.env`, private key files, or secret-bearing config values by default.
- If secret-bearing files must be inspected, list key names only and redact values.
- Never include API keys, tokens, service role keys, webhook secrets, private URLs, or credential values in reports.
- If a secret is encountered accidentally, stop quoting it and report only that secret exposure risk exists.

## Common Mistakes

| Mistake | Correct behavior |
| --- | --- |
| Treating a local project as a public website | Run Pre-launch Source Readiness Review unless the user provides a production URL |
| Promoting a source-domain candidate to production target | List candidates and set `target_domain_status: unconfirmed` when signals conflict |
| Showing a full overall score when coverage is low | Use provisional readiness score or no single score based on thresholds |
| Treating missing integrations as failures | Mark them `not_assessed` and lower coverage/confidence only |
| Calling readiness evidence visibility proof | Label readiness separately from rankings, traffic, and AI citations |
| Producing narrative before structured data | Generate JSON/findings first, then Markdown/HTML explanation |
| Penalizing every missing schema type | Deduct only when the rule applies to the page and evidence supports it |
| Recommending fixes without Finding IDs | Cite the Finding ID and observed evidence behind each recommendation |
