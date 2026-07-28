from assistant.infrastructure.storage import (
    create_ingestion_job as create_ingestion_job_record,
)
from assistant.infrastructure.storage import (
    create_uploaded_document as create_uploaded_document_record,
)
from assistant.infrastructure.storage import list_all_chunks


def record_uploaded_document(
    document_id: str,
    job_id: str,
    doc_type: str,
    access_roles: list[str],
    upload_path: str,
    original_filename: str,
) -> None:
    create_uploaded_document_record(
        document_id,
        doc_type,
        access_roles,
        upload_path,
        original_filename,
    )
    create_ingestion_job_record(
        job_id,
        document_id,
        stage="validate",
        status="queued",
        progress=0,
    )


def get_chunks() -> list[dict]:
    return list_all_chunks()
