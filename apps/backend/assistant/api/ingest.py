import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel

from assistant.api.file_dependencies import get_file_fingerprint_service, get_file_ingestion_service
from assistant.application.file_fingerprint import FileFingerprintService
from assistant.application.file_ingestion import (
    FileIngestionRequest,
    FileIngestionService,
    FileIngestionUnavailable,
    IdempotentFileRequestConflict,
    InvalidFileIdempotencyKey,
)
from assistant.application.ingest_document import ingest_document
from assistant.application.uploads import get_chunks as list_chunks
from core.config import DISABLE_INGEST, get_ingest_api_key, get_max_upload_bytes, get_upload_dir
from shared.dependencies.rate_limit import limiter

router = APIRouter()
logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
UPLOAD_CHUNK_SIZE = 1024 * 1024


class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    access_roles: list[str] = ["user"]


def require_ingest_api_key(x_api_key: str | None):
    expected_api_key = get_ingest_api_key()
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="Ingest API key is not configured.")

    if x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid ingest API key.")


def parse_access_roles(access_roles: list[str] | None) -> list[str]:
    if not access_roles:
        return ["user"]

    roles: list[str] = []
    for role in access_roles:
        roles.extend(part.strip() for part in role.split(",") if part.strip())

    return roles or ["user"]


@router.post("/ingest")
@limiter.limit("5/minute")
def ingest(request: Request, body: IngestRequest):
    if DISABLE_INGEST:
        raise HTTPException(
            status_code=403, detail="Ingest endpoint is disabled in this environment."
        )

    return ingest_document(text=body.text, doc_type=body.doc_type, access_roles=body.access_roles)


@router.post("/ingest/upload", status_code=202)
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    response: Response,
    fingerprint_service: Annotated[FileFingerprintService, Depends(get_file_fingerprint_service)],
    ingestion_service: Annotated[FileIngestionService, Depends(get_file_ingestion_service)],
    file: Annotated[UploadFile | None, File()] = None,
    doc_type: Annotated[str, Form()] = "general",
    access_roles: Annotated[list[str] | None, Form()] = None,
    document_id: Annotated[UUID | None, Form()] = None,
    force_reindex: Annotated[bool, Form()] = False,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if DISABLE_INGEST:
        raise HTTPException(
            status_code=403, detail="Ingest endpoint is disabled in this environment."
        )
    require_ingest_api_key(x_api_key)

    if file is None:
        raise HTTPException(status_code=400, detail="PDF file is required.")

    original_filename = Path(file.filename or "").name
    if Path(original_filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Uploaded file must have a .pdf extension.")

    if file.content_type and file.content_type != PDF_CONTENT_TYPE:
        raise HTTPException(
            status_code=400, detail="Uploaded file content type must be application/pdf."
        )

    upload_id = str(uuid.uuid4())
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{upload_id}.pdf"
    max_upload_bytes = get_max_upload_bytes()

    bytes_written = 0
    with upload_path.open("wb") as output:
        while chunk := await file.read(UPLOAD_CHUNK_SIZE):
            bytes_written += len(chunk)
            if bytes_written > max_upload_bytes:
                output.close()
                upload_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file exceeds maximum size.")
            output.write(chunk)

    if bytes_written == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="PDF file is required.")

    logger.info("fingerprint_calculation_started", extra={"file_size_bytes": bytes_written})
    try:
        with upload_path.open("rb") as source:
            fingerprint = fingerprint_service.calculate_sha256(source)
    except OSError as exc:
        logger.exception("fingerprint_calculation_failed")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ingestion_source_unavailable",
                "message": "The uploaded source could not be read.",
            },
        ) from exc
    if fingerprint.file_size_bytes != bytes_written:
        logger.error(
            "fingerprint_calculation_failed",
            extra={"file_size_bytes": fingerprint.file_size_bytes},
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ingestion_source_changed",
                "message": "The uploaded source changed while its integrity was verified.",
            },
        )
    logger.info(
        "fingerprint_calculation_completed",
        extra={
            "checksum_algorithm": fingerprint.algorithm,
            "file_size_bytes": fingerprint.file_size_bytes,
        },
    )

    roles = tuple(parse_access_roles(access_roles))
    try:
        result = ingestion_service.submit(
            FileIngestionRequest(
                document_id=str(document_id) if document_id else None,
                doc_type=doc_type,
                access_roles=roles,
                upload_path=str(upload_path),
                original_filename=original_filename,
                mime_type=PDF_CONTENT_TYPE,
                fingerprint=fingerprint,
                checksum_calculated_at=datetime.now(timezone.utc),
                force_reindex=force_reindex,
                idempotency_key=idempotency_key,
            )
        )
    except InvalidFileIdempotencyKey as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_idempotency_key", "message": str(exc)},
        ) from exc
    except IdempotentFileRequestConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "idempotency_key_conflict", "message": str(exc)},
        ) from exc
    except FileIngestionUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ingestion_deduplication_conflict",
                "message": "File ingestion is temporarily unavailable.",
            },
        ) from exc

    response.status_code = 202 if result.ingestion_required else 200

    return {
        "document_id": result.document_id,
        "job_id": str(result.ingestion_job_id),
        "ingestion_job_id": str(result.ingestion_job_id),
        "filename": original_filename,
        "status": "queued" if result.ingestion_required else "deduplicated",
        "next_stage": "validate" if result.ingestion_required else None,
        "content_status": result.content_status.value,
        "deduplicated": result.deduplicated,
        "ingestion_required": result.ingestion_required,
        "ingestion_in_progress": result.ingestion_in_progress,
        "force_reindex": result.force_reindex,
    }


@router.get("/chunks")
def get_chunks():
    return list_chunks()


class SearchRequest(BaseModel):
    query: str = Query(..., description="Search query")
    access_role: str = Query("user", description="Access role for filtering results")
