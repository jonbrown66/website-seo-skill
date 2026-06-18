from __future__ import annotations

from ..crawler import crawl_site
from ..models import AdapterResult
from ..rules import evaluate_pages
from .base import Adapter

DEFAULT_USER_AGENT = "WebsiteSEOAudit/0.1"


class InternalCrawlerAdapter(Adapter):
    name = "internal_crawler"

    def run(self, context: dict) -> AdapterResult:
        pages, robots_meta = crawl_site(
            context["url"],
            max_pages=context.get("max_pages", 50),
            timeout=context.get("timeout", 10),
            user_agent=context.get("user_agent", DEFAULT_USER_AGENT),
            obey_robots=context.get("obey_robots", True),
        )
        findings = evaluate_pages(pages, robots_meta)
        return AdapterResult(
            adapter=self.name,
            status="ok",
            findings=findings,
            raw={"pages": [page.to_dict() for page in pages], "robots": robots_meta},
        )
