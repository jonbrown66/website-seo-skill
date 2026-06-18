from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

BLOCKED_HOSTS = {"localhost", "0.0.0.0", "127.0.0.1", "::1"}
METADATA_IPS = {ipaddress.ip_address("169.254.169.254")}
BENCHMARK_NETS = (ipaddress.ip_network("198.18.0.0/15"),)
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s<]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
]


class SecurityError(ValueError):
    pass


def validate_public_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in {"http", "https"}:
        raise SecurityError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise SecurityError("URL must include a hostname")
    hostname = parsed.hostname.lower()
    if hostname in BLOCKED_HOSTS or hostname.endswith(".localhost"):
        raise SecurityError("Localhost targets are not allowed")
    addresses = resolve_host(hostname)
    blocked = [address for address in addresses if is_blocked_ip(address)]
    public = [address for address in addresses if not is_blocked_ip(address)]
    benchmark_only_blocked = blocked and all(is_benchmark_ip(address) for address in blocked)
    if blocked and not (public and benchmark_only_blocked):
        raise SecurityError(f"Blocked non-public address: {blocked[0]}")
    return parsed.geturl()


def resolve_host(hostname: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SecurityError(f"Unable to resolve host: {hostname}") from exc
    addresses: list[ipaddress._BaseAddress] = []
    for info in infos:
        addresses.append(ipaddress.ip_address(info[4][0]))
    return addresses


def is_blocked_ip(address: ipaddress._BaseAddress) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or address in METADATA_IPS
    )


def is_benchmark_ip(address: ipaddress._BaseAddress) -> bool:
    return any(address in network for network in BENCHMARK_NETS)


def safe_join(base: Path, *parts: str) -> Path:
    resolved_base = base.resolve()
    target = resolved_base.joinpath(*parts).resolve()
    if resolved_base != target and resolved_base not in target.parents:
        raise SecurityError("Output path escapes base directory")
    return target


def escape_html(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def redact_secrets(value: object) -> object:
    if isinstance(value, dict):
        return {key: redact_secrets(val) for key, val in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda m: m.group(0).split("=", 1)[0] + "=REDACTED" if "=" in m.group(0) else "REDACTED", redacted)
    for _, env_value in os.environ.items():
        if env_value and len(env_value) >= 12:
            redacted = redacted.replace(env_value, "REDACTED")
    return redacted
