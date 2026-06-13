from api.services.embeddings import cosine_similarity, get_embedding


def _empty_result(sentence: str) -> dict:
    return {
        "sentence": sentence,
        "supported": False,
        "source_ids": [],
        "support_score": 0.0,
    }


def _chunk_embedding(chunk: dict) -> list[float] | None:
    embedding = chunk.get("embedding")
    if embedding is not None:
        return embedding

    text = chunk.get("text", "")
    if not text.strip():
        return None

    return get_embedding(text)


def verify_sentence(
    sentence: str,
    chunks: list[dict],
    threshold: float = 0.78,
) -> dict:
    if not sentence.strip() or not chunks:
        return _empty_result(sentence)

    sentence_embedding = get_embedding(sentence)
    best_source_id: str | None = None
    best_score = 0.0

    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue

        embedding = _chunk_embedding(chunk)
        if embedding is None:
            continue

        score = float(cosine_similarity(sentence_embedding, embedding))
        if score <= best_score:
            continue

        best_source_id = chunk_id
        best_score = score

    support_score = round(best_score, 4)
    if best_source_id and best_score >= threshold:
        return {
            "sentence": sentence,
            "supported": True,
            "source_ids": [best_source_id],
            "support_score": support_score,
        }

    return {
        "sentence": sentence,
        "supported": False,
        "source_ids": [],
        "support_score": support_score,
    }
