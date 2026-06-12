from api.services.citation_verifier import verify_sentence
from api.services.split_sentences import split_sentences


def evaluate_answer(answer: str, chunks: list[dict]) -> list[dict]:
    results: list[dict] = []

    for sentence in split_sentences(answer):
        supported, source_ids = verify_sentence(sentence.text, chunks)
        results.append(
            {
                "sentence": sentence.text,
                "supported": supported,
                "source_ids": source_ids,
            }
        )

    return results
