import logging

from api.services.rag_chat import rag_chat
from api.services.rag_search import rag_search

if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger(__name__)

TEST_CASES = [
    {
        "query": "Do doctors need to sterilise equipment?",
        "expected_keywords": ["sterilisation", "hygiene"],
    },
    {"query": "Who can prescribe antibiotics?", "expected_keywords": ["physicians", "prescribe"]},
    {"query": "infection signs", "expected_keywords": ["fever", "inflammation"]},
    {"query": "Who can access patient data?", "expected_keywords": ["records", "confidential"]},
]


def evaluate_retrieval():
    hits = 0

    for case in TEST_CASES:
        results = rag_search(case["query"], user_role="doctor")

        texts = [r["text"].lower() for r in results]

        if any(any(keyword in text for keyword in case["expected_keywords"]) for text in texts):
            hits += 1
        else:
            logger.info(f"Missed Retrieval - Query: {case['query']}, Retrieved Texts: {texts}")

    return hits


def evaluate_answers():
    hits = 0
    for case in TEST_CASES:
        response = rag_chat(case["query"], "doctor")

        answer = response["reply"].lower()

        logger.info(f"Query: {case['query']}")
        logger.info(f"Answer: {answer}")

        if score_answer(answer, case["expected_keywords"]):
            hits += 1
        else:
            logger.info(f"Missed Answer - Query: {case['query']}, Answer: {answer}")

    return hits


def score_answer(answer: str, keywords: list[str]) -> bool:
    return any(k in answer for k in keywords)


def evaluate():
    total = len(TEST_CASES)
    retrieval_hits = evaluate_retrieval()
    answer_hits = evaluate_answers()
    logger.info("\n--- RESULTS ---")
    logger.info(f"Retrieval Hits: {retrieval_hits}/{total}")
    logger.info(f"Answer Hits: {answer_hits}/{total}")


if __name__ == "__main__":
    evaluate()
