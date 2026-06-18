from __future__ import annotations

import hashlib
import os

from ..models import AdapterResult
from .base import Adapter, unavailable


class AICitationsAdapter(Adapter):
    name = "ai_citations"

    def run(self, context: dict) -> AdapterResult:
        if not os.getenv("AI_PROVIDER_API_KEY"):
            return unavailable("ai_citations", "credentials_missing", "AI citation visibility was not assessed")
        records = []
        for query in context.get("queries", []):
            raw_hash = hashlib.sha256(f"{query}|not-run".encode("utf-8")).hexdigest()
            records.append(
                {
                    "provider": "unconfigured",
                    "model": "not-run",
                    "query": query if isinstance(query, str) else query.get("query", ""),
                    "country": context.get("country", ""),
                    "language": context.get("language", ""),
                    "timestamp": "",
                    "brand_mentioned": False,
                    "domain_cited": False,
                    "cited_urls": [],
                    "competitors_mentioned": [],
                    "grounding_type": "unable_to_confirm",
                    "raw_response_hash": raw_hash,
                    "run_id": "",
                }
            )
        return AdapterResult(adapter=self.name, status="not_implemented", reason="phase_two", impact="AI provider execution is not implemented in MVP", raw={"citation_runs": records})

