from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse


def normalize_url(url: str, base: str | None = None) -> str:
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)
    parsed = urlparse(url if "://" in url else f"https://{url}")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def same_domain(url: str, root: str) -> bool:
    return urlparse(url).hostname == urlparse(root).hostname


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def read_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except Exception:
        data: dict = {}
        stack: list[tuple[int, dict]] = [(-1, data)]
        for raw_line in text.splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            line = raw_line.strip()
            if ":" not in line or line.startswith("- "):
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if value == "":
                parent[key] = {}
                stack.append((indent, parent[key]))
            else:
                parent[key] = value.strip("'\"")
        return data

