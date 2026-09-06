from pydantic import BaseModel, Field


class RagChatRequest(BaseModel):
    message: str = Field(max_length=4000)
    user_role: str | None = None


class RagChatResponse(BaseModel):
    reply: dict
    sources: list[dict]
    evaluation: dict | None = None
