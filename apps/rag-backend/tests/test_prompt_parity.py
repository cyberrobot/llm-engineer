from pathlib import Path


def test_extracted_prompts_match_the_legacy_rag_prompts():
    repository_root = Path(__file__).parents[3]
    legacy_prompts = repository_root / "apps" / "backend" / "prompts"
    extracted_prompts = repository_root / "apps" / "rag-backend" / "prompts"

    for name in ("query_generation.md", "rerank_chunks.md", "answer_system.md"):
        assert (extracted_prompts / name).read_text(encoding="utf-8") == (
            legacy_prompts / name
        ).read_text(encoding="utf-8")
