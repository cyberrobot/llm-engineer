import json

from api.db.database import get_connection
from api.services.settings import CHUNKS_SEARCH_RESULTS_LIMIT


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
    access_role: str,
    max_distance: float,
    limit: int = CHUNKS_SEARCH_RESULTS_LIMIT,
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, doc_id, text, embedding <=> %s::vector AS distance, access_roles 
                FROM chunks
                WHERE access_roles::jsonb ? %s
                  AND embedding <=> %s::vector <= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """,
                (
                    query_embedding,
                    access_role,
                    query_embedding,
                    max_distance,
                    query_embedding,
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
