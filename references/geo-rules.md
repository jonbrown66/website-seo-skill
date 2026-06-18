# GEO Rules

GEO (Generative Engine Optimization) checks measure whether the page exposes clear entity, authorship, freshness, and metadata signals that generative engines tend to rely on. These are deterministic, parser-based readiness signals parsed from already-fetched HTML and schema. They are NOT proof of AI citation or rankings.

GEO readiness complements `ai_readiness` (llms.txt / bot access) and `ai_citations` (live provider proof). GEO rules map to the `ai_visibility` scoring dimension, source `aeo_geo`.

## Rule set

| Rule | Trigger | Status | Notes |
| --- | --- | --- | --- |
| `GEO-ENTITY-ORG` | `Organization` (or Corporation / LocalBusiness / etc.) schema | `passed` when >= 75% complete (name, url, logo, sameAs), `warning(medium)` otherwise | A complete entity strengthens knowledge-graph disambiguation. |
| `GEO-ENTITY-AUTHOR` | `author` on Article-like schema | `passed` when a named author (Person/Organization) is present, `warning(low)` when an Article exists but has no author | Supports E-E-A-T. |
| `GEO-DATE` | `datePublished` / `dateModified` on schema | `passed` when present, `warning(low)` when an Article exists but has no dates | Freshness signals; keep `dateModified` current on material updates. |
| `GEO-OG-CONSISTENT` | `og:title` / `og:description` present and matching page title/description | `passed` when consistent, `warning(low)` when divergent or absent | Keeps the page coherent when shared or surfaced by AI. |

## Boundary

- GEO readiness is not AI citation proof. A complete Organization entity does not guarantee mention by any LLM.
- Missing `llms.txt`, missing FAQ schema, or a disallowed individual AI bot is `informational`/`low` at most by default, not a critical issue.
- Live provider citation testing (ChatGPT, Perplexity, Google AI Overviews) remains a separate phase-two path via `ai_citations` and requires authorized provider access plus multiple runs before stability claims.
