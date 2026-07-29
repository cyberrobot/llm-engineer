from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """A source of knowledge available to the Assistant."""

    id: str
    title: str
    source_uri: str | None = None
