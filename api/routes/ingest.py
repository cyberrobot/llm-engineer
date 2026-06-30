import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from api.core.rate_limit import limiter
from api.services.ingest_document import ingest_document
from api.services.storage import (
    create_ingestion_job,
    create_uploaded_document,
    list_all_chunks,
)

router = APIRouter()

DISABLE_INGEST = os.getenv("DISABLE_INGEST", "false").lower() == "true"
PDF_CONTENT_TYPE = "application/pdf"
UPLOAD_CHUNK_SIZE = 1024 * 1024


class IngestRequest(BaseModel):
    text: str
    doc_type: str = "general"
    access_roles: list[str] = ["user"]


def require_ingest_api_key(x_api_key: str | None):
    expected_api_key = os.getenv("INGEST_API_KEY") or os.getenv("ADMIN_API_KEY")
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


def get_max_upload_bytes() -> int:
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "25"))
    return max_upload_mb * 1024 * 1024


def get_upload_dir() -> Path:
    return Path(os.getenv("UPLOAD_DIR", "uploads"))


@router.post("/ingest")
@limiter.limit("5/minute")
def ingest(request: Request, body: IngestRequest):
    if DISABLE_INGEST:
        raise HTTPException(
            status_code=403, detail="Ingest endpoint is disabled in this environment."
        )

    return ingest_document(text=body.text, doc_type=body.doc_type, access_roles=body.access_roles)


@router.post("/ingest/upload")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    file: Annotated[UploadFile | None, File()] = None,
    doc_type: Annotated[str, Form()] = "general",
    access_roles: Annotated[list[str] | None, Form()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
):
    if DISABLE_INGEST:
        raise HTTPException(
            status_code=403, detail="Ingest endpoint is disabled in this environment."
        )
    require_ingest_api_key(x_api_key)

    if file is None:
        raise HTTPException(status_code=400, detail="PDF file is required.")

    original_filename = file.filename or ""
    if Path(original_filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Uploaded file must have a .pdf extension.")

    if file.content_type and file.content_type != PDF_CONTENT_TYPE:
        raise HTTPException(status_code=400, detail="Uploaded file content type must be application/pdf.")

    document_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    upload_dir = get_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{document_id}.pdf"
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

    roles = parse_access_roles(access_roles)
    create_uploaded_document(
        document_id,
        doc_type,
        roles,
        str(upload_path),
        original_filename,
    )
    create_ingestion_job(
        job_id,
        document_id,
        stage="validate",
        status="queued",
        progress=0,
    )

    return {
        "document_id": document_id,
        "job_id": job_id,
        "filename": original_filename,
        "status": "uploaded",
        "next_stage": "validate",
    }


@router.get("/chunks")
def get_chunks():
    return list_all_chunks()


class SearchRequest(BaseModel):
    query: str = Query(..., description="Search query")
    access_role: str = Query("user", description="Access role for filtering results")
