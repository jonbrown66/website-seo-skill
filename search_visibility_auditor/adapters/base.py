from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import AdapterResult


class Adapter(ABC):
    name: str

    @abstractmethod
    def run(self, context: dict) -> AdapterResult:
        raise NotImplementedError


def unavailable(adapter: str, reason: str, impact: str) -> AdapterResult:
    return AdapterResult(adapter=adapter, status="unavailable", reason=reason, impact=impact)

