# Security Policy

## Supported Versions

This project is pre-1.0. Security fixes are applied to the latest main branch until formal release branches exist.

## Reporting a Vulnerability

Please do not open a public issue for sensitive vulnerabilities. Report privately to the repository maintainer when a security contact is available.

Relevant areas include:

- SSRF or unsafe URL fetching.
- Path traversal in report output.
- Secret, cookie, token, credential, or private URL leakage.
- Unsafe HTML rendering in generated reports.

## Security Expectations

The auditor should reject localhost, private, reserved, link-local, and metadata-service targets during public crawling. Reports must redact sensitive values and escape untrusted HTML.
