from assistant.application.prompt_builder import SYSTEM_PROMPT, PromptBuilder
from assistant.application.retrieval_service import RetrievalService
from assistant.domain import Citation, KnowledgeChunk
from assistant.schemas import ChatRequest, ChatResponse, SourceReference
from infrastructure.ai.providers import AIProvider

__all__ = ["ChatService", "SYSTEM_PROMPT"]


class ChatService:
    """Handle Assistant chat requests."""

    def __init__(
        self,
        ai_provider: AIProvider,
        retrieval_service: RetrievalService | None = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        self._ai_provider = ai_provider
        self._retrieval_service = retrieval_service
        self._prompt_builder = prompt_builder or PromptBuilder()

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Validate and orchestrate a single stateless Assistant response."""
        user_prompt = request.message.strip()
        if not user_prompt:
            raise ValueError("Chat message must not be empty")

        chunks = self._retrieval_service.retrieve(user_prompt) if self._retrieval_service else []
        return self.generate(question=user_prompt, retrieved_context=chunks)

    def generate(
        self,
        *,
        question: str,
        retrieved_context: list[KnowledgeChunk],
    ) -> ChatResponse:
        """Generate a grounded response from already-retrieved production context."""

        user_prompt = question.strip()
        if not user_prompt:
            raise ValueError("Chat message must not be empty")
        prompt = self._prompt_builder.build(user_prompt, retrieved_context)
        message = self._ai_provider.generate_response(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
        )
        return ChatResponse(
            message=message,
            sources=self._map_sources(retrieved_context),
        )

    @staticmethod
    def _map_sources(chunks: list[KnowledgeChunk]) -> list[SourceReference]:
        sources: list[SourceReference] = []
        seen_documents: set[str] = set()
        for chunk in chunks:
            citation = Citation.from_chunk(chunk)
            if citation.document_id in seen_documents:
                continue
            seen_documents.add(citation.document_id)
            sources.append(SourceReference(id=citation.document_id, title=citation.title))
        return sources
