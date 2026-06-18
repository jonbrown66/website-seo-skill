# Limitations

Quick Scan cannot verify real rankings, clicks, impressions, conversions, backlinks, server log crawl evidence, or AI citations. Those require authorized integrations or provider APIs.

## Report Type Limits

- Public Quick Scan cannot verify source implementation details unless source is provided.
- Pre-launch Source Readiness Review cannot verify live crawlability, rendered production HTML, rankings, impressions, clicks, conversions, backlinks, server logs, or AI citations.
- Repository Search Readiness Review cannot verify production behavior unless a deployed URL is provided and reachable.
- Blocked Public Crawl Diagnostic cannot assess public visibility; it can only explain why crawl evidence is missing.

## Target Limits

If the production domain is not explicitly provided or confirmed, reports must say `target_domain_unconfirmed`. Candidate domains from source metadata are not enough by themselves.

## Score Limits

When data coverage is below 80%, score language must be provisional. When below 60%, do not show a single overall score.

## AI Visibility Limits

Schema, `llms.txt`, bot access, and answerable copy are AI readiness signals. They are not evidence of AI citations or AI search visibility without provider testing across multiple prompts and providers.
