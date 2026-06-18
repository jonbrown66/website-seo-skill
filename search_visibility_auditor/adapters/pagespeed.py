from __future__ import annotations

import os

from ..models import AdapterResult, Finding
from .base import Adapter, unavailable


class PageSpeedAdapter(Adapter):
    name = "pagespeed"

    def run(self, context: dict) -> AdapterResult:
        if not os.getenv("PAGESPEED_API_KEY"):
            return unavailable("pagespeed", "credentials_missing", "Performance and Core Web Vitals were not assessed")
        return AdapterResult(
            adapter=self.name,
            status="not_implemented",
            reason="phase_two",
            impact="PageSpeed integration is declared but not implemented in MVP",
            findings=[
                Finding(
                    id="UX-PERF-001",
                    rule_version="1.0.0",
                    source="pagespeed",
                    category="performance",
                    dimension="ux_business_outcome",
                    title="PageSpeed integration is not implemented in MVP",
                    status="not_assessed",
                    severity="informational",
                    confidence=1.0,
                    evidence_type="unknown",
                    affected_urls=[context["url"]],
                    evidence={"observed": "adapter not implemented", "expected": "authorized PageSpeed/CrUX data"},
                    impact=0,
                    effort=1,
                    reach=1,
                    recommendation="Enable phase-two PageSpeed adapter before making Core Web Vitals claims.",
                    validation={"method": "Run adapter with valid API key", "expected_result": "Performance metrics captured"},
                )
            ],
        )

