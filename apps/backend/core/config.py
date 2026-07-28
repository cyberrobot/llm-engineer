import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CHUNKS_SEARCH_RESULTS_LIMIT = 8
CHUNK_TOP_K = 3
CHUNKS_MAX_DISTANCE = 0.8
WEIGHT_KEYWORD_MATCH = 0.2
WEIGHT_EMBEDDING_SIMILARITY = 0.8
AUDIT_LOG_LIMIT = 10

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DISABLE_RATE_LIMITS = os.getenv("DISABLE_RATE_LIMITS", "false").lower() == "true"
DISABLE_INGEST = os.getenv("DISABLE_INGEST", "false").lower() == "true"
DISABLE_CACHE = os.getenv("DISABLE_CACHE", "false").lower() == "true"
DISABLE_AUDIT_LOGS = os.getenv("DISABLE_AUDIT_LOGS", "false").lower() == "true"
DEBUG_DELAY = os.getenv("DEBUG_DELAY", "false").lower() == "true"


def get_openai_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_ingest_api_key() -> str | None:
    return os.getenv("INGEST_API_KEY") or os.getenv("ADMIN_API_KEY")


def get_max_upload_bytes() -> int:
    return int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def get_upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "uploads"))
