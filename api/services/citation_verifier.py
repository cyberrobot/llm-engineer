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
    source_ids: list[str] = []
    best_score = 0.0

    for chunk in chunks:
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue

        embedding = _chunk_embedding(chunk)
        if embedding is None:
            continue

        score = float(cosine_similarity(sentence_embedding, embedding))
        best_score = max(best_score, score)

        if score >= threshold:
            source_ids.append(chunk_id)

    support_score = round(best_score, 4)
    if source_ids:
        return {
            "sentence": sentence,
            "supported": True,
            "source_ids": source_ids,
            "support_score": support_score,
        }

    return {
        "sentence": sentence,
        "supported": False,
        "source_ids": [],
        "support_score": support_score,
    }
