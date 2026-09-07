from pathlib import Path


def test_runtime_image_is_rag_owned_and_uses_readiness_probe():
    root = Path(__file__).parents[1]
    dockerfile = (root / "Dockerfile").read_text()

    assert "/health/ready" in dockerfile
    assert "uvicorn main:app" in dockerfile
    assert "apps/backend" not in dockerfile
    assert "migrations.py upgrade" not in dockerfile
    assert "RAG_MIGRATION_DATABASE_URL" not in dockerfile


def test_migration_credential_is_separate_from_runtime_credentials():
    example = (Path(__file__).parents[1] / ".env.example").read_text()

    assert "RAG_KNOWLEDGE_DATABASE_URL=" in example
    assert "RAG_AUTH_AUDIT_DATABASE_URL=" in example
    assert "RAG_MIGRATION_DATABASE_URL=" in example
    assert "\nDATABASE_URL=" not in example
