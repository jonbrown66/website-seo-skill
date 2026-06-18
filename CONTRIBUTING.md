# Contributing

Thanks for improving Website SEO Audit.

## Development Setup

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Contribution Guidelines

- Keep findings evidence-based. Missing integrations should reduce coverage, not score as failures.
- Do not claim rankings, traffic, conversions, Core Web Vitals, backlinks, or AI citations without verified evidence.
- Add or update tests for scoring, validation, report output, security, and crawler behavior when changing those areas.
- Avoid committing generated reports, caches, credentials, or local browser profile data.

## Pull Request Checklist

- Tests pass with `python -m pytest`.
- New report fields validate against the JSON schemas when applicable.
- User-facing report language clearly separates readiness from visibility proof.
- Security-sensitive data is redacted from raw output and reports.
