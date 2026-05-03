import json

from api.db.database import get_connection
from api.services.settings import (
    CHUNKS_SEARCH_RESULTS_LIMIT,
    WEIGHT_EMBEDDING_SIMILARITY,
    WEIGHT_KEYWORD_MATCH,
)


def save_document(doc_id: str, doc_type: str, access_roles: list[str]):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                  INSERT INTO documents (id, doc_type, access_roles)
                  VALUES (%s, %s, %s)
                """,
                (doc_id, doc_type, json.dumps(access_roles)),
            )


def save_chunk(
    chunk_id: str, doc_id: str, text: str, embedding: list[float], access_roles: list[str]
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                  INSERT INTO chunks (id, doc_id, text, embedding, access_roles)
                  VALUES (%s, %s, %s, %s, %s)
                """,
                (chunk_id, doc_id, text, embedding, json.dumps(access_roles)),
            )


def search_chunks_by_embedding(
    query_embedding: list[float],
    query: str,
    access_role: str,
    limit: int = CHUNKS_SEARCH_RESULTS_LIMIT,
    weight_keyword_match: float = WEIGHT_KEYWORD_MATCH,
    weight_embedding_similarity: float = WEIGHT_EMBEDDING_SIMILARITY,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH ranked_chunks AS (
                  SELECT id, doc_id, text, embedding <=> %s::vector AS distance, access_roles,
                  COALESCE(
                    ts_rank(
                      text_search,
                      plainto_tsquery('english', %s)
                    ),
                    0
                  ) AS keyword_match
                  FROM chunks
                  WHERE access_roles::jsonb ? %s
                )
                SELECT id, doc_id, text, distance, access_roles, keyword_match,
                    ((1 - distance) * %s + keyword_match * %s) AS hybrid_score
                FROM ranked_chunks
                ORDER BY hybrid_score DESC
                LIMIT %s
            """,
                (
                    query_embedding,
                    query,
                    access_role,
                    weight_embedding_similarity,
                    weight_keyword_match,
                    limit,
                ),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "doc_id": row[1],
                    "text": row[2],
                    "distance": row[3],
                    "access_roles": row[4],
                    "keyword_match": float(row[5]),
                    "hybrid_score": row[6],
                }
                for row in rows
            ]


def list_all_chunks():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, doc_id, text, embedding, access_roles 
                FROM chunks
            """,
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "doc_id": row[1],
                    "text": row[2],
                    "embedding": row[3],
                    "access_roles": row[4],
                }
                for row in rows
            ]
