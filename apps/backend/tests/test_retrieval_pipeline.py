from uuid import uuid4

from assistant.application.chat import ChatService
from assistant.application.prompt_builder import SYSTEM_PROMPT, PromptBuilder
from assistant.application.retrieval_service import RetrievalService
from assistant.domain import KnowledgeChunk, KnowledgeDocument
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID, DocumentRetrievalState
from assistant.infrastructure.repositories import VectorKnowledgeRepository
from assistant.infrastructure.vector_store import (
    InMemoryVectorEntry,
    InMemoryVectorStore,
    VectorRecord,
)
from assistant.schemas import ChatRequest
from infrastructure.ai.providers import AIProvider


class StubProvider(AIProvider):
    def __init__(self, embedding: list[float] | None = None) -> None:
        self.embedding = embedding or [1.0, 0.0]
        self.embedding_calls: list[str] = []
        self.response_call: tuple[str, str] | None = None

    @property
    def name(self) -> str:
        return "stub"

    @property
    def model(self) -> str:
        return "stub-model"

    def generate_embedding(self, *, text: str) -> list[float]:
        self.embedding_calls.append(text)
        return self.embedding

    def generate_response(self, *, system_prompt: str, user_prompt: str) -> str:
        self.response_call = (system_prompt, user_prompt)
        return "Use workshops to align on outcomes. [Source 1]"


def entry(
    chunk_id: str,
    document_id: str,
    title: str,
    embedding: tuple[float, ...],
) -> InMemoryVectorEntry:
    return InMemoryVectorEntry(
        record=VectorRecord(
            chunk_id=chunk_id,
            document_id=document_id,
            document_title=title,
            content=f"Knowledge from {title}",
            score=0,
        ),
        embedding=embedding,
    )


def test_retrieval_ranks_similar_chunks_and_respects_threshold():
    store = InMemoryVectorStore(
        (
            entry("near", "doc-near", "Near source", (0.9, 0.1)),
            entry("far", "doc-far", "Far source", (0.0, 1.0)),
            entry("exact", "doc-exact", "Exact source", (1.0, 0.0)),
        )
    )
    repository = VectorKnowledgeRepository(store)
    provider = StubProvider([1.0, 0.0])

    chunks = RetrievalService(
        provider,
        repository,
        assistant_id=REDMOOR_ASSISTANT_ID,
        limit=2,
        min_score=0.5,
    ).retrieve(" query ")

    assert provider.embedding_calls == ["query"]
    assert [chunk.id for chunk in chunks] == ["exact", "near"]
    assert chunks[0].score == 1.0


def test_retrieval_returns_empty_for_no_matching_knowledge():
    repository = VectorKnowledgeRepository(
        InMemoryVectorStore((entry("far", "doc", "Far source", (0.0, 1.0)),))
    )

    chunks = RetrievalService(
        StubProvider(), repository, assistant_id=REDMOOR_ASSISTANT_ID, min_score=0.8
    ).retrieve("question")

    assert chunks == []


def test_retrieval_isolates_assistants_and_excludes_disabled_documents():
    other_assistant = uuid4()
    store = InMemoryVectorStore(
        (
            entry("redmoor", "redmoor-doc", "Redmoor", (1.0, 0.0)),
            InMemoryVectorEntry(
                record=entry("other", "other-doc", "Other", (1.0, 0.0)).record,
                embedding=(1.0, 0.0),
                assistant_id=other_assistant,
            ),
            InMemoryVectorEntry(
                record=entry("disabled", "disabled-doc", "Disabled", (1.0, 0.0)).record,
                embedding=(1.0, 0.0),
                retrieval_state=DocumentRetrievalState.disabled,
            ),
        )
    )

    redmoor = RetrievalService(
        StubProvider(),
        VectorKnowledgeRepository(store),
        assistant_id=REDMOOR_ASSISTANT_ID,
        min_score=0.5,
    ).retrieve("question")
    other = RetrievalService(
        StubProvider(),
        VectorKnowledgeRepository(store),
        assistant_id=other_assistant,
        min_score=0.5,
    ).retrieve("question")

    assert [chunk.id for chunk in redmoor] == ["redmoor"]
    assert [chunk.id for chunk in other] == ["other"]


def test_prompt_builder_constructs_deterministic_grounded_prompt():
    chunk = KnowledgeChunk(
        id="chunk-1",
        document=KnowledgeDocument(id="doc-1", title="Discovery guide"),
        content="Workshops align stakeholders.",
        score=0.91,
    )

    prompt = PromptBuilder().build("  How do workshops help?  ", [chunk])

    assert prompt.system_prompt == SYSTEM_PROMPT
    assert prompt.user_prompt == (
        "Retrieved knowledge:\n[Source 1: Discovery guide]\n"
        "Workshops align stakeholders.\n\nUser question:\nHow do workshops help?"
    )


def test_chat_service_retrieves_builds_prompt_and_maps_unique_citations():
    store = InMemoryVectorStore(
        (
            entry("chunk-1", "doc-1", "Discovery guide", (1.0, 0.0)),
            entry("chunk-2", "doc-1", "Discovery guide", (0.9, 0.1)),
        )
    )
    provider = StubProvider()
    retrieval = RetrievalService(
        provider,
        VectorKnowledgeRepository(store),
        assistant_id=REDMOOR_ASSISTANT_ID,
        min_score=0.5,
    )

    response = ChatService(provider, retrieval).chat(ChatRequest(message="How do workshops help?"))

    assert provider.embedding_calls == ["How do workshops help?"]
    assert provider.response_call is not None
    assert "Knowledge from Discovery guide" in provider.response_call[1]
    assert response.message == "Use workshops to align on outcomes. [Source 1]"
    assert [source.model_dump() for source in response.sources] == [
        {"id": "doc-1", "title": "Discovery guide"}
    ]


def test_chat_service_generates_from_supplied_context_without_retrieving_again():
    provider = StubProvider()
    retrieval = RetrievalService(
        provider,
        VectorKnowledgeRepository(InMemoryVectorStore(())),
        assistant_id=REDMOOR_ASSISTANT_ID,
    )
    supplied = [
        KnowledgeChunk(
            id="chunk-1",
            document=KnowledgeDocument(id="doc-1", title="Discovery guide"),
            content="Workshops align stakeholders.",
            score=0.91,
        )
    ]

    response = ChatService(provider, retrieval).generate(
        question="How do workshops help?",
        retrieved_context=supplied,
    )

    assert provider.embedding_calls == []
    assert provider.response_call is not None
    assert "Workshops align stakeholders." in provider.response_call[1]
    assert response.message == "Use workshops to align on outcomes. [Source 1]"
    assert [source.id for source in response.sources] == ["doc-1"]
