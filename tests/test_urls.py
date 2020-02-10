import pytest

from httpcore._url import normalize_url, url_as_bytes


def test_lowercased():
    url = (b"HTTP", b"EXAMPLE.org", 80, b"/")
    url = normalize_url(url)
    assert url == (b"http", b"example.org", 80, b"/")


def test_default_port():
    url = (b"http", b"example.org", 80, b"/")
    assert url_as_bytes(url) == b"http://example.org/"


def test_non_default_port():
    url = (b"http", b"example.org", 81, b"/")
    assert url_as_bytes(url) == b"http://example.org:81/"


# Valid ranges for scheme, hostname.


def test_invalid_scheme():
    url = (b"dummy", b"example.org", 80, b"/")
    with pytest.raises(ValueError):
        normalize_url(url)


def test_invalid_hostname():
    url = (b"http", b"example\xff.org", 80, b"/")
    with pytest.raises(ValueError):
        normalize_url(url)


def test_missing_scheme():
    url = (b"", b"example.org", 80, b"/")
    with pytest.raises(ValueError):
        normalize_url(url)


def test_missing_hostname():
    url = (b"http", b"", 80, b"/")
    with pytest.raises(ValueError):
        normalize_url(url)


# Type checking


def test_scheme_type():
    url = ("http", b"example.org", 80, b"/")
    with pytest.raises(TypeError):
        normalize_url(url)


def test_hostname_type():
    url = (b"http", "example.org", 80, b"/")
    with pytest.raises(TypeError):
        normalize_url(url)


def test_port_type():
    url = (b"http", b"example.org", "80", b"/")
    with pytest.raises(TypeError):
        normalize_url(url)


def test_target_type():
    url = (b"http", b"example.org", 80, "/")
    with pytest.raises(TypeError):
        normalize_url(url)
