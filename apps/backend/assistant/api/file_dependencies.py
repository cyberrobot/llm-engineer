from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from assistant.application.file_fingerprint import FileFingerprintService
from assistant.application.file_ingestion import FileIngestionRepository, FileIngestionService
from assistant.infrastructure.repositories.file_ingestion import (
    InMemoryFileIngestionRepository,
    PostgresFileIngestionRepository,
)
from core.config import DATABASE_URL


@lru_cache
def get_file_fingerprint_service() -> FileFingerprintService:
    return FileFingerprintService()


@lru_cache
def get_file_ingestion_repository():
    if DATABASE_URL:
        return PostgresFileIngestionRepository()
    return InMemoryFileIngestionRepository()


def get_file_ingestion_service(
    repository: Annotated[FileIngestionRepository, Depends(get_file_ingestion_repository)],
) -> FileIngestionService:
    return FileIngestionService(repository)
