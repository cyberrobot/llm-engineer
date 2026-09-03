import json
from uuid import UUID

from infrastructure.database.connection import get_connection


def save_document_with_chunks(doc_id, doc_type, access_roles, chunks, *, assistant_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                  INSERT INTO documents (id, doc_type, access_roles, assistant_id)
                  VALUES (%s, %s, %s, %s)
                """,
                (doc_id, doc_type, json.dumps(access_roles), str(assistant_id)),
            )

            cur.executemany(
                """
                INSERT INTO chunks (id, doc_id, text, embedding, access_roles, assistant_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        chunk["id"],
                        chunk["doc_id"],
                        chunk["text"],
                        chunk["embedding"],
                        json.dumps(chunk["access_roles"]),
                        str(assistant_id),
                    )
                    for chunk in chunks
                ],
            )


def create_uploaded_document(
    doc_id, doc_type, access_roles, upload_path, original_filename, *, assistant_id: UUID
):
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
                    original_filename,
                    assistant_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id,
                    doc_type,
                    json.dumps(access_roles),
                    "uploaded",
                    upload_path,
                    original_filename,
                    str(assistant_id),
                ),
            )


def create_ingestion_job(job_id, document_id, stage, status, progress):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_ingestion_jobs (
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


def list_all_chunks(*, assistant_id: UUID):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, doc_id, text, access_roles
                FROM chunks
                WHERE assistant_id = %s
            """,
                (str(assistant_id),),
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
