import json

from api.db.database import get_connection
from api.services.settings import (
    CHUNKS_SEARCH_RESULTS_LIMIT,
    WEIGHT_EMBEDDING_SIMILARITY,
    WEIGHT_KEYWORD_MATCH,
)


def save_document_with_chunks(doc_id, doc_type, access_roles, chunks):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                  INSERT INTO documents (id, doc_type, access_roles)
                  VALUES (%s, %s, %s)
                """,
                (doc_id, doc_type, json.dumps(access_roles)),
            )

            cur.executemany(
                """
                INSERT INTO chunks (id, doc_id, text, embedding, access_roles)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        chunk["id"],
                        chunk["doc_id"],
                        chunk["text"],
                        chunk["embedding"],
                        json.dumps(chunk["access_roles"]),
                    )
                    for chunk in chunks
                ],
            )


def create_uploaded_document(doc_id, doc_type, access_roles, upload_path, original_filename):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (
                    id,
                    doc_type,
                    access_roles,
                    status,
                    upload_path,
                    original_filename
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id,
                    doc_type,
                    json.dumps(access_roles),
                    "uploaded",
                    upload_path,
                    original_filename,
                ),
            )


def create_ingestion_job(job_id, document_id, stage, status, progress):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_jobs (
                    id,
                    document_id,
                    stage,
                    status,
                    progress
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (job_id, document_id, stage, status, progress),
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
                WITH vector_candidates AS (
                  SELECT id, doc_id, text, embedding <=> %s::vector AS distance, access_roles, text_search
                  FROM chunks
                  WHERE access_roles ? %s
                  ORDER BY embedding <=> %s::vector
                  LIMIT 50
                )
                SELECT id, doc_id, text, distance, access_roles, ts_rank(text_search, plainto_tsquery('english', %s)) AS keyword_match,
                    ((1 - distance) * %s + ts_rank(text_search, plainto_tsquery('english', %s)) * %s) AS hybrid_score
                FROM vector_candidates
                ORDER BY hybrid_score DESC
                LIMIT %s
            """,
                (
                    query_embedding,
                    access_role,
                    query_embedding,
                    query,
                    weight_embedding_similarity,
                    query,
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
                SELECT id, doc_id, text, access_roles
                FROM chunks
            """,
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "doc_id": row[1],
                    "text": row[2],
                    "access_roles": row[3],
                }
                for row in rows
            ]
