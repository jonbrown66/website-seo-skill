from search_visibility_auditor.utils import normalize_url


def test_normalize_url_removes_fragment_and_trailing_slash():
    assert normalize_url("HTTPS://Example.COM/path/#frag") == "https://example.com/path"


def test_normalize_url_uses_base():
    assert normalize_url("/pricing#top", "https://example.com/docs") == "https://example.com/pricing"

