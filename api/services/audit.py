import json
import os
import time
from datetime import datetime, timezone

from api.db.database import get_connection

DEBUG_DELAY = os.getenv("DEBUG_DELAY", "false").lower() == "true"


def log_rag_event(
    user_role: str,
    question: str,
    retrieved_chunks: list[dict],
    reply: dict,
    metrics: dict,
    queries: list[dict],
):
    timestamp = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (timestamp, user_role, question, queries, reply, retrieved_chunks, metrics)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    timestamp,
                    user_role,
                    question,
                    json.dumps(queries),
                    json.dumps(reply),
                    json.dumps(retrieved_chunks),
                    json.dumps(metrics),
                ),
            )


def get_audit_logs(limit: int):
    if DEBUG_DELAY:
        time.sleep(2)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, timestamp, user_role, question, reply, retrieved_chunks, metrics, queries 
                FROM audit_logs 
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "timestamp": row[1].isoformat() if hasattr(row[1], "isoformat") else row[1],
                    "user_role": row[2],
                    "question": row[3],
                    "reply": row[4],
                    "retrieved_chunks": row[5],
                    "metrics": row[6],
                    "queries": row[7],
                }
                for row in rows
            ]


def get_latest_audit_log_for_query(question: str, user_role: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, timestamp, user_role, question, reply, retrieved_chunks, metrics, queries
                FROM audit_logs
                WHERE question = %s
                  AND user_role = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (question, user_role),
            )

            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "timestamp": row[1].isoformat() if hasattr(row[1], "isoformat") else row[1],
        "user_role": row[2],
        "question": row[3],
        "reply": row[4],
        "retrieved_chunks": row[5],
        "metrics": row[6],
        "queries": row[7],
    }
