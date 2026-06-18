# Scoring Methodology

Scores are calculated only from assessed evidence. `not_assessed` findings affect data coverage and confidence, not score penalties.

Default weights:

- SEO Foundation: 25
- Content & Answerability: 20
- Authority & Entity: 15
- Search Performance: 15
- AI Visibility: 15
- UX & Business Outcome: 10

Overall score equals the weighted average of assessed dimensions.

## Score Eligibility

Use score labels that match evidence:

- `readiness_score`: source or public readiness signals are assessed.
- `provisional_readiness_score`: data coverage is 60-79% or public crawl is unavailable.
- `public_visibility_score`: public crawl and live search visibility evidence are assessed.
- `verified_performance_score`: GSC, GA4, CrUX, PageSpeed, logs, or equivalent verified data are assessed.

Do not emit a generic `overall_score` when important requested conclusions are not eligible.

## Coverage Calculation

Track coverage by module:

- Target resolution
- Public crawl
- Technical SEO
- Metadata/canonical
- Structured data
- Content/answerability
- Performance/Core Web Vitals
- Search performance data
- Conversion data
- Authority/backlinks
- AI citation/provider evidence
- Source implementation

Coverage should reflect the modules relevant to the requested report type, not every possible enterprise integration.

## Blocked Evidence

Blocked public crawl, DNS issues, auth walls, robots exclusion, missing credentials, and provider failures reduce coverage and confidence. They do not become score penalties unless the requested audit specifically evaluates configuration readiness and the blocked state is caused by an observed implementation issue.
