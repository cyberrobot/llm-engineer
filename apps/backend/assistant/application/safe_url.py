from urllib.parse import urlsplit


def safe_url_origin(url: str) -> str:
    """Return a log-safe origin without credentials, path, query, or fragment."""
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or parsed.hostname is None:
            return "invalid-source"
        hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        default_port = 80 if parsed.scheme.lower() == "http" else 443
        port = "" if parsed.port in {None, default_port} else f":{parsed.port}"
        return f"{parsed.scheme.lower()}://{hostname.lower()}{port}"
    except ValueError:
        return "invalid-source"
