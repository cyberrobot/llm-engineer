import pytest
from pydantic import ValidationError

from assistant.schemas import ChatRequest, ChatResponse, ErrorResponse, SourceReference
from assistant.schemas.chat import MAX_CHAT_MESSAGE_LENGTH


def test_chat_request_accepts_and_strips_valid_message():
    request = ChatRequest(message="  How can you help?  ")

    assert request.message == "How can you help?"


@pytest.mark.parametrize("message", ["", " ", "\n\t"])
def test_chat_request_rejects_empty_message(message):
    with pytest.raises(ValidationError):
        ChatRequest(message=message)


def test_chat_request_rejects_message_over_maximum_length():
    with pytest.raises(ValidationError):
        ChatRequest(message="a" * (MAX_CHAT_MESSAGE_LENGTH + 1))


def test_chat_request_rejects_additional_fields():
    with pytest.raises(ValidationError):
        ChatRequest(message="Hello", conversation_id="not-supported-yet")


def test_chat_response_defaults_to_independent_empty_source_lists():
    first = ChatResponse(message="First")
    second = ChatResponse(message="Second")

    first.sources.append(SourceReference(id="source-1", title="Source one"))

    assert len(first.sources) == 1
    assert second.sources == []


def test_common_contracts_serialize_as_expected():
    source = SourceReference(id="source-1", title="Source one")
    error = ErrorResponse(detail="Invalid request")

    assert source.model_dump() == {"id": "source-1", "title": "Source one"}
    assert error.model_dump() == {"detail": "Invalid request"}
