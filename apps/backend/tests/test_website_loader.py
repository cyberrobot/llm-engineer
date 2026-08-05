import logging
from collections.abc import Callable
from time import monotonic

import dns.exception
import dns.resolver
import httpx
import pytest

from assistant.application.ports.website_loader import (
    InvalidWebsiteUrl,
    WebsiteLoadError,
    WebsiteTimeoutError,
)
from assistant.infrastructure.ingestion.url_normaliser import resolve_public_addresses
from assistant.infrastructure.ingestion.website_loader import HttpWebsiteLoader

PUBLIC_IPS = ("93.184.216.34",)


def make_loader(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_pages: int = 10,
    max_response_size: int = 1024 * 1024,
) -> HttpWebsiteLoader:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpWebsiteLoader(
        timeout_seconds=2,
        user_agent="website-loader-test/1.0",
        max_pages=max_pages,
        max_response_size=max_response_size,
        client=client,
        resolver=lambda _hostname: PUBLIC_IPS,
    )


def html_response(request: httpx.Request, html: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content=html.encode(),
        request=request,
    )


def test_load_returns_untouched_html_and_metadata_for_valid_website():
    raw_html = "<!doctype html>\n<html><body>  Original &amp; untouched  </body></html>"
    loader = make_loader(lambda request: html_response(request, raw_html))

    documents = loader.load("https://example.com")

    assert len(documents) == 1
    document = documents[0]
    assert document.url == "https://example.com/"
    assert document.status_code == 200
    assert document.content_type == "text/html"
    assert document.html == raw_html
    assert document.title is None
    assert document.retrieved_at.tzinfo is not None


def test_load_follows_safe_redirect_and_uses_final_url():
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(301, headers={"Location": "/docs"}, request=request)
        return html_response(request, "<html>docs</html>")

    documents = make_loader(handler).load("https://example.com")

    assert requested_urls == [
        f"https://{PUBLIC_IPS[0]}/",
        f"https://{PUBLIC_IPS[0]}/docs",
    ]
    assert [document.url for document in documents] == ["https://example.com/docs"]


def test_crawl_removes_fragments_ignores_duplicates_and_unsupported_links():
    requested_urls: list[str] = []
    root = """<html><body>
        <a href="/guide#intro">Guide</a>
        <a href="https://example.com/guide#other">Duplicate guide</a>
        <a href="mailto:help@example.com">Email</a>
        <a href="tel:+441234">Phone</a>
        <a href="javascript:void(0)">Script</a>
    </body></html>"""

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return html_response(request, root if request.url.path == "/" else "<html>guide</html>")

    documents = make_loader(handler).load("https://example.com/#top")

    assert requested_urls == [
        f"https://{PUBLIC_IPS[0]}/",
        f"https://{PUBLIC_IPS[0]}/guide",
    ]
    assert [document.url for document in documents] == [
        "https://example.com/",
        "https://example.com/guide",
    ]


def test_crawl_stays_on_same_origin():
    requested_hosts: list[str] = []
    root = '<a href="/local">Local</a><a href="https://other.example/page">External</a>'

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return html_response(request, root if request.url.path == "/" else "local")

    documents = make_loader(handler).load("https://example.com")

    assert [document.url for document in documents] == [
        "https://example.com/",
        "https://example.com/local",
    ]
    assert requested_hosts == [PUBLIC_IPS[0], PUBLIC_IPS[0]]


def test_crawl_obeys_page_request_limit_deterministically():
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return html_response(request, '<a href="/b">B</a><a href="/a">A</a><a href="/c">C</a>')

    documents = make_loader(handler, max_pages=3).load("https://example.com")

    assert requested_paths == ["/", "/b", "/a"]
    assert [document.url for document in documents] == [
        "https://example.com/",
        "https://example.com/b",
        "https://example.com/a",
    ]


def test_unsupported_child_content_type_is_skipped_and_crawl_continues():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return html_response(request, '<a href="/manual.pdf">PDF</a><a href="/guide">Guide</a>')
        if request.url.path == "/manual.pdf":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/pdf"},
                content=b"%PDF",
                request=request,
            )
        return html_response(request, "<html>guide</html>")

    documents = make_loader(handler).load("https://example.com")

    assert [document.url for document in documents] == [
        "https://example.com/",
        "https://example.com/guide",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "data:text/html,hello",
        "javascript:alert(1)",
        "https://user:secret@example.com/private",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/internal",
        "http://[::1]/admin",
    ],
)
def test_load_rejects_invalid_or_unsafe_root_url_without_requesting(url):
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return html_response(request, "never")

    with pytest.raises(InvalidWebsiteUrl):
        make_loader(handler).load(url)

    assert requests == 0


def test_load_rejects_hostname_resolving_to_private_address_without_requesting():
    requests = 0
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("request must not be sent"))
        )
    )
    loader = HttpWebsiteLoader(
        timeout_seconds=2,
        user_agent="test",
        max_pages=2,
        max_response_size=1024,
        client=client,
        resolver=lambda _hostname: ("192.168.1.20",),
    )

    with pytest.raises(InvalidWebsiteUrl, match="public network address"):
        loader.load("https://internal.example")

    assert requests == 0


def test_timeout_on_root_surfaces_application_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow upstream", request=request)

    with pytest.raises(WebsiteTimeoutError, match="timed out"):
        make_loader(handler).load("https://example.com")


def test_dns_resolution_is_bounded_and_surfaces_timeout(monkeypatch):
    observed_lifetimes: list[float] = []

    def timed_out_resolution(_hostname, _record_type, *, lifetime):
        observed_lifetimes.append(lifetime)
        raise dns.exception.Timeout

    monkeypatch.setattr(dns.resolver, "resolve", timed_out_resolution)
    started = monotonic()

    with pytest.raises(TimeoutError, match="resolution timed out"):
        resolve_public_addresses("example.com", timeout_seconds=0.01)

    assert monotonic() - started < 0.1
    assert 0 < observed_lifetimes[0] <= 0.01


def test_loader_maps_dns_timeout_to_website_timeout():
    loader = HttpWebsiteLoader(
        timeout_seconds=1,
        user_agent="test",
        max_pages=1,
        max_response_size=100,
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: pytest.fail())),
        resolver=lambda _hostname: (_ for _ in ()).throw(TimeoutError()),
    )

    with pytest.raises(WebsiteTimeoutError, match="hostname resolution"):
        loader.load("https://example.com")


def test_failed_child_page_does_not_stop_remaining_crawl():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return html_response(
                request, '<a href="/broken">Broken</a><a href="/working">Working</a>'
            )
        if request.url.path == "/broken":
            return httpx.Response(503, request=request)
        return html_response(request, "<html>working</html>")

    documents = make_loader(handler).load("https://example.com")

    assert [document.url for document in documents] == [
        "https://example.com/",
        "https://example.com/working",
    ]


def test_failed_root_page_fails_the_load():
    loader = make_loader(lambda request: httpx.Response(503, request=request))

    with pytest.raises(WebsiteLoadError, match="root page"):
        loader.load("https://example.com")


def test_oversized_child_response_is_skipped():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return html_response(request, '<a href="/large">Large</a><a href="/small">Small</a>')
        return html_response(request, "x" * 200 if request.url.path == "/large" else "small")

    documents = make_loader(handler, max_response_size=100).load("https://example.com")

    assert [document.url for document in documents] == [
        "https://example.com/",
        "https://example.com/small",
    ]


def test_redirect_to_private_host_is_rejected_before_following():
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1/admin"},
            request=request,
        )

    with pytest.raises(WebsiteLoadError, match="root page"):
        make_loader(handler).load("https://example.com")

    assert requested_urls == [f"https://{PUBLIC_IPS[0]}/"]


def test_request_connects_to_validated_address_with_original_host_and_tls_sni():
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers["Host"]
        observed["sni"] = request.extensions["sni_hostname"]
        return html_response(request, "<html>safe</html>")

    documents = make_loader(handler, max_pages=1).load("https://example.com/docs")

    assert observed == {
        "url": f"https://{PUBLIC_IPS[0]}/docs",
        "host": "example.com",
        "sni": b"example.com",
    }
    assert documents[0].url == "https://example.com/docs"


def test_crawl_emits_structured_lifecycle_logs_without_page_contents(caplog):
    secret_html = '<a href="/guide">TOP-SECRET-CONTENT</a>'
    loader = make_loader(
        lambda request: html_response(request, secret_html if request.url.path == "/" else "guide")
    )

    with caplog.at_level(logging.INFO):
        loader.load("https://example.com")

    messages = [record.getMessage() for record in caplog.records]
    assert "Website crawl started" in messages
    assert "Website page discovered" in messages
    assert messages.count("Website page loaded") == 2
    assert "Website crawl completed" in messages
    assert all("TOP-SECRET-CONTENT" not in message for message in messages)
    completion = next(
        record for record in caplog.records if record.getMessage() == "Website crawl completed"
    )
    assert completion.pages_loaded == 2
    assert completion.pages_skipped == 0
    assert completion.duration_seconds >= 0
