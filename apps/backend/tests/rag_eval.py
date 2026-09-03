import logging

from assistant.application.rag_chat import rag_chat
from assistant.application.rag_search import rag_search
from assistant.domain.assistant import REDMOOR_ASSISTANT_ID
from assistant.infrastructure.repositories.rag_knowledge import PostgresRagKnowledgeRepository

if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

logger = logging.getLogger(__name__)

TEST_CASES = [
    {
        "query": "What procedures should staff follow before performing surgery?",
        "user_role": "doctor",
        "expected_keywords": [
            "disinfect",
            "sterilise",
            "protective equipment",
            "consent",
            "infection",
        ],
        "expected_min_sources": 2,
        "expected_max_sources": 5,
    },
    {
        "query": "What checks are required before approving a large international payment?",
        "user_role": "manager",
        "expected_keywords": [
            "anti-money laundering",
            "identity verification",
            "suspicious transactions",
            "sanctions",
            "audit",
        ],
        "expected_min_sources": 2,
        "expected_max_sources": 5,
    },
    {
        "query": "How should support agents handle customer complaints about delayed deliveries?",
        "user_role": "manager",
        "expected_keywords": [
            "apologise",
            "tracking",
            "compensation",
            "logistics",
            "crm",
        ],
        "expected_min_sources": 2,
        "expected_max_sources": 5,
    },
]


def evaluate_retrieval():
    hits = 0
    repository = PostgresRagKnowledgeRepository()

    for case in TEST_CASES:
        results = rag_search(
            REDMOOR_ASSISTANT_ID,
            case["query"],
            case["user_role"],
            repository,
        )

        texts = [r["text"].lower() for r in results["results"]]

        if any(any(keyword in text for keyword in case["expected_keywords"]) for text in texts):
            hits += 1
        else:
            logger.info(f"Missed Retrieval - Query: {case['query']}, Retrieved Texts: {texts}")

    return hits


def evaluate_answers():
    hits = 0
    repository = PostgresRagKnowledgeRepository()
    for case in TEST_CASES:
        response = rag_chat(case["query"], case["user_role"], repository)

        answer = response["reply"]["answer"].lower()

        source_ids = response["reply"].get("source_ids", [])

        answer_ok = score_answer(answer, case["expected_keywords"])

        sources_ok = score_sources(
            source_ids,
            case["expected_min_sources"],
            case["expected_max_sources"],
        )

        if answer_ok and sources_ok:
            hits += 1
        else:
            logger.info(
                "Missed Answer - Query: %s, Answer OK: %s, Sources OK: %s, Source Count: %s, Answer: %s",
                case["query"],
                answer_ok,
                sources_ok,
                len(source_ids),
                answer,
            )

    return hits


def score_answer(answer: str, keywords: list[str]) -> bool:
    answer = answer.lower()
    return any(keyword.lower() in answer for keyword in keywords)


def score_sources(source_ids: list[str], min_sources: int, max_sources: int) -> bool:
    return min_sources <= len(source_ids) <= max_sources


def evaluate():
    total = len(TEST_CASES)
    retrieval_hits = evaluate_retrieval()
    answer_hits = evaluate_answers()
    logger.info("\n--- RESULTS ---")
    logger.info(f"Retrieval Hits: {retrieval_hits}/{total}")
    logger.info(f"Answer Hits: {answer_hits}/{total}")


if __name__ == "__main__":
    evaluate()
