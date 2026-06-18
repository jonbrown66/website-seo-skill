from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen
import base64
import hashlib
import json
import os
import socket
import subprocess
import time

from .models import Finding, utc_now


DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_PROFILE_DIR = "E:\\browser-profiles\\website-seo-audit"
EVIDENCE_DESTINATIONS = [
    {"source": "gsc", "url": "https://search.google.com/search-console", "evidence": ["queries", "pages", "countries", "devices"]},
    {"source": "ga4", "url": "https://analytics.google.com/analytics/web/", "evidence": ["landing_pages", "traffic_acquisition"]},
    {"source": "bing_webmaster", "url": "https://www.bing.com/webmasters/", "evidence": ["keywords", "pages", "crawl_issues"]},
]
CHROME_CANDIDATES = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
]


@dataclass
class BrowserAttachResult:
    available: bool
    cdp_url: str
    browser: str
    tabs: list[dict]
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def inspect_cdp(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 1.5) -> BrowserAttachResult:
    cdp_url = cdp_url.rstrip("/")
    try:
        version = _get_json(f"{cdp_url}/json/version", timeout)
        tabs = _get_json(f"{cdp_url}/json/list", timeout)
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return BrowserAttachResult(False, cdp_url, "", [], str(exc))
    return BrowserAttachResult(
        available=True,
        cdp_url=cdp_url,
        browser=str(version.get("Browser", "")),
        tabs=[
            {
                "id": tab.get("id", ""),
                "title": tab.get("title", ""),
                "url": tab.get("url", ""),
                "type": tab.get("type", ""),
                "webSocketDebuggerUrl": tab.get("webSocketDebuggerUrl", ""),
            }
            for tab in tabs
            if tab.get("type") == "page"
        ],
    )


def build_chrome_attach_command(profile_dir: str = DEFAULT_PROFILE_DIR, port: int = 9222) -> str:
    executable = find_chrome_executable() or CHROME_CANDIDATES[0]
    return (
        f'& "{executable}" '
        f"--remote-debugging-port={port} "
        f'--user-data-dir="{profile_dir}"'
    )


def ensure_cdp(
    cdp_url: str = DEFAULT_CDP_URL,
    profile_dir: str = DEFAULT_PROFILE_DIR,
    browser_mode: str = "launch-once",
    target_url: str = "",
    timeout: float = 8.0,
) -> tuple[BrowserAttachResult, bool, str]:
    result = inspect_cdp(cdp_url)
    if result.available or browser_mode == "attach":
        return result, False, ""
    if browser_mode != "launch-once":
        return result, False, f"Unsupported browser mode: {browser_mode}"
    launch_error = launch_fixed_audit_browser(profile_dir, _port_from_cdp_url(cdp_url), target_url=target_url)
    if launch_error:
        return result, False, launch_error
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = inspect_cdp(cdp_url, timeout=1.0)
        if result.available:
            return result, True, ""
        time.sleep(0.25)
    return result, True, result.error or "CDP did not become available after launching the fixed audit browser"


def launch_fixed_audit_browser(profile_dir: str = DEFAULT_PROFILE_DIR, port: int = 9222, target_url: str = "") -> str:
    executable = find_chrome_executable()
    if not executable:
        return "Chrome or Edge executable was not found"
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    args = [
        executable,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    args.extend(launch_urls(target_url))
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return str(exc)
    return ""


def find_chrome_executable() -> str:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return ""


def launch_urls(target_url: str = "") -> list[str]:
    urls = [target_url] if target_url else []
    urls.extend(destination["url"] for destination in EVIDENCE_DESTINATIONS)
    return list(dict.fromkeys(urls))


def profile_health(profile_dir: str = DEFAULT_PROFILE_DIR) -> dict:
    profile = Path(profile_dir)
    cookies = profile / "Default" / "Network" / "Cookies"
    preferences = profile / "Default" / "Preferences"
    return {
        "profile_dir": str(profile),
        "profile_exists": profile.exists(),
        "cookie_store_exists": cookies.exists(),
        "cookie_store_bytes": cookies.stat().st_size if cookies.exists() else 0,
        "cookie_store_updated_at": cookies.stat().st_mtime if cookies.exists() else None,
        "preferences_exists": preferences.exists(),
        "note": "Cookie metadata only; cookie values are never read.",
    }


def plan_zero_config_capture(result: BrowserAttachResult, url: str, browser_mode: str = "launch-once", launched: bool = False, launch_error: str = "") -> dict:
    status_summary = browser_evidence_status(result, url)
    extracted = extract_browser_evidence(result, url)
    return {
        "browser_mode": browser_mode,
        "cdp_url": result.cdp_url,
        "target_url": url,
        "can_capture_browser_evidence": result.available,
        "will_launch_browser": bool(browser_mode == "launch-once" and launched),
        "browser_launch": {
            "attempted": bool(launched),
            "error": launch_error,
            "profile_dir": DEFAULT_PROFILE_DIR,
        },
        "profile_health": profile_health(DEFAULT_PROFILE_DIR),
        "browser": result.browser,
        "tabs": result.tabs,
        "destinations": EVIDENCE_DESTINATIONS,
        "status_summary": status_summary,
        "extracted_evidence": extracted,
        "stage_status": _browser_stage_status(status_summary),
        "required_user_action": "" if result.available else f"Start or inspect the fixed audit browser: {build_chrome_attach_command()}",
        "privacy": {
            "passwords": "never handled by the skill",
            "cookies": "used only by the browser session; not written to reports",
            "downloads": "CSV/JSON evidence should be saved under the audit evidence directory",
        },
    }


def extract_browser_evidence(result: BrowserAttachResult, target_url: str) -> list[dict]:
    if not result.available:
        return []
    captures = []
    for source, needle in [
        ("gsc", "search.google.com/search-console"),
        ("ga4", "analytics.google.com/analytics"),
        ("bing_webmaster", "bing.com/webmasters"),
    ]:
        tab = _find_tab(result.tabs, needle)
        if not tab:
            captures.append({"source": source, "status": "not_open", "reason": "tab_not_found"})
            continue
        capture = capture_visible_page_state(tab)
        capture["source"] = source
        capture["target_url"] = target_url
        captures.append(capture)
    return captures


def capture_visible_page_state(tab: dict, timeout: float = 3.0) -> dict:
    websocket_url = tab.get("webSocketDebuggerUrl", "")
    if not websocket_url:
        return {
            "status": "error",
            "reason": "missing_websocket_debugger_url",
            "url": tab.get("url", ""),
            "title": tab.get("title", ""),
        }
    expression = """
(() => {
  const text = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim();
  const headings = Array.from(document.querySelectorAll('h1,h2,h3')).slice(0, 20).map(el => el.innerText.trim()).filter(Boolean);
  const buttons = Array.from(document.querySelectorAll('button,[role="button"],a')).slice(0, 80).map(el => el.innerText.trim()).filter(Boolean);
  return {
    title: document.title,
    url: location.href,
    textLength: text.length,
    textExcerpt: text.slice(0, 4000),
    headings,
    buttons,
    capturedAt: new Date().toISOString()
  };
})()
"""
    try:
        response = _cdp_request(websocket_url, "Runtime.evaluate", {"expression": expression, "returnByValue": True}, timeout=timeout)
    except (OSError, TimeoutError, ValueError) as exc:
        return {"status": "error", "reason": exc.__class__.__name__, "detail": str(exc), "url": tab.get("url", ""), "title": tab.get("title", "")}
    value = response.get("result", {}).get("result", {}).get("value")
    if not isinstance(value, dict):
        return {"status": "error", "reason": "unexpected_cdp_response", "url": tab.get("url", ""), "title": tab.get("title", "")}
    value["status"] = "captured" if value.get("textLength", 0) > 0 else "empty"
    value["signals"] = _visible_text_signals(str(value.get("textExcerpt", "")))
    return value


def browser_evidence_findings(captures: list[dict], target_url: str) -> list[Finding]:
    findings = []
    for capture in captures:
        if capture.get("status") != "captured":
            continue
        source = capture.get("source", "browser")
        signals = capture.get("signals", {})
        if source == "gsc":
            findings.append(
                _browser_finding(
                    "BROWSER-GSC-001",
                    "Search Console page was captured from the authorized browser",
                    "search_performance",
                    "search_console",
                    target_url,
                    capture,
                    "Use the captured Search Console property as verified browser evidence; export query/page rows for metric-level scoring.",
                    signals,
                )
            )
        elif source == "ga4":
            findings.append(
                _browser_finding(
                    "BROWSER-GA4-001",
                    "GA4 page was captured from the authorized browser",
                    "ux_business_outcome",
                    "analytics",
                    target_url,
                    capture,
                    "Use the captured GA4 property as verified browser evidence; export landing page and acquisition rows for conversion-level scoring.",
                    signals,
                )
            )
        elif source == "bing_webmaster":
            findings.append(
                _browser_finding(
                    "BROWSER-BING-001",
                    "Bing Webmaster Tools page was captured from the authorized browser",
                    "authority_entity",
                    "webmaster_tools",
                    target_url,
                    capture,
                    "Use the captured Bing Webmaster Tools access as verified browser evidence; export keyword/page/crawl issue rows for search-engine-specific scoring.",
                    signals,
                )
            )
    return findings


def browser_evidence_status(result: BrowserAttachResult, target_url: str) -> list[dict]:
    target_origin = _origin(target_url)
    statuses = []
    gsc_tab = _find_tab(result.tabs, "search.google.com/search-console")
    if gsc_tab:
        resource_id = _query_value(gsc_tab.get("url", ""), "resource_id")
        matched = bool(resource_id and _origin(resource_id) == target_origin)
        statuses.append(
            {
                "source": "gsc",
                "status": "ready" if matched else "wrong_property",
                "detail": f"Matched property {resource_id}" if matched else f"Open, but selected property is {resource_id or 'unknown'}",
                "tab_url": gsc_tab.get("url", ""),
            }
        )
    else:
        statuses.append({"source": "gsc", "status": "not_open", "detail": "Search Console tab was not detected", "tab_url": ""})

    ga4_tab = _find_tab(result.tabs, "analytics.google.com/analytics")
    statuses.append(
        {
            "source": "ga4",
            "status": "open" if ga4_tab else "not_open",
            "detail": "Analytics tab detected; property match requires exported data or configured mapping" if ga4_tab else "GA4 tab was not detected",
            "tab_url": ga4_tab.get("url", "") if ga4_tab else "",
        }
    )

    bing_tab = _find_tab(result.tabs, "bing.com/webmasters")
    statuses.append(
        {
            "source": "bing_webmaster",
            "status": "open" if bing_tab else "not_open",
            "detail": "Bing Webmaster tab detected; site match requires exported data or page state extraction" if bing_tab else "Bing Webmaster tab was not detected",
            "tab_url": bing_tab.get("url", "") if bing_tab else "",
        }
    )
    return statuses


def _browser_finding(
    rule_id: str,
    title: str,
    dimension: str,
    category: str,
    target_url: str,
    capture: dict,
    recommendation: str,
    signals: dict,
) -> Finding:
    source = str(capture.get("source", "browser"))
    evidence = {
        "source": source,
        "page_title": capture.get("title", ""),
        "page_url": capture.get("url", ""),
        "text_length": capture.get("textLength", 0),
        "signals": signals,
        "excerpt": capture.get("textExcerpt", "")[:700],
    }
    return Finding(
        id=rule_id,
        rule_version="2.0.0",
        source=f"browser_{source}",
        category=category,
        dimension=dimension,
        title=title,
        status="passed",
        severity="informational",
        confidence=0.75,
        evidence_type="verified",
        affected_urls=[target_url],
        evidence=evidence,
        impact=0,
        effort=1,
        reach=1,
        recommendation=recommendation,
        validation={"method": "CDP Runtime.evaluate on authorized browser tab", "expected_result": "Visible page text is captured and source tab matches the requested data source"},
        fix_prompt="Export the underlying table data from the authorized browser source to enable metric-level scoring.",
        detected_at=utc_now(),
    )


def _visible_text_signals(text: str) -> dict:
    lower = text.lower()
    return {
        "has_clicks": "click" in lower or "点击" in text,
        "has_impressions": "impression" in lower or "展示" in text,
        "has_queries": "quer" in lower or "查询" in text,
        "has_pages": "page" in lower or "网页" in text or "页面" in text,
        "has_users": "user" in lower or "用户" in text,
        "has_sessions": "session" in lower or "会话" in text,
        "has_crawl": "crawl" in lower or "抓取" in text,
    }


def _browser_stage_status(statuses: list[dict]) -> str:
    if any(item["status"] == "ready" for item in statuses):
        return "browser_authorized_ready"
    if any(item["status"] in {"open", "wrong_property"} for item in statuses):
        return "browser_open_needs_export"
    return "browser_not_ready"


def _find_tab(tabs: list[dict], needle: str) -> dict:
    for tab in tabs:
        if needle in tab.get("url", ""):
            return tab
    return {}


def _query_value(url: str, key: str) -> str:
    parsed = urlparse(url)
    return parse_qs(parsed.query).get(key, [""])[0]


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/".lower()


def _cdp_request(websocket_url: str, method: str, params: dict, timeout: float = 3.0) -> dict:
    parsed = urlparse(websocket_url)
    if parsed.scheme != "ws":
        raise ValueError("Only local ws:// CDP endpoints are supported")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        _websocket_handshake(sock, host, port, path)
        payload = json.dumps({"id": 1, "method": method, "params": params}, separators=(",", ":")).encode("utf-8")
        _send_ws_text(sock, payload)
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = _recv_ws_text(sock)
            data = json.loads(message)
            if data.get("id") == 1:
                if "error" in data:
                    raise ValueError(json.dumps(data["error"], ensure_ascii=False))
                return data
    raise TimeoutError(f"CDP method timed out: {method}")


def _websocket_handshake(sock: socket.socket, host: str, port: int, path: str) -> None:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise ValueError("WebSocket handshake failed")
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
    if expected.encode("ascii") not in response:
        raise ValueError("WebSocket accept key mismatch")


def _send_ws_text(sock: socket.socket, payload: bytes) -> None:
    length = len(payload)
    mask = os.urandom(4)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    elif length < 65536:
        header = bytes([0x81, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([0x81, 0x80 | 127]) + length.to_bytes(8, "big")
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    sock.sendall(header + mask + masked)


def _recv_ws_text(sock: socket.socket) -> str:
    first = _recv_exact(sock, 2)
    opcode = first[0] & 0x0F
    length = first[1] & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(sock, 8), "big")
    masked = bool(first[1] & 0x80)
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length)
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    if opcode == 0x8:
        raise ValueError("WebSocket closed")
    if opcode not in {0x1, 0x2}:
        return _recv_ws_text(sock)
    return payload.decode("utf-8")


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ValueError("Socket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
    return f"{parsed.scheme}://{parsed.netloc}/".lower()


def _get_json(url: str, timeout: float) -> object:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _port_from_cdp_url(cdp_url: str) -> int:
    try:
        return int(cdp_url.rstrip("/").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 9222
