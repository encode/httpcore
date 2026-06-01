import ssl

import certifi


def _normalize_server_hostname(server_hostname: str | None) -> str | None:
    if server_hostname is None:
        return None

    return server_hostname.rstrip(".")


def default_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(certifi.where())
    return context
