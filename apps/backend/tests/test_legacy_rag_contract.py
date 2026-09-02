import pytest
from fastapi.testclient import TestClient
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from assistant.application import rag_chat as rag_chat_application
from core.config import AUDIT_LOG_LIMIT
from main import app
from operations.api.administration_dependencies import get_runtime_state_store
from operations.application.administration import MaintenanceService
from shared.dependencies.rate_limit import limiter

EMPTY_RESPONSE = {
    "reply": {
        "answer": "I could not find relevant information in the provided documents.",
        "source_ids": [],
    },
    "sources": [],
    "evaluation": {
        "sentences": [],
        "metrics": {
            "groundedness_score": 0,
            "verified_sentences": 0,
            "unsupported_claims": 0,
            "total_sentences": 0,
            "citation_count": 0,
        },
    },
}


@pytest.fixture(autouse=True)
def isolated_legacy_runtime_state():
    previous_rate_limit_state = limiter.enabled
    maintenance = MaintenanceService(get_runtime_state_store())
    previous_maintenance_state = maintenance.get()
    limiter.enabled = False
    maintenance.update(enabled=False, message=None, actor="legacy-contract-test")
    yield
    limiter.enabled = previous_rate_limit_state
    maintenance.update(
        enabled=previous_maintenance_state.enabled,
        message=previous_maintenance_state.message,
        actor=previous_maintenance_state.updated_by or "legacy-contract-test",
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_rag_chat_forwards_explicit_role_and_preserves_complete_ordered_response(
    client, monkeypatch
) -> None:
    calls = []
    expected = {
        "reply": {
            "answer": "Review the checklist and obtain consent.",
            "source_ids": ["chunk-20", "chunk-10"],
        },
        "sources": [
            {"id": "chunk-20", "text": "The checklist must be reviewed."},
            {"id": "chunk-10", "text": "Consent must be documented."},
        ],
        "evaluation": {
            "sentences": [
                {
                    "sentence": "Review the checklist and obtain consent.",
                    "supported": True,
                    "source_ids": ["chunk-20", "chunk-10"],
                    "support_score": 1.0,
                }
            ],
            "metrics": {
                "groundedness_score": 1.0,
                "verified_sentences": 1,
                "unsupported_claims": 0,
                "total_sentences": 1,
                "citation_count": 2,
            },
        },
    }

    def complete_response(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr("assistant.api.rag.rag_chat", complete_response)

    response = client.post(
        "/rag-chat",
        json={"message": "What is required?", "user_role": "manager"},
    )

    assert response.status_code == 200
    assert calls == [{"query": "What is required?", "user_role": "manager"}]
    assert response.json() == expected


@pytest.mark.parametrize(
    ("body", "expected_query", "expected_role"),
    [
        ({"message": "What is required?"}, "What is required?", "user"),
        ({"message": "", "user_role": ""}, "", ""),
        (
            {"message": "What is required?", "unexpected": "ignored"},
            "What is required?",
            "user",
        ),
    ],
    ids=["omitted-role-defaults-to-user", "empty-strings", "extra-fields-ignored"],
)
def test_rag_chat_preserves_current_accepted_request_values(
    client, monkeypatch, body, expected_query, expected_role
) -> None:
    calls = []

    def response_for(**kwargs):
        calls.append(kwargs)
        return EMPTY_RESPONSE

    monkeypatch.setattr("assistant.api.rag.rag_chat", response_for)

    response = client.post("/rag-chat", json=body)

    assert response.status_code == 200
    assert calls == [{"query": expected_query, "user_role": expected_role}]
    assert response.json() == EMPTY_RESPONSE


@pytest.mark.parametrize(
    ("request_kwargs", "expected_detail"),
    [
        (
            {"json": {"user_role": "user"}},
            [
                {
                    "type": "missing",
                    "loc": ["body", "message"],
                    "msg": "Field required",
                    "input": {"user_role": "user"},
                }
            ],
        ),
        (
            {"json": {"message": None}},
            [
                {
                    "type": "string_type",
                    "loc": ["body", "message"],
                    "msg": "Input should be a valid string",
                    "input": None,
                }
            ],
        ),
        (
            {"json": {"message": "hello", "user_role": None}},
            [
                {
                    "type": "string_type",
                    "loc": ["body", "user_role"],
                    "msg": "Input should be a valid string",
                    "input": None,
                }
            ],
        ),
        (
            {"json": {"message": 7, "user_role": 8}},
            [
                {
                    "type": "string_type",
                    "loc": ["body", "message"],
                    "msg": "Input should be a valid string",
                    "input": 7,
                },
                {
                    "type": "string_type",
                    "loc": ["body", "user_role"],
                    "msg": "Input should be a valid string",
                    "input": 8,
                },
            ],
        ),
        (
            {"content": '{"message":', "headers": {"Content-Type": "application/json"}},
            [
                {
                    "type": "json_invalid",
                    "loc": ["body", 11],
                    "msg": "JSON decode error",
                    "input": {},
                    "ctx": {"error": "Expecting value"},
                }
            ],
        ),
    ],
    ids=["missing-message", "null-message", "null-role", "wrong-types", "malformed-json"],
)
def test_rag_chat_preserves_validation_errors(client, request_kwargs, expected_detail) -> None:
    response = client.post("/rag-chat", **request_kwargs)

    assert response.status_code == 422
    assert response.json() == {"detail": expected_detail}


def test_rag_chat_preserves_empty_context_success_through_http(client, monkeypatch) -> None:
    monkeypatch.setattr(rag_chat_application, "DEBUG_DELAY", False)
    monkeypatch.setattr(rag_chat_application, "get_cached_response", lambda *_args: None)
    monkeypatch.setattr(
        rag_chat_application,
        "retrieve_context",
        lambda *_args: ([], [], 1.25),
    )

    response = client.post("/rag-chat", json={"message": "Unknown policy"})

    assert response.status_code == 200
    assert response.json() == EMPTY_RESPONSE


def test_rag_chat_preserves_existing_exception_mapping_through_http(client, monkeypatch) -> None:
    monkeypatch.setattr(rag_chat_application, "DEBUG_DELAY", False)
    monkeypatch.setattr(
        rag_chat_application,
        "get_cached_response",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("fictional retrieval failure")),
    )

    response = client.post("/rag-chat", json={"message": "What is required?"})

    assert response.status_code == 500
    assert response.json() == {"detail": "fictional retrieval failure"}


def _audit_item(*, item_id: int, timestamp: str, question: str) -> dict:
    return {
        "id": item_id,
        "timestamp": timestamp,
        "user_role": "manager",
        "question": question,
        "reply": {"answer": "Use the checklist.", "source_ids": ["chunk-2", "chunk-1"]},
        "metrics": {
            "retrieval_time": 12.5,
            "llm_time": 25.0,
            "total_time": 37.5,
            "cache_hit": False,
            "input_tokens": 4,
            "output_tokens": 9,
        },
        "queries": [question, "Which checklist applies?"],
        "retrieved_chunks": [
            {
                "rank": 1,
                "id": "chunk-2",
                "doc_id": "document-2",
                "distance": 0.1,
                "hybrid_score": 0.9,
                "text_snippet": "Review the checklist.",
                "keyword_match": 0.375,
            },
            {
                "rank": 2,
                "id": "chunk-1",
                "doc_id": "document-1",
                "distance": 0.2,
                "hybrid_score": 0.8,
                "text_snippet": "Document consent.",
                "keyword_match": 0.0,
            },
        ],
        "reranked_chunks": [
            {
                "rank": 1,
                "id": "chunk-1",
                "doc_id": "document-1",
                "distance": 0.2,
                "hybrid_score": 0.8,
                "text_snippet": "Document consent.",
                "keyword_match": 0.0,
            },
            {
                "rank": 2,
                "id": "chunk-2",
                "doc_id": "document-2",
                "distance": 0.1,
                "hybrid_score": 0.9,
                "text_snippet": "Review the checklist.",
                "keyword_match": 0.375,
            },
        ],
        "evaluation": {
            "sentences": [],
            "metrics": {
                "groundedness_score": 1.0,
                "verified_sentences": 1,
                "unsupported_claims": 0,
                "total_sentences": 1,
                "citation_count": 2,
            },
        },
    }


def test_audit_logs_preserve_complete_newest_first_array_and_default_limit(
    client, monkeypatch
) -> None:
    expected = [
        _audit_item(
            item_id=12,
            timestamp="2026-08-31T12:01:00+00:00",
            question="What is required now?",
        ),
        _audit_item(
            item_id=11,
            timestamp="2026-08-31T12:00:00+00:00",
            question="What was required before?",
        ),
    ]
    received_limits = []

    def ordered_rows(limit):
        received_limits.append(limit)
        return expected

    monkeypatch.setattr("assistant.api.audit.get_audit_logs", ordered_rows)

    response = client.get("/audit-logs")

    assert response.status_code == 200
    assert received_limits == [AUDIT_LOG_LIMIT]
    assert response.json() == expected
    assert [item["id"] for item in response.json()] == [12, 11]
    keyword_matches = [
        chunk["keyword_match"]
        for item in response.json()
        for group in ("retrieved_chunks", "reranked_chunks")
        for chunk in item[group]
    ]
    assert keyword_matches == [0.375, 0.0, 0.0, 0.375] * 2
    assert all(type(value) is float for value in keyword_matches)


def test_audit_logs_preserve_empty_array(client, monkeypatch) -> None:
    monkeypatch.setattr("assistant.api.audit.get_audit_logs", lambda _limit: [])

    response = client.get("/audit-logs")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("query", "expected_limit"),
    [
        ("?limit=4", 4),
        ("?limit=0", 0),
        ("?limit=-2", -2),
        ("?limit=4&limit=7", 7),
        ("?limit=999999999999999999999999999999", 999999999999999999999999999999),
    ],
    ids=["explicit", "zero", "negative", "repeated-last-wins", "excessively-large"],
)
def test_audit_logs_parse_and_forward_current_integer_limits(
    client, monkeypatch, query, expected_limit
) -> None:
    class ForwardedLimit(Exception):
        def __init__(self, limit: int) -> None:
            self.limit = limit

    def rows(limit):
        raise ForwardedLimit(limit)

    monkeypatch.setattr("assistant.api.audit.get_audit_logs", rows)

    with pytest.raises(ForwardedLimit) as raised:
        client.get(f"/audit-logs{query}")

    assert raised.value.limit == expected_limit


def test_audit_logs_reject_malformed_limit(client) -> None:
    response = client.get("/audit-logs?limit=nope")

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "int_parsing",
                "loc": ["query", "limit"],
                "msg": "Input should be a valid integer, unable to parse string as an integer",
                "input": "nope",
            }
        ]
    }


def test_legacy_routes_remain_anonymous_and_keep_maintenance_asymmetry(client, monkeypatch) -> None:
    monkeypatch.setattr("assistant.api.rag.rag_chat", lambda **_kwargs: EMPTY_RESPONSE)
    monkeypatch.setattr("assistant.api.audit.get_audit_logs", lambda _limit: [])
    maintenance = MaintenanceService(get_runtime_state_store())

    assert client.post("/rag-chat", json={"message": "hello"}).status_code == 200
    assert client.get("/audit-logs").status_code == 200

    maintenance.update(enabled=True, message="private operator note", actor="operator")

    blocked = client.post("/rag-chat", json={"message": "hello"})
    audit_response = client.get("/audit-logs")

    assert blocked.status_code == 503
    assert blocked.json() == {
        "detail": {
            "code": "maintenance_mode",
            "message": "The service is undergoing maintenance.",
        }
    }
    assert "private operator note" not in blocked.text
    assert audit_response.status_code == 200
    assert audit_response.json() == []


def test_legacy_routes_preserve_public_http_rate_limits(monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr(limiter, "_storage", storage)
    monkeypatch.setattr(limiter, "_limiter", FixedWindowRateLimiter(storage))
    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setattr("assistant.api.rag.rag_chat", lambda **_kwargs: EMPTY_RESPONSE)
    monkeypatch.setattr("assistant.api.audit.get_audit_logs", lambda _limit: [])
    client = TestClient(app)

    rag_responses = [client.post("/rag-chat", json={"message": "hello"}) for _ in range(21)]

    assert [response.status_code for response in rag_responses[:20]] == [200] * 20
    assert rag_responses[20].status_code == 429
    assert rag_responses[20].json() == {
        "error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please wait a moment before trying again.",
            "retry_after_seconds": 60,
        }
    }

    limiter.reset()
    audit_responses = [client.get("/audit-logs") for _ in range(61)]

    assert [response.status_code for response in audit_responses[:60]] == [200] * 60
    assert audit_responses[60].status_code == 429
    assert audit_responses[60].json() == {
        "error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please wait a moment before trying again.",
            "retry_after_seconds": 60,
        }
    }


def test_openapi_freezes_legacy_route_methods_and_transport_schemas() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert set(paths["/rag-chat"]) == {"post"}
    assert set(paths["/audit-logs"]) == {"get"}
    assert "/admin/assistants/rag-chat" not in paths
    assert "/admin/operations/audit/rag" not in paths
    assert "/assistant/chat" not in paths
    assert "/chunks" not in paths
    assert "/ingest" not in paths

    rag_operation = paths["/rag-chat"]["post"]
    assert rag_operation["requestBody"] == {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/RagChatRequest"}}
        },
        "required": True,
    }
    assert rag_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RagChatResponse"
    }
    assert schema["components"]["schemas"]["RagChatRequest"] == {
        "properties": {
            "message": {"type": "string", "title": "Message"},
            "user_role": {"type": "string", "title": "User Role", "default": "user"},
        },
        "type": "object",
        "required": ["message"],
        "title": "RagChatRequest",
    }
    assert schema["components"]["schemas"]["RagChatResponse"] == {
        "properties": {
            "reply": {
                "additionalProperties": True,
                "type": "object",
                "title": "Reply",
            },
            "sources": {
                "items": {"additionalProperties": True, "type": "object"},
                "type": "array",
                "title": "Sources",
            },
            "evaluation": {
                "anyOf": [
                    {"additionalProperties": True, "type": "object"},
                    {"type": "null"},
                ],
                "title": "Evaluation",
            },
        },
        "type": "object",
        "required": ["reply", "sources"],
        "title": "RagChatResponse",
    }

    audit_operation = paths["/audit-logs"]["get"]
    assert audit_operation["parameters"] == [
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "default": AUDIT_LOG_LIMIT, "title": "Limit"},
        }
    ]
    assert audit_operation["responses"]["200"]["content"]["application/json"]["schema"] == {}
