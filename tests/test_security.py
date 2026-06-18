import pytest

from search_visibility_auditor import security
from search_visibility_auditor.security import SecurityError, escape_html, redact_secrets, safe_join, validate_public_url


def test_rejects_localhost():
    with pytest.raises(SecurityError):
        validate_public_url("http://localhost:8000")


def test_escapes_html():
    assert escape_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_redacts_secret_like_values():
    assert "REDACTED" in redact_secrets("api_key=abc123456789000")


def test_safe_join_blocks_traversal(tmp_path):
    with pytest.raises(SecurityError):
        safe_join(tmp_path, "..", "escape.txt")


def test_allows_benchmark_proxy_address_when_public_address_exists(monkeypatch):
    monkeypatch.setattr(
        security,
        "resolve_host",
        lambda hostname: [security.ipaddress.ip_address("198.18.0.10"), security.ipaddress.ip_address("2606:4700:4700::1111")],
    )

    assert validate_public_url("https://example.com/path") == "https://example.com/path"


def test_rejects_private_address_even_when_public_address_exists(monkeypatch):
    monkeypatch.setattr(
        security,
        "resolve_host",
        lambda hostname: [security.ipaddress.ip_address("10.0.0.1"), security.ipaddress.ip_address("2606:4700:4700::1111")],
    )

    with pytest.raises(SecurityError):
        validate_public_url("https://example.com/path")
