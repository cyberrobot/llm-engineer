from core.config import AISettings, get_ai_settings
from infrastructure.ai.exceptions import AIConfigurationError
from infrastructure.ai.providers import AIProvider, OpenAIProvider


def create_ai_provider(settings: AISettings | None = None) -> AIProvider:
    """Build the configured provider without exposing its SDK to callers."""
    try:
        resolved_settings = settings or get_ai_settings()
    except (TypeError, ValueError) as exc:
        raise AIConfigurationError("AI provider configuration is invalid.") from exc

    if resolved_settings.provider != "openai":
        raise AIConfigurationError(
            f"Unsupported AI provider: {resolved_settings.provider or '<empty>'}."
        )
    if not resolved_settings.openai_api_key:
        raise AIConfigurationError("OPENAI_API_KEY is not configured.")
    if not resolved_settings.openai_model:
        raise AIConfigurationError("OPENAI_MODEL must not be empty.")
    if not resolved_settings.embedding_model:
        raise AIConfigurationError("OPENAI_EMBEDDING_MODEL must not be empty.")

    return OpenAIProvider(
        api_key=resolved_settings.openai_api_key,
        model=resolved_settings.openai_model,
        timeout=resolved_settings.request_timeout,
        max_retries=resolved_settings.max_retries,
        embedding_model=resolved_settings.embedding_model,
    )
