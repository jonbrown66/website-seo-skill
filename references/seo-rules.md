# SEO Rules

MVP deterministic checks include HTTP status, robots access, sitemap discovery, meta title, meta description, canonical, H1, duplicate title/description, JSON-LD syntax, image alt, and basic content depth.

## Public URL Checks

For a reachable public URL, assess:

- HTTP status and redirect chain.
- Robots access and relevant bot directives.
- Sitemap discovery and sitemap URL validity.
- Title, meta description, canonical, meta robots.
- H1 and heading structure.
- Internal links and obvious broken links.
- JSON-LD syntax and applicable schema types.
- Image alt coverage for indexable pages.
- Basic content depth and first-viewport clarity.

## Local Project Checks

For local or GitHub projects, treat results as implementation readiness, not live SEO proof.

### Next.js App Router

Check:

- `app/layout.*`, nested layouts, route metadata, and `generateMetadata`.
- `app/robots.*`, `app/sitemap.*`, `public/robots.txt`, `public/sitemap.xml`.
- `metadataBase`, canonical, Open Graph URL, Twitter metadata, and `alternates.languages`.
- i18n route config and whether localized URLs have canonical/hreflang strategy.
- JSON-LD components or `application/ld+json` scripts.
- `public/llms.txt`.
- `app/manifest.*` or `public/manifest.json`.
- Public asset size, hero priority images, and large above-the-fold images.
- Build/lint/typecheck output when available.
- Route inventory: public marketing routes, legal routes, authenticated app routes, API routes.

Do not infer live canonical tags, robots behavior, or rendered metadata unless a local or public server was actually rendered and inspected.

## Domain Candidate Rules

When reviewing source, collect but do not automatically trust:

- `metadataBase`
- Open Graph `url`
- canonical metadata
- sitemap host
- robots host
- README production links
- deployment config domains
- visible mockup text that looks like a domain

If candidates conflict, report `target_domain_status: unconfirmed`.
