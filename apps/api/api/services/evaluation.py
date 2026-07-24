from api.services.citation_verifier import verify_sentence
from api.services.split_sentences import split_sentences


def evaluate_answer(answer: str, chunks: list[dict]) -> list[dict]:
    results: list[dict] = []

    for sentence in split_sentences(answer):
        results.append(verify_sentence(sentence.text, chunks))

    return results


def calculate_evaluation_metrics(results: list[dict]) -> dict:
    total_sentences = len(results)

    if total_sentences == 0:
        return {
            "groundedness_score": 0,
            "verified_sentences": 0,
            "unsupported_claims": 0,
            "total_sentences": 0,
            "citation_count": 0,
        }

    supported_results = [result for result in results if result.get("supported")]
    verified_sentences = len(supported_results)
    source_ids = {
        source_id
        for result in supported_results
        for source_id in result.get("source_ids", [])
    }

    return {
        "groundedness_score": round(verified_sentences / total_sentences, 2),
        "verified_sentences": verified_sentences,
        "unsupported_claims": total_sentences - verified_sentences,
        "total_sentences": total_sentences,
        "citation_count": len(source_ids),
    }
