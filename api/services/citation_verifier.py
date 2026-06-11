from difflib import SequenceMatcher


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def verify_sentence(
    sentence: str,
    chunks: list[dict],
    threshold: float = 0.6,
) -> tuple[bool, list[str]]:
    if not sentence.strip() or not chunks:
        return (False, [])

    matching_source_ids: list[str] = []

    for chunk in chunks:
        chunk_id = chunk.get("id")
        chunk_text = chunk.get("text")

        if not chunk_id or not chunk_text:
            continue

        if similarity(sentence, chunk_text) >= threshold:
            matching_source_ids.append(chunk_id)

    if matching_source_ids:
        return (True, matching_source_ids)

    return (False, [])
