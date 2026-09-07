from uuid import NAMESPACE_URL, uuid5

REDMOOR_ASSISTANT_ID = uuid5(NAMESPACE_URL, "assistant:redmoor")


class RequestTimedOut(Exception):
    """Raised when work cannot finish before the request's absolute deadline."""
