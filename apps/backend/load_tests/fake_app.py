import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("PUBLIC_ASSISTANT_CHAT_ENABLED", "true")
os.environ.setdefault("PUBLIC_CHAT_ALLOWED_ORIGINS", "http://localhost:5173")
# The controlled harness owns all dependencies and must never touch a configured database.
os.environ["DATABASE_URL"] = ""

from assistant.api.dependencies import (  # noqa: E402
    get_public_chat_protection,
    get_public_chat_service_factory,
)
from assistant.application.public_chat import PublicAssistantChatService  # noqa: E402
from assistant.application.public_chat_protection import PublicChatProtection  # noqa: E402
from assistant.domain import KnowledgeChunk, KnowledgeDocument  # noqa: E402
from assistant.domain.assistant import (  # noqa: E402
    Assistant,
    AssistantStatus,
    AssistantVisibility,
)
from assistant.domain.assistant_repository import AssistantNotFound  # noqa: E402
from core.config import get_public_assistant_chat_settings  # noqa: E402
from infrastructure.ai.providers import AIProvider  # noqa: E402
from main import app  # noqa: E402


class FakeAssistantRepository:
    def __init__(self) -> None:
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        self.item = Assistant(
            uuid4(),
            "redmoor",
            "Redmoor",
            AssistantStatus.active,
            AssistantVisibility.public,
            now,
            now,
        )

    def get_by_slug(self, slug: str) -> Assistant:
        if slug != self.item.slug:
            raise AssistantNotFound("Assistant not found.")
        return self.item

    def get_by_id(self, assistant_id: UUID) -> Assistant:
        if assistant_id != self.item.id:
            raise AssistantNotFound("Assistant not found.")
        return self.item


class FakeProvider(AIProvider):
    @property
    def name(self) -> str:
        return "load-test-fake"

    @property
    def model(self) -> str:
        return "gpt-5.5"

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        raise AssertionError("The load-test provider must use streaming")

    def stream_response(self, **kwargs):
        del kwargs
        first_token_delay = float(os.getenv("LOAD_TEST_FIRST_TOKEN_DELAY_SECONDS", "0.01"))
        token_delay = float(os.getenv("LOAD_TEST_TOKEN_DELAY_SECONDS", "0.005"))
        output_chunks = int(os.getenv("LOAD_TEST_OUTPUT_CHUNKS", "4"))
        failure_after = int(os.getenv("LOAD_TEST_FAILURE_AFTER_CHUNKS", "-1"))
        time.sleep(first_token_delay)
        for index in range(output_chunks):
            if index == failure_after:
                raise RuntimeError("controlled provider failure")
            time.sleep(token_delay)
            yield "controlled "


class FakeRetrievalFactory:
    def __call__(self, assistant_id: UUID):
        del assistant_id

        class Retrieval:
            def retrieve(self, query: str) -> list[KnowledgeChunk]:
                del query
                return [
                    KnowledgeChunk(
                        id="load-test-chunk",
                        document=KnowledgeDocument(id="load-test-document", title="Test"),
                        content="Controlled load-test knowledge only.",
                        score=1.0,
                    )
                ]

        return Retrieval()


def build_service() -> PublicAssistantChatService:
    return PublicAssistantChatService(
        FakeAssistantRepository(),
        FakeRetrievalFactory(),
        FakeProvider(),
        settings=get_public_assistant_chat_settings(),
    )


app.dependency_overrides[get_public_chat_service_factory] = lambda: build_service
load_test_protection = PublicChatProtection.for_tests(get_public_assistant_chat_settings())
app.dependency_overrides[get_public_chat_protection] = lambda: load_test_protection
