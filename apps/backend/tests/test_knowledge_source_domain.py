from datetime import datetime, timezone
from uuid import uuid4

import pytest

from assistant.domain.knowledge_source import (
    MAX_DIRECT_TEXT_CHARACTERS,
    KnowledgeSource,
    KnowledgeSourceType,
)


def test_direct_text_source_is_durable_and_versioned_without_a_public_url():
    source = KnowledgeSource.create(
        assistant_id=uuid4(),
        source_type=KnowledgeSourceType.direct_text,
        name=" Handbook ",
        direct_text="Redmoor policy",
        now=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    assert source.name == "Handbook"
    assert source.url is None
    assert len(source.content_version) == 64


@pytest.mark.parametrize("text", ["", "   ", "x" * (MAX_DIRECT_TEXT_CHARACTERS + 1)])
def test_direct_text_source_rejects_empty_or_oversized_content(text):
    with pytest.raises(ValueError):
        KnowledgeSource.create(
            assistant_id=uuid4(),
            source_type=KnowledgeSourceType.direct_text,
            name="Policy",
            direct_text=text,
        )


def test_url_source_normalizes_and_rejects_credentials():
    source = KnowledgeSource.create(
        assistant_id=uuid4(),
        source_type=KnowledgeSourceType.url,
        name="Site",
        url="HTTPS://Example.COM:443/about",
    )
    assert source.url == "https://example.com/about"
    with pytest.raises(ValueError, match="fragment"):
        KnowledgeSource.create(
            assistant_id=uuid4(),
            source_type=KnowledgeSourceType.url,
            name="Site",
            url="https://example.com/about#team",
        )
    with pytest.raises(ValueError, match="credentials"):
        KnowledgeSource.create(
            assistant_id=uuid4(),
            source_type=KnowledgeSourceType.url,
            name="Site",
            url="https://user:secret@example.com/",
        )
