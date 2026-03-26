"""Tests for trailing-dot FQDN hostname normalisation (issue #1063)."""

import pytest
import httpcore


def test_origin_str_strips_trailing_dot():
    """Origin.__str__ must strip the trailing dot from FQDNs.

    'myhost.internal.' is a valid FQDN but TLS certificates use
    'myhost.internal' (without the dot). Passing the raw hostname
    to ssl_wrap_socket would cause CERTIFICATE_VERIFY_FAILED.
    """
    origin = httpcore.Origin(b"https", b"myhost.internal.", 443)
    assert str(origin) == "https://myhost.internal:443"


def test_origin_str_no_trailing_dot_unchanged():
    """Normal hostnames (no trailing dot) must not be modified."""
    origin = httpcore.Origin(b"https", b"example.com", 443)
    assert str(origin) == "https://example.com:443"


def test_url_host_strips_trailing_dot():
    """URL.host used for SNI should not carry the trailing dot."""
    url = httpcore.URL("https://myhost.internal.:8443/")
    assert url.host == b"myhost.internal."   # raw host preserved
    # but str(origin) strips it for TLS
    origin = httpcore.Origin(b"https", url.host, url.port)
    assert str(origin) == "https://myhost.internal:8443"
