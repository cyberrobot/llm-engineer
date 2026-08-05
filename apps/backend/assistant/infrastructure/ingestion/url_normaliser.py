import ipaddress
from collections.abc import Callable, Iterable
from time import monotonic
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import dns.exception
import dns.resolver

from assistant.application.ports.website_loader import InvalidWebsiteUrl

AddressResolver = Callable[[str], Iterable[str]]
Origin = tuple[str, str, int]


def resolve_public_addresses(hostname: str, *, timeout_seconds: float = 5) -> tuple[str, ...]:
    """Resolve all addresses for a hostname without making an HTTP request."""
    if timeout_seconds <= 0:
        raise ValueError("DNS resolution timeout must be greater than zero.")
    deadline = monotonic() + timeout_seconds
    addresses: list[str] = []
    for record_type in ("A", "AAAA"):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Website hostname resolution timed out.")
        try:
            answer = dns.resolver.resolve(hostname, record_type, lifetime=remaining)
        except dns.exception.Timeout as exc:
            raise TimeoutError("Website hostname resolution timed out.") from exc
        except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers) as exc:
            raise InvalidWebsiteUrl("Website hostname could not be resolved.") from exc
        except dns.resolver.NoAnswer:
            continue
        addresses.extend(str(item) for item in answer)
    return tuple(dict.fromkeys(addresses))


def normalise_url(url: str, *, base_url: str | None = None) -> str:
    """Return a canonical crawl URL after structural validation."""
    candidate = urljoin(base_url, url) if base_url is not None else url
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise InvalidWebsiteUrl("Website URL is malformed.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidWebsiteUrl("Website URL must use HTTP or HTTPS.")
    if not parsed.hostname:
        raise InvalidWebsiteUrl("Website URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidWebsiteUrl("Website URL must not contain credentials.")

    hostname = parsed.hostname.lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidWebsiteUrl("Website hostname is invalid.") from exc

    default_port = 80 if scheme == "http" else 443
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = display_host if port in {None, default_port} else f"{display_host}:{port}"
    path = parsed.path or "/"
    return urlunsplit(SplitResult(scheme, netloc, path, parsed.query, ""))


def validate_public_url(url: str, resolver: AddressResolver) -> str:
    """Validate the URL and ensure every resolved address is publicly routable."""
    normalised, _addresses = validate_public_url_addresses(url, resolver)
    return normalised


def validate_public_url_addresses(
    url: str, resolver: AddressResolver
) -> tuple[str, tuple[str, ...]]:
    """Return a canonical URL and the exact public addresses validated for connection."""
    normalised = normalise_url(url)
    hostname = urlsplit(normalised).hostname
    if hostname is None:  # Defensive: normalise_url already enforces this.
        raise InvalidWebsiteUrl("Website URL must include a hostname.")

    lowered_hostname = hostname.rstrip(".").lower()
    if lowered_hostname == "localhost" or lowered_hostname.endswith(".localhost"):
        raise InvalidWebsiteUrl("Website URL must resolve to a public network address.")

    addresses: tuple[str, ...]
    try:
        literal_address = ipaddress.ip_address(lowered_hostname)
        addresses = (str(literal_address),)
    except ValueError:
        try:
            addresses = tuple(resolver(lowered_hostname))
        except InvalidWebsiteUrl:
            raise
        except TimeoutError:
            raise
        except (OSError, ValueError) as exc:
            raise InvalidWebsiteUrl("Website hostname could not be resolved.") from exc

    if not addresses:
        raise InvalidWebsiteUrl("Website hostname could not be resolved.")
    try:
        parsed_addresses = tuple(ipaddress.ip_address(address) for address in addresses)
    except ValueError as exc:
        raise InvalidWebsiteUrl("Website hostname resolved to an invalid address.") from exc
    if any(not address.is_global for address in parsed_addresses):
        raise InvalidWebsiteUrl("Website URL must resolve to a public network address.")
    return normalised, tuple(str(address) for address in parsed_addresses)


def origin_for(url: str) -> Origin:
    parsed = urlsplit(url)
    if parsed.hostname is None:
        raise InvalidWebsiteUrl("Website URL must include a hostname.")
    return parsed.scheme, parsed.hostname, parsed.port or (80 if parsed.scheme == "http" else 443)
