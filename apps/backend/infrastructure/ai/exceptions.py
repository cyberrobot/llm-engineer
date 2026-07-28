class AIProviderError(RuntimeError):
    """Base error raised by an AI provider without leaking SDK details."""

    default_message = "The AI provider could not complete the request."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class AIConfigurationError(AIProviderError):
    default_message = "The AI provider is not configured."


class AIAuthenticationError(AIProviderError):
    default_message = "The AI provider rejected its configured credentials."


class AIRateLimitError(AIProviderError):
    default_message = "The AI provider is temporarily rate limited."


class AITimeoutError(AIProviderError):
    default_message = "The AI provider timed out."


class AIUnavailableError(AIProviderError):
    default_message = "The AI provider is temporarily unavailable."
