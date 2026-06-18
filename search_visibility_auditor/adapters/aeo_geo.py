from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from ..crawler import fetch_url, parse_page
from ..models import AdapterResult, Finding, utc_now
from .base import Adapter

# Schema @type values that signal a machine-answerable content shape.
ANSWER_SCHEMA_TYPES = {"FAQPage", "HowTo", "QA", "Question", "Answer", "Article", "BlogPosting", "TechArticle", "BreadcrumbList"}
ENTITY_ORG_TYPES = {"Organization", "Corporation", "LocalBusiness", "NGO", "EducationalOrganization", "GovernmentOrganization"}
ENTITY_AUTHOR_TYPES = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "Recipe", "Person"}
DEFAULT_USER_AGENT = "WebsiteSEOAudit/0.1"


class AEOGeoAdapter(Adapter):
    """Deterministic Answer-Engine Optimization (AEO) and Generative Engine
    Optimization (GEO) readiness checks.

    These are readiness signals parsed from already-fetched HTML/schema. They
    are NOT proof of AI citation or rankings (see references/geo-rules.md).
    AEO findings map to content_answerability; GEO findings map to ai_visibility,
    complementing ai_readiness so those dimensions are genuinely assessed without
    an API key.
    """

    name = "aeo_geo"

    def run(self, context: dict) -> AdapterResult:
        url = context["url"]
        timeout = context.get("timeout", 10)
        user_agent = context.get("user_agent", DEFAULT_USER_AGENT)
        findings: list[Finding] = []
        raw: dict = {}

        try:
            status, final_url, content_type, body = fetch_url(url, user_agent, timeout, max_bytes=2_000_000, retries=0)
        except Exception as exc:
            findings.append(_finding("AEO-FETCH-001", "Homepage could not be fetched for AEO/GEO analysis", "error", "low", url, {"observed": exc.__class__.__name__, "expected": "Fetchable public homepage"}, "Rerun after homepage fetch succeeds.", "content_answerability", confidence=0.5))
            return AdapterResult(adapter=self.name, status="error", reason=exc.__class__.__name__, impact="AEO/GEO readiness could not be assessed", findings=findings, raw={"error": str(exc)})

        page = parse_page(url, status, final_url, content_type, body)
        extra = _ExtraHTMLParser(final_url)
        try:
            extra.feed(body)
        except Exception:
            pass

        schema_objects = _extract_schema(page.schema_blocks)
        raw["schema_types"] = sorted({obj.get("@type") for obj in schema_objects if obj.get("@type")})
        raw["word_count"] = page.word_count
        raw["has_table"] = extra.has_table
        raw["has_list"] = extra.has_list
        raw["has_definition_list"] = extra.has_dl
        raw["faq_headings"] = extra.faq_headings
        raw["paragraph_word_counts"] = extra.paragraph_word_counts[:50]

        _evaluate_aeo(findings, url, page, schema_objects, extra)
        _evaluate_geo(findings, url, page, schema_objects, extra)

        return AdapterResult(adapter=self.name, status="ok", findings=findings, raw=raw)


def _evaluate_aeo(findings: list[Finding], url, page, schema_objects, extra) -> None:
    schema_types = {obj.get("@type") for obj in schema_objects if obj.get("@type")}
    faq_schema = any(t in {"FAQPage", "QA", "Question"} for t in schema_types) or _walk(schema_objects, lambda o: "acceptedAnswer" in o or "suggestedAnswer" in o)
    howto_schema = "HowTo" in schema_types
    if faq_schema or extra.faq_headings:
        findings.append(_finding("AEO-FAQ-001", "Answerable FAQ structure detected", "passed", "informational", url, {"observed": {"faq_schema": faq_schema, "faq_headings": len(extra.faq_headings)}, "expected": "Question + answer blocks for answer engines"}, "Keep FAQ answers concise (40-60 words) and aligned with visible content.", "content_answerability"))
    else:
        findings.append(_finding("AEO-FAQ-001", "No FAQ or Q&A structure detected", "warning", "low", url, {"observed": "none", "expected": "FAQPage schema or question-headed answer blocks where intent is informational"}, "Add FAQPage schema or question + answer blocks for common informational queries.", "content_answerability", confidence=0.75))

    if howto_schema:
        findings.append(_finding("AEO-HOWTO-001", "HowTo structured data detected", "passed", "informational", url, {"observed": "HowTo", "expected": "Step-by-step structured guidance"}, "Keep steps accurate and matching visible content.", "content_answerability"))

    answer_shape = []
    if extra.has_table:
        answer_shape.append("table")
    if extra.has_list:
        answer_shape.append("list")
    if extra.has_dl:
        answer_shape.append("definition_list")
    if answer_shape:
        findings.append(_finding("AEO-STRUCTURE-001", "Structured answer elements detected", "passed", "informational", url, {"observed": answer_shape, "expected": "Tables, lists, or definition lists aid extraction"}, "Keep structured elements accurate and self-explanatory.", "content_answerability"))
    else:
        findings.append(_finding("AEO-STRUCTURE-001", "No structured answer elements detected", "warning", "low", url, {"observed": "none", "expected": "Tables, lists, or definition lists for extractable answers"}, "Add structured elements (tables, ordered lists) for content that has a list or comparison shape.", "content_answerability", confidence=0.7))

    passage_lengths = extra.paragraph_word_counts
    extractable = [n for n in passage_lengths if 40 <= n <= 60]
    if extractable:
        findings.append(_finding("AEO-PASSAGE-001", "Extractable-length passages detected", "passed", "informational", url, {"observed": {"passages_in_range": len(extractable)}, "expected": "40-60 word self-contained passages"}, "Keep answer passages self-contained and factual.", "content_answerability"))
    elif page.word_count >= 100:
        findings.append(_finding("AEO-PASSAGE-001", "Few extractable-length passages", "warning", "low", url, {"observed": {"passages_in_range": 0, "word_count": page.word_count}, "expected": "Some 40-60 word self-contained passages"}, "Add concise self-contained answer paragraphs (40-60 words) for key questions.", "content_answerability", confidence=0.7))

    article_like = any(t in {"Article", "BlogPosting", "NewsArticle", "TechArticle"} for t in schema_types)
    if article_like or answer_schema_present(schema_types):
        findings.append(_finding("AEO-SCHEMA-001", "Answer-relevant schema detected", "passed", "informational", url, {"observed": sorted([t for t in schema_types if t in ANSWER_SCHEMA_TYPES]), "expected": "Article/FAQ/HowTo schema where relevant"}, "Keep schema aligned with visible content.", "content_answerability"))
    elif page.word_count >= 150:
        findings.append(_finding("AEO-SCHEMA-001", "No answer-relevant schema on content pages", "warning", "low", url, {"observed": "none", "expected": "Article/FAQ/HowTo schema where the content warrants it"}, "Add Article/FAQ/HowTo schema where it accurately represents the content.", "content_answerability", confidence=0.7))


def _evaluate_geo(findings: list[Finding], url, page, schema_objects, extra) -> None:
    schema_types = {obj.get("@type") for obj in schema_objects if obj.get("@type")}
    org = _first_of_type(schema_objects, ENTITY_ORG_TYPES)
    if org:
        completeness = _org_completeness(org)
        if completeness["score"] >= 0.75:
            findings.append(_finding("GEO-ENTITY-ORG", "Organization entity is well-defined", "passed", "informational", url, {"observed": completeness["present"], "expected": "Organization with name/url/logo/sameAs"}, "Keep Organization schema accurate and consistent with the knowledge graph.", "ai_visibility"))
        else:
            findings.append(_finding("GEO-ENTITY-ORG", "Organization entity is incomplete", "warning", "medium", url, {"observed": completeness["present"], "missing": completeness["missing"], "expected": "Organization with name/url/logo/sameAs"}, "Complete Organization schema (name, url, logo, sameAs links) to strengthen entity signals.", "ai_visibility", confidence=0.8))
    else:
        findings.append(_finding("GEO-ENTITY-ORG", "No Organization entity detected", "warning", "medium", url, {"observed": "none", "expected": "Organization schema with name/url/logo/sameAs"}, "Add Organization schema with name, url, logo, and sameAs links to build a clear entity.", "ai_visibility", confidence=0.85))

    author = _first_author(schema_objects)
    if author:
        findings.append(_finding("GEO-ENTITY-AUTHOR", "Author attribution detected", "passed", "informational", url, {"observed": author, "expected": "Named author (Person/Organization) for E-E-A-T"}, "Keep author attribution accurate and link to a Person entity where possible.", "ai_visibility"))
    elif _first_of_type(schema_objects, ENTITY_AUTHOR_TYPES):
        findings.append(_finding("GEO-ENTITY-AUTHOR", "Article present but no author", "warning", "low", url, {"observed": "missing", "expected": "Named author for E-E-A-T"}, "Add an author (Person or Organization) to article schema to support E-E-A-T.", "ai_visibility", confidence=0.75))

    dates = _collect_dates(schema_objects)
    if dates:
        findings.append(_finding("GEO-DATE", "Publishing freshness dates detected", "passed", "informational", url, {"observed": dates, "expected": "datePublished/dateModified"}, "Keep dateModified current when content is materially updated.", "ai_visibility"))
    elif _first_of_type(schema_objects, ENTITY_AUTHOR_TYPES):
        findings.append(_finding("GEO-DATE", "Article has no publishing/freshness dates", "warning", "low", url, {"observed": "none", "expected": "datePublished/dateModified"}, "Add datePublished and dateModified to article schema for freshness signals.", "ai_visibility", confidence=0.7))

    og = extra.open_graph
    title_matches = bool(og.get("title")) and _normalize(og["title"]) == _normalize(page.title)
    desc_matches = bool(og.get("description")) and _normalize(og["description"]) == _normalize(page.meta_description)
    if og.get("title") or og.get("description"):
        if title_matches and desc_matches:
            findings.append(_finding("GEO-OG-CONSISTENT", "Open Graph metadata is consistent with page metadata", "passed", "informational", url, {"observed": {"og_title": og.get("title", "")[:60], "og_description": og.get("description", "")[:60]}, "expected": "og:title/og:description aligned with title/description"}, "Keep OG metadata consistent when pages are shared or surfaced by AI.", "ai_visibility"))
        else:
            findings.append(_finding("GEO-OG-CONSISTENT", "Open Graph metadata diverges from page metadata", "warning", "low", url, {"observed": {"title_match": title_matches, "desc_match": desc_matches}, "expected": "og:title/og:description aligned with title/description"}, "Align og:title/og:description with the page title and description so AI/social surfaces stay consistent.", "ai_visibility", confidence=0.7))
    else:
        findings.append(_finding("GEO-OG-CONSISTENT", "No Open Graph metadata detected", "warning", "low", url, {"observed": "none", "expected": "og:title and og:description"}, "Add og:title and og:description so the page surfaces consistently when shared or cited.", "ai_visibility", confidence=0.75))


def answer_schema_present(schema_types: set) -> bool:
    return bool(schema_types & ANSWER_SCHEMA_TYPES)


def _extract_schema(blocks: list[str]) -> list[dict]:
    objects: list[dict] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        objects.extend(_flatten_graph(data))
    return objects


def _flatten_graph(data) -> list[dict]:
    out: list[dict] = []
    if isinstance(data, list):
        for item in data:
            out.extend(_flatten_graph(item))
    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                out.extend(_flatten_graph(item))
        elif data.get("@type"):
            out.append(data)
    return out


def _walk(objects, predicate) -> bool:
    for obj in objects:
        stack = [obj]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                if predicate(current):
                    return True
                stack.extend(v for v in current.values() if isinstance(v, (dict, list)))
            elif isinstance(current, list):
                stack.extend(current)
    return False


def _first_of_type(objects, types: set):
    for obj in objects:
        t = obj.get("@type")
        if isinstance(t, list):
            if any(item in types for item in t):
                return obj
        elif t in types:
            return obj
    return None


def _first_author(objects):
    for obj in objects:
        if obj.get("@type") in ENTITY_AUTHOR_TYPES or "Article" in str(obj.get("@type", "")):
            author = obj.get("author")
            if isinstance(author, dict):
                return author.get("name") or author.get("@type") or "present"
            if isinstance(author, str) and author.strip():
                return author.strip()
    return None


def _org_completeness(org: dict) -> dict:
    fields = {"name", "url", "logo", "sameAs"}
    present = sorted({f for f in fields if org.get(f) not in (None, "", [], {})})
    missing = sorted(fields - set(present))
    return {"present": present, "missing": missing, "score": len(present) / len(fields)}


def _collect_dates(objects) -> dict:
    dates = {}
    for obj in objects:
        for key in ("datePublished", "dateModified"):
            value = obj.get(key)
            if value:
                dates[key] = value
    return dates


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


class _ExtraHTMLParser(HTMLParser):
    """Collect AEO/GEO signals not exposed by the main PageSnapshot parser."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.open_graph: dict[str, str] = {}
        self.has_table = False
        self.has_list = False
        self.has_dl = False
        self.faq_headings: list[str] = []
        self.paragraph_word_counts: list[int] = []
        self._in_p = False
        self._p_text: list[str] = []
        self._heading_text: list[str] = []
        self._heading_tag: str | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            prop = (attrs.get("property") or attrs.get("name") or "").lower()
            if prop.startswith("og:"):
                self.open_graph[prop[3:]] = attrs.get("content", "").strip()
        if tag == "table":
            self.has_table = True
        if tag in {"ul", "ol"}:
            self.has_list = True
        if tag == "dl":
            self.has_dl = True
        if tag == "p":
            self._in_p = True
            self._p_text = []
        if tag in {f"h{i}" for i in range(1, 7)}:
            self._heading_tag = tag
            self._heading_text = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "p" and self._in_p:
            text = " ".join(" ".join(self._p_text).split())
            words = len(text.split())
            if words:
                self.paragraph_word_counts.append(words)
            self._in_p = False
        if self._heading_tag == tag:
            text = " ".join(" ".join(self._heading_text).split())
            if text and ("?" in text or text.lower().startswith(("what ", "how ", "why ", "when ", "where ", "who "))):
                self.faq_headings.append(text)
            self._heading_tag = None

    def handle_data(self, data):
        if self._in_p:
            self._p_text.append(data)
        if self._heading_tag:
            self._heading_text.append(data)


def _finding(rule_id: str, title: str, status: str, severity: str, url: str, evidence: dict, recommendation: str, dimension: str, confidence: float = 1.0) -> Finding:
    impact = {"medium": 3, "low": 2, "informational": 0}.get(severity, 0) if status in {"warning", "error"} else 0
    return Finding(
        id=rule_id,
        rule_version="2.0.0",
        source="aeo_geo",
        category="aeo" if dimension == "content_answerability" else "geo",
        dimension=dimension,
        title=title,
        status=status,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,
        evidence_type="verified",
        affected_urls=[url],
        evidence=evidence,
        impact=impact,
        effort=1,
        reach=1,
        recommendation=recommendation,
        validation={"method": f"Re-run {rule_id}", "expected_result": evidence.get("expected", "")},
        fix_prompt=f"Address {rule_id}: {recommendation}",
        detected_at=utc_now(),
    )
