from pydantic import BaseModel, Field

from assistant.application.public_assistant import PublicAssistantConfiguration


class PublicAssistantConfigurationResponse(BaseModel):
    """The deliberately narrow, presentation-only anonymous Assistant contract."""

    id: str
    name: str
    welcome_message: str
    input_placeholder: str
    suggested_questions: list[str]
    published_revision: int = Field(ge=1)

    @classmethod
    def from_configuration(
        cls, configuration: PublicAssistantConfiguration
    ) -> "PublicAssistantConfigurationResponse":
        return cls(
            id=configuration.id,
            name=configuration.name,
            welcome_message=configuration.welcome_message,
            input_placeholder=configuration.input_placeholder,
            suggested_questions=list(configuration.suggested_questions),
            published_revision=configuration.published_revision,
        )
