import json
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import psycopg
import redis
from config import settings
from openai import OpenAI

REDMOOR_ASSISTANT_ID = uuid5(NAMESPACE_URL, "assistant:redmoor")


@contextmanager
def _connection(database_url: str | None, setting_name: str):
    if not database_url:
        raise RuntimeError(f"{setting_name} is not configured")
    with psycopg.connect(
        database_url, connect_timeout=3, options="-c statement_timeout=30000"
    ) as conn:
        yield conn


def knowledge_connection():
    return _connection(settings.knowledge_database_url, "RAG_KNOWLEDGE_DATABASE_URL")


def auth_audit_connection():
    return _connection(settings.auth_audit_database_url, "RAG_AUTH_AUDIT_DATABASE_URL")


class PostgresKnowledgeRepository:
    def search(
        self,
        *,
        assistant_id: str,
        query_embedding: list[float],
        query: str,
        role: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with knowledge_connection() as conn:
            rows = conn.execute(
                """WITH vector_candidates AS (
                SELECT c.id, c.doc_id, c.text, c.text_search,
                       c.embedding <=> %s::vector AS distance
                FROM chunks c JOIN documents d ON d.id = c.doc_id
                WHERE c.assistant_id = %s AND d.assistant_id = %s
                  AND d.retrieval_state = 'enabled' AND c.access_roles ? %s
                ORDER BY c.embedding <=> %s::vector LIMIT 50)
                SELECT id, doc_id, text, distance,
                  ts_rank(text_search, plainto_tsquery('english', %s)),
                  ((1-distance)*0.8 + ts_rank(text_search,
                    plainto_tsquery('english', %s))*0.2)
                FROM vector_candidates ORDER BY 6 DESC LIMIT %s""",
                (
                    query_embedding,
                    str(assistant_id),
                    str(assistant_id),
                    role,
                    query_embedding,
                    query,
                    query,
                    limit,
                ),
            ).fetchall()
        return [
            {
                "id": r[0],
                "doc_id": r[1],
                "text": r[2],
                "distance": float(r[3]),
                "keyword_match": float(r[4]),
                "hybrid_score": float(r[5]),
            }
            for r in rows
        ]


class AuditRepository:
    def list(self, limit: int) -> list[dict]:
        with auth_audit_connection() as conn:
            rows = conn.execute(
                """SELECT id,timestamp,user_role,question,reply,
                retrieved_chunks,reranked_chunks,metrics,queries,evaluation
                FROM audit_logs ORDER BY id DESC LIMIT %s""",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "timestamp": r[1].isoformat(),
                "user_role": r[2],
                "question": r[3],
                "reply": r[4],
                "retrieved_chunks": r[5],
                "reranked_chunks": r[6],
                "metrics": r[7],
                "queries": r[8],
                "evaluation": r[9],
            }
            for r in rows
        ]

    def write(
        self,
        *,
        role: str,
        question: str,
        reply: dict,
        retrieved: Sequence[Any],
        reranked: Sequence[Any],
        queries: Sequence[Any],
        evaluation: dict,
        metrics: dict,
    ) -> None:
        with auth_audit_connection() as conn:
            conn.execute(
                """INSERT INTO audit_logs
                (timestamp,user_role,question,queries,reply,retrieved_chunks,
                 reranked_chunks,evaluation,metrics) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    datetime.now(timezone.utc),
                    role,
                    question,
                    json.dumps(queries),
                    json.dumps(reply),
                    json.dumps(retrieved),
                    json.dumps(reranked),
                    json.dumps(evaluation),
                    json.dumps(metrics),
                ),
            )

    def latest(self, *, question: str, role: str) -> dict | None:
        with auth_audit_connection() as conn:
            row = conn.execute(
                """SELECT reply,retrieved_chunks,reranked_chunks,metrics,queries,evaluation
                FROM audit_logs WHERE question = %s AND user_role = %s
                ORDER BY id DESC LIMIT 1""",
                (question, role),
            ).fetchone()
        if row is None:
            return None
        return {
            "reply": row[0],
            "retrieved_chunks": row[1],
            "reranked_chunks": row[2],
            "metrics": row[3],
            "queries": row[4],
            "evaluation": row[5],
        }


class Cache:
    def __init__(self):
        self.client = redis.from_url(settings.redis_url, decode_responses=True)

    def key(self, query: str, role: str) -> str:
        return f"rag:{' '.join(query.strip().lower().split())}:{role}"

    def get(self, query: str, role: str):
        if settings.disable_cache:
            return None
        try:
            value = self.client.get(self.key(query, role))
            return json.loads(value) if value else None
        except redis.RedisError:
            return None

    def set(self, query: str, role: str, value: dict):
        if not settings.disable_cache:
            try:
                self.client.setex(
                    self.key(query, role), settings.cache_ttl_seconds, json.dumps(value)
                )
            except redis.RedisError:
                pass

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False

    def close(self) -> None:
        self.client.close()


class Provider:
    def __init__(self):
        if not settings.openai_api_key:
            raise RuntimeError("RAG_OPENAI_API_KEY is not configured")
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.provider_timeout_seconds,
            max_retries=settings.provider_max_retries,
        )

    def embedding(self, text: str) -> list[float]:
        return (
            self.client.embeddings.create(model=settings.embedding_model, input=text)
            .data[0]
            .embedding
        )

    def text(self, prompt: str) -> str:
        return self.client.responses.create(
            model=settings.chat_model, input=prompt
        ).output_text.strip()

    def close(self) -> None:
        self.client.close()
