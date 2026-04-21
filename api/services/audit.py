import json
from datetime import datetime, timezone

from api.db.database import get_connection


def log_rag_event(user_role: str, question: str, results: list[tuple], reply: str):
    retrieved_chunks = [
        {
            "id": chunk["id"],
            "doc_id": chunk["doc_id"],
            "score": score,
            "text_snippet": chunk["text"][:150],
        }
        for score, chunk in results
    ]

    timestamp = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (timestamp, user_role, question, reply, retrieved_chunks)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (timestamp, user_role, question, reply, json.dumps(retrieved_chunks)),
            )


def get_audit_logs():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, timestamp, user_role, question, reply, retrieved_chunks 
                FROM audit_logs 
                ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "user_role": row[2],
                    "question": row[3],
                    "reply": row[4],
                    "retrieved_chunks": row[5],
                }
                for row in rows
            ]
