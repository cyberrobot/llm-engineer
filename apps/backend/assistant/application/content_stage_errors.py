class ContentStageError(RuntimeError):
    """Base error for an explicitly recoverable page-processing stage failure."""


class RecoverableContentExtractionError(ContentStageError):
    """Raised when one page cannot be extracted but other pages may continue."""


class RecoverableTextCleaningError(ContentStageError):
    """Raised when one extracted page cannot be cleaned but processing may continue."""


class RecoverableTextChunkingError(ContentStageError):
    """Raised when one cleaned page cannot be chunked but processing may continue."""
