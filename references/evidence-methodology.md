# Evidence Methodology

Every failed or warning Finding must include URL, rule ID, observed value, expected value, source, timestamp, confidence, and rule version.

Evidence types:

- `verified`: directly measured by code or authorized API.
- `inferred`: judgment based on measured facts.
- `unknown`: unavailable or not configured.

## Target Evidence

Before auditing, record:

- `input_source`: `public_url`, `local_project`, `github_repo`, `public_url_plus_source`, `verified_data`, `report_only`, or `unknown`.
- `target_domain_status`: `confirmed`, `candidate`, `conflicting`, `unconfirmed`, or `blocked`.
- `target_candidates`: public URLs found in user input, deploy config, metadata, sitemap, robots, README, or app metadata.
- `selected_target`: the URL or path actually assessed.

Only the user's explicit URL is automatically `confirmed`. Domains found in source code are candidates until they are consistent across source signals or confirmed by the user.

## Conclusion Eligibility

Use `eligible`, `not_assessed`, or `blocked` for each conclusion:

| Conclusion | Required evidence |
| --- | --- |
| Crawlability | Public or rendered local crawl completed |
| Indexability | Crawl plus status, robots, meta robots, canonical assessed |
| Search performance | GSC, CrUX, PageSpeed, or equivalent authorized data |
| Organic conversion | GA4/product analytics or equivalent authorized data |
| AI visibility | Multi-prompt/provider AI citation or answer testing |
| Source readiness | Local/GitHub source inspected |

If eligibility is `not_assessed` or `blocked`, do not score that conclusion.

## Coverage Thresholds

Coverage controls score language:

- `>= 80%`: full score is allowed.
- `60% - 79%`: only provisional readiness score is allowed.
- `< 60%`: do not show an overall score; show a readiness matrix and blockers.

When public crawl is blocked, public visibility, rankings, AI citations, Core Web Vitals, and traffic must be `not_assessed`.

## Main Body vs Appendix

Main body should emphasize verified and inferred actionable findings. Put broad unavailable integrations in data coverage or appendix unless they block the requested audit.
