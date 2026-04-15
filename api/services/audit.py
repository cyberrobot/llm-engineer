from datetime import datetime, timezone

AUDIT_LOGS = []


def log_rag_event(user_role: str, question: str, results: list[tuple], reply: str):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_role": user_role,
        "question": question,
        "retrieved_chunk_ids": [
            {
                "id": chunk["id"],
                "doc_id": chunk["doc_id"],
                "score": score,
                "text_snippet": chunk["text"][:150],
            }
            for score, chunk in results
        ],
        "reply": reply,
    }
    AUDIT_LOGS.append(entry)

    return entry
