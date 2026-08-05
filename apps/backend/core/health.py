import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.config import get_upload_dir, validate_startup_configuration
from infrastructure.database.connection import get_connection

logger = logging.getLogger(__name__)


class DependencyHealthError(RuntimeError):
    """Safe readiness failure that does not disclose infrastructure details."""


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def validate_dependency_health(*, connection_factory: Callable[[], Any] = get_connection) -> None:
    """Validate configured production dependencies using bounded connection settings."""
    try:
        validate_startup_configuration()
        if not is_production():
            return

        database_url = os.getenv("DATABASE_URL")
        api_key = os.getenv("OPENAI_API_KEY")
        if not database_url or not api_key:
            raise RuntimeError("Required production configuration is missing.")

        upload_dir = get_upload_dir()
        resolved_upload_dir = upload_dir.expanduser().resolve()
        writable_parent = _existing_parent(resolved_upload_dir)
        if (
            resolved_upload_dir.exists()
            and not resolved_upload_dir.is_dir()
            or not writable_parent.is_dir()
            or not os.access(writable_parent, os.W_OK)
        ):
            raise RuntimeError("Upload storage is not writable.")

        with connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
                row = cursor.fetchone()
                if not row or not bool(row[0]):
                    raise RuntimeError("The vector extension is unavailable.")
    except DependencyHealthError:
        raise
    except Exception as exc:
        logger.exception("Dependency health validation failed")
        raise DependencyHealthError("Service dependencies are unavailable.") from exc


def _existing_parent(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate
