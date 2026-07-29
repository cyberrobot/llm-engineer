import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import urljoin

import httpx

from assistant.application.ports.website_loader import (
    InvalidWebsiteUrl,
    WebsiteLoader,
    WebsiteLoadError,
    WebsiteTimeoutError,
)
from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.ingestion.url_normaliser import (
    AddressResolver,
    Origin,
    normalise_url,
    origin_for,
    resolve_public_addresses,
    validate_public_url,
)

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
MAX_REDIRECTS = 10


class _PageFailure(RuntimeError):
    pass


class _PageTimeout(_PageFailure):
    pass


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
        client: httpx.Client | None = None,
        resolver: AddressResolver = resolve_public_addresses,
    ) -> None:
        if timeout_seconds <= 0 or max_pages <= 0 or max_response_size <= 0:
            raise ValueError("Website loader limits must be greater than zero.")
        if not user_agent.strip():
            raise ValueError("Website loader user agent must not be empty.")
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._max_pages = max_pages
        self._max_response_size = max_response_size
        self._client = client or httpx.Client(follow_redirects=False)
        self._resolver = resolver

    def load(self, url: str) -> list[WebsiteDocument]:
        root_url = validate_public_url(url, self._resolver)
        started_at = monotonic()
        logger.info("Website crawl started", extra={"root_url": root_url})

        try:
            root_page = self._download(root_url, allowed_origin=None)
        except _PageTimeout as exc:
            self._log_failed_crawl(root_url, started_at)
            raise WebsiteTimeoutError("Website root page request timed out.") from exc
        except (InvalidWebsiteUrl, _PageFailure) as exc:
            self._log_failed_crawl(root_url, started_at)
            raise WebsiteLoadError("Website root page could not be loaded.") from exc

        crawl_origin = origin_for(root_page.url)
        documents = [self._to_document(root_page)]
        loaded_urls = {root_page.url}
        logger.info(
            "Website page loaded",
            extra={"page_url": root_page.url, "status_code": root_page.status_code},
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
                    extra={"page_url": page_url, "reason": type(exc).__name__},
                )
                continue

            if page.url in loaded_urls:
                continue
            seen.add(page.url)
            loaded_urls.add(page.url)
            documents.append(self._to_document(page))
            logger.info(
                "Website page loaded",
                extra={"page_url": page.url, "status_code": page.status_code},
            )
            self._enqueue_links(page, crawl_origin, queue, seen)

        logger.info(
            "Website crawl completed",
            extra={
                "root_url": root_url,
                "pages_loaded": len(documents),
                "pages_skipped": pages_skipped,
                "duration_seconds": monotonic() - started_at,
            },
        )
        return documents

    def _download(self, url: str, *, allowed_origin: Origin | None) -> _DownloadedPage:
        current_url = url
        for _redirect_count in range(MAX_REDIRECTS + 1):
            safe_url = validate_public_url(current_url, self._resolver)
            if allowed_origin is not None and origin_for(safe_url) != allowed_origin:
                raise _PageFailure("Redirect left the crawl origin.")
            try:
                with self._client.stream(
                    "GET",
                    safe_url,
                    headers={
                        "User-Agent": self._user_agent,
                        "Accept": "text/html,application/xhtml+xml",
                    },
                    timeout=self._timeout_seconds,
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise _PageFailure("Redirect response did not include a location.")
                        current_url = normalise_url(urljoin(safe_url, location))
                        continue
                    if not response.is_success:
                        raise _PageFailure(f"Website returned HTTP {response.status_code}.")

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
                        url=str(response.url),
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
            logger.warning("Website link discovery skipped", extra={"page_url": page.url})
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
                extra={"source_url": page.url, "page_url": discovered_url},
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
            extra={"root_url": root_url, "duration_seconds": monotonic() - started_at},
        )
