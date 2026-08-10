import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import httpx

from assistant.application.ports.website_loader import (
    InvalidWebsiteUrl,
    WebsiteHTTPStatusError,
    WebsiteLoader,
    WebsiteLoadError,
    WebsiteTimeoutError,
)
from assistant.application.safe_url import safe_url_origin
from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.ingestion.url_normaliser import (
    AddressResolver,
    Origin,
    normalise_url,
    origin_for,
    resolve_public_addresses,
    validate_public_url,
    validate_public_url_addresses,
)

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
MAX_REDIRECTS = 10


class _PageFailure(RuntimeError):
    pass


class _PageTimeout(_PageFailure):
    pass


class _PageHTTPStatus(_PageFailure):
    def __init__(self, status_code: int, retry_after: str | None) -> None:
        super().__init__("Website returned an unsuccessful HTTP status.")
        self.status_code = status_code
        self.retry_after = retry_after


class _LinkCollector(HTMLParser):
    """Collect links for traversal without transforming the downloaded document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value is not None:
                self.links.append(value)
                return


@dataclass(frozen=True, slots=True)
class _DownloadedPage:
    url: str
    status_code: int
    content_type: str
    html: str
    retrieved_at: datetime


class HttpWebsiteLoader(WebsiteLoader):
    """Synchronous HTTP loader with bounded, same-origin traversal."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        user_agent: str,
        max_pages: int,
        max_response_size: int,
        max_retries: int = 2,
        client: httpx.Client | None = None,
        resolver: AddressResolver | None = None,
    ) -> None:
        if timeout_seconds <= 0 or max_pages <= 0 or max_response_size <= 0:
            raise ValueError("Website loader limits must be greater than zero.")
        if max_retries < 0:
            raise ValueError("Website loader retries must not be negative.")
        if not user_agent.strip():
            raise ValueError("Website loader user agent must not be empty.")
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._max_pages = max_pages
        self._max_response_size = max_response_size
        self._owns_client = client is None
        self._client = client or httpx.Client(
            follow_redirects=False,
            transport=httpx.HTTPTransport(retries=max_retries),
        )
        self._resolver = resolver or (
            lambda hostname: resolve_public_addresses(
                hostname, timeout_seconds=self._timeout_seconds
            )
        )

    def close(self) -> None:
        """Release the internally owned connection pool; injected clients remain caller-owned."""
        if self._owns_client:
            self._client.close()

    def load(self, url: str) -> list[WebsiteDocument]:
        try:
            root_url = validate_public_url(url, self._resolver)
        except TimeoutError as exc:
            raise WebsiteTimeoutError("Website hostname resolution timed out.") from exc
        started_at = monotonic()
        logger.info("Website crawl started", extra={"root_url": safe_url_origin(root_url)})

        try:
            root_page = self._download(root_url, allowed_origin=None)
        except _PageTimeout as exc:
            self._log_failed_crawl(root_url, started_at)
            raise WebsiteTimeoutError("Website root page request timed out.") from exc
        except _PageHTTPStatus as exc:
            self._log_failed_crawl(root_url, started_at)
            raise WebsiteHTTPStatusError(
                exc.status_code,
                retry_after_seconds=self._parse_retry_after(exc.retry_after),
            ) from exc
        except (InvalidWebsiteUrl, _PageFailure) as exc:
            self._log_failed_crawl(root_url, started_at)
            raise WebsiteLoadError("Website root page could not be loaded.") from exc

        crawl_origin = origin_for(root_page.url)
        documents = [self._to_document(root_page)]
        loaded_urls = {root_page.url}
        logger.info(
            "Website page loaded",
            extra={
                "page_url": safe_url_origin(root_page.url),
                "status_code": root_page.status_code,
            },
        )

        queue: deque[str] = deque()
        seen = {root_page.url}
        self._enqueue_links(root_page, crawl_origin, queue, seen)
        pages_requested = 1
        pages_skipped = 0

        while queue and pages_requested < self._max_pages:
            page_url = queue.popleft()
            pages_requested += 1
            try:
                page = self._download(page_url, allowed_origin=crawl_origin)
            except (InvalidWebsiteUrl, _PageFailure) as exc:
                pages_skipped += 1
                logger.warning(
                    "Website page skipped",
                    extra={
                        "page_url": safe_url_origin(page_url),
                        "reason": type(exc).__name__,
                    },
                )
                continue

            if page.url in loaded_urls:
                continue
            seen.add(page.url)
            loaded_urls.add(page.url)
            documents.append(self._to_document(page))
            logger.info(
                "Website page loaded",
                extra={
                    "page_url": safe_url_origin(page.url),
                    "status_code": page.status_code,
                },
            )
            self._enqueue_links(page, crawl_origin, queue, seen)

        logger.info(
            "Website crawl completed",
            extra={
                "root_url": safe_url_origin(root_url),
                "pages_loaded": len(documents),
                "pages_skipped": pages_skipped,
                "duration_seconds": monotonic() - started_at,
            },
        )
        return documents

    def load_single_page(self, url: str) -> list[WebsiteDocument]:
        """Load exactly the requested page while retaining URL and redirect protections."""
        try:
            root_url = validate_public_url(url, self._resolver)
        except TimeoutError as exc:
            raise WebsiteTimeoutError("Website hostname resolution timed out.") from exc
        try:
            return [self._to_document(self._download(root_url, allowed_origin=None))]
        except _PageTimeout as exc:
            raise WebsiteTimeoutError("Website root page request timed out.") from exc
        except _PageHTTPStatus as exc:
            raise WebsiteHTTPStatusError(
                exc.status_code,
                retry_after_seconds=self._parse_retry_after(exc.retry_after),
            ) from exc
        except (InvalidWebsiteUrl, _PageFailure) as exc:
            raise WebsiteLoadError("Website root page could not be loaded.") from exc

    def _download(self, url: str, *, allowed_origin: Origin | None) -> _DownloadedPage:
        current_url = url
        for _redirect_count in range(MAX_REDIRECTS + 1):
            try:
                safe_url, addresses = validate_public_url_addresses(current_url, self._resolver)
            except TimeoutError as exc:
                raise _PageTimeout("Website hostname resolution timed out.") from exc
            if allowed_origin is not None and origin_for(safe_url) != allowed_origin:
                raise _PageFailure("Redirect left the crawl origin.")
            parsed_safe_url = urlsplit(safe_url)
            if parsed_safe_url.hostname is None:  # Defensive: validation requires a hostname.
                raise _PageFailure("Website URL did not include a hostname.")
            try:
                with self._client.stream(
                    "GET",
                    self._pinned_url(safe_url, addresses[0]),
                    headers={
                        "User-Agent": self._user_agent,
                        "Accept": "text/html,application/xhtml+xml",
                        "Host": parsed_safe_url.netloc,
                        "Connection": "close",
                    },
                    timeout=self._timeout_seconds,
                    extensions={"sni_hostname": parsed_safe_url.hostname.encode("ascii")},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise _PageFailure("Redirect response did not include a location.")
                        current_url = normalise_url(urljoin(safe_url, location))
                        continue
                    if not response.is_success:
                        raise _PageHTTPStatus(
                            response.status_code, response.headers.get("Retry-After")
                        )

                    content_type = (
                        response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    )
                    if content_type not in SUPPORTED_CONTENT_TYPES:
                        raise _PageFailure("Website returned an unsupported content type.")
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            if int(content_length) > self._max_response_size:
                                raise _PageFailure("Website response exceeded the size limit.")
                        except ValueError as exc:
                            raise _PageFailure(
                                "Website returned an invalid content length."
                            ) from exc

                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_response_size:
                            raise _PageFailure("Website response exceeded the size limit.")
                    encoding = response.encoding or "utf-8"
                    try:
                        html = bytes(body).decode(encoding)
                    except (LookupError, UnicodeDecodeError):
                        html = bytes(body).decode("utf-8", errors="replace")
                    return _DownloadedPage(
                        url=safe_url,
                        status_code=response.status_code,
                        content_type=content_type,
                        html=html,
                        retrieved_at=datetime.now(timezone.utc),
                    )
            except httpx.TimeoutException as exc:
                raise _PageTimeout("Website request timed out.") from exc
            except httpx.HTTPError as exc:
                raise _PageFailure("Website request failed.") from exc
        raise _PageFailure("Website exceeded the redirect limit.")

    @staticmethod
    def _pinned_url(url: str, address: str) -> str:
        parsed = urlsplit(url)
        display_address = f"[{address}]" if ":" in address else address
        netloc = display_address if parsed.port is None else f"{display_address}:{parsed.port}"
        return urlunsplit(SplitResult(parsed.scheme, netloc, parsed.path, parsed.query, ""))

    def _enqueue_links(
        self,
        page: _DownloadedPage,
        crawl_origin: Origin,
        queue: deque[str],
        seen: set[str],
    ) -> None:
        parser = _LinkCollector()
        try:
            parser.feed(page.html)
        except (
            Exception
        ):  # HTMLParser can reject malformed declarations; the document remains valid output.
            logger.warning(
                "Website link discovery skipped",
                extra={"page_url": safe_url_origin(page.url)},
            )
            return

        for href in parser.links:
            try:
                discovered_url = normalise_url(href, base_url=page.url)
            except InvalidWebsiteUrl:
                continue
            if origin_for(discovered_url) != crawl_origin or discovered_url in seen:
                continue
            seen.add(discovered_url)
            queue.append(discovered_url)
            logger.info(
                "Website page discovered",
                extra={
                    "source_url": safe_url_origin(page.url),
                    "page_url": safe_url_origin(discovered_url),
                },
            )

    @staticmethod
    def _to_document(page: _DownloadedPage) -> WebsiteDocument:
        return WebsiteDocument(
            url=page.url,
            status_code=page.status_code,
            content_type=page.content_type,
            html=page.html,
            title=None,
            retrieved_at=page.retrieved_at,
        )

    @staticmethod
    def _log_failed_crawl(root_url: str, started_at: float) -> None:
        logger.error(
            "Website crawl failed",
            extra={
                "root_url": safe_url_origin(root_url),
                "duration_seconds": monotonic() - started_at,
            },
        )

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            delay = float(value)
        except ValueError:
            return None
        return delay if delay >= 0 else None
