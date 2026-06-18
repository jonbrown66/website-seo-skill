from __future__ import annotations

import json
from pathlib import Path

from .utils import write_json


def compare_scores(baseline: Path, current: Path, output: Path | None = None) -> dict:
    before = json.loads(baseline.read_text(encoding="utf-8"))
    after = json.loads(current.read_text(encoding="utf-8"))
    result = {
        "baseline": str(baseline),
        "current": str(current),
        "overall_delta": _delta(before.get("overall_score"), after.get("overall_score")),
        "data_coverage_delta": _delta(before.get("data_coverage"), after.get("data_coverage")),
        "dimension_deltas": {},
    }
    for dimension, before_data in before.get("dimensions", {}).items():
        after_data = after.get("dimensions", {}).get(dimension, {})
        result["dimension_deltas"][dimension] = _delta(before_data.get("score"), after_data.get("score"))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, result)
    return result


def _delta(a, b):
    if a is None or b is None:
        return None
    return round(float(b) - float(a), 2)

