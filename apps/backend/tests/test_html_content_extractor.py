from datetime import datetime, timezone
from pathlib import Path

import pytest

from assistant.domain.website_document import WebsiteDocument
from assistant.infrastructure.ingestion.html_content_extractor import HtmlContentExtractor

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "content_processing"
RETRIEVED_AT = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)


def website_document(html: str, *, title: str | None = None) -> WebsiteDocument:
    return WebsiteDocument(
        url="https://example.com/services",
        status_code=200,
        content_type="text/html",
        html=html,
        title=title,
        retrieved_at=RETRIEVED_AT,
    )


def fixture(name: str) -> WebsiteDocument:
    return website_document((FIXTURE_DIR / name).read_text())


def test_extracts_main_content_title_and_semantic_structure_without_boilerplate():
    extracted = HtmlContentExtractor().extract(fixture("business_homepage.html"))

    assert extracted is not None
    assert extracted.title == "Northstar Digital"
    assert extracted.headings == ["Northstar Digital", "What we do"]
    assert extracted.text == (
        "# Northstar Digital\n\n"
        "We help organisations modernise important services.\n\n"
        "## What we do\n\n"
        "- Technical discovery\n"
        "- Reliable software delivery"
    )
    assert extracted.source_url == "https://example.com/services"
    assert extracted.retrieved_at == RETRIEVED_AT
    assert "SCRIPT SECRET" not in extracted.text
    assert "STYLE SECRET" not in extracted.text
    assert "Accept cookies" not in extracted.text
    assert "Copyright" not in extracted.text


def test_extracts_article_lists_blockquote_and_table_text():
    extracted = HtmlContentExtractor().extract(fixture("service_page.html"))

    assert extracted is not None
    assert extracted.title == "AI Integration | Northstar Digital"
    assert "# AI Integration" in extracted.text
    assert "> Useful automation starts with trustworthy knowledge." in extracted.text
    assert "1. Discovery and risk assessment" in extracted.text
    assert "2. Evaluation and controlled rollout" in extracted.text
    assert "Stage | Outcome" in extracted.text
    assert "Discovery | Prioritised use cases" in extracted.text


def test_role_main_is_preferred_and_obvious_navigation_footer_and_overlay_are_excluded():
    extracted = HtmlContentExtractor().extract(fixture("navigation_heavy.html"))

    assert extracted is not None
    assert extracted.title == "Engineering Enablement"
    assert "developer feedback loops" in extracted.text
    assert "customer outcomes" in extracted.text
    assert "Privacy Terms" not in extracted.text
    assert "Subscribe to everything" not in extracted.text


def test_malformed_html_is_processed_deterministically():
    extractor = HtmlContentExtractor()

    first = extractor.extract(fixture("malformed.html"))
    second = extractor.extract(fixture("malformed.html"))

    assert first == second
    assert first is not None
    assert first.title == "Resilient delivery"
    assert "Malformed markup still contains useful customer guidance." in first.text
    assert "- Observe failures" in first.text


@pytest.mark.parametrize("html", ["", "   ", "<html><head></head></html>"])
def test_empty_or_missing_body_returns_none(html):
    assert HtmlContentExtractor().extract(website_document(html)) is None


def test_title_precedence_uses_document_metadata_then_html_title_then_first_h1():
    extractor = HtmlContentExtractor()
    html = "<html><head><title>HTML Title</title></head><body><main><h1>Heading</h1></main></body></html>"

    assert extractor.extract(website_document(html, title=" Loader Title ")).title == "Loader Title"
    assert extractor.extract(website_document(html)).title == "HTML Title"
    assert (
        extractor.extract(website_document("<main><h1>Heading</h1><h1>Other</h1></main>")).title
        == "Heading"
    )


def test_long_or_boilerplate_metadata_title_falls_back_to_meaningful_h1():
    html = (
        '<html><head><meta property="og:title" content="Cookie settings" />'
        f"<title>{'x' * 250}</title></head><body><main><h1>Useful title</h1></main></body></html>"
    )

    assert HtmlContentExtractor().extract(website_document(html)).title == "Useful title"


def test_hidden_content_and_metadata_do_not_leak_into_body():
    html = """
    <html><head><meta property="og:title" content="Visible title"></head><body><main>
      <h1>Visible heading</h1><p>Visible paragraph.</p>
      <p hidden>Tracking value</p><div aria-hidden="true">Hidden modal</div>
      <template>{"analytics": true}</template><svg><text>Chart label</text></svg>
    </main></body></html>
    """

    extracted = HtmlContentExtractor().extract(website_document(html))

    assert extracted is not None
    assert extracted.title == "Visible title"
    assert extracted.text == "# Visible heading\n\nVisible paragraph."
