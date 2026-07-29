from dataclasses import dataclass

from assistant.domain import KnowledgeChunk

SYSTEM_PROMPT = """You are a professional business discovery assistant.
Answer using the retrieved knowledge supplied with the question.
Do not invent facts that are absent from the retrieved knowledge.
If the knowledge is insufficient, say so clearly.
Cite supporting passages with their [Source N] label where possible."""


@dataclass(frozen=True, slots=True)
class Prompt:
    system_prompt: str
    user_prompt: str


class PromptBuilder:
    """Build provider-neutral prompts deterministically in one place."""

    def build(self, user_message: str, chunks: list[KnowledgeChunk]) -> Prompt:
        context = self._format_context(chunks)
        return Prompt(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=f"Retrieved knowledge:\n{context}\n\nUser question:\n{user_message.strip()}",
        )

    @staticmethod
    def _format_context(chunks: list[KnowledgeChunk]) -> str:
        if not chunks:
            return "No relevant knowledge was found."
        return "\n\n".join(
            f"[Source {index}: {chunk.document.title}]\n{chunk.content}"
            for index, chunk in enumerate(chunks, start=1)
        )
