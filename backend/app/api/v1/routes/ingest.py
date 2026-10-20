from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deps import get_api_key_project
from app.core.errors import AppError, error_responses
from app.core.ratelimit import ingest_limiter
from app.db.session import get_db
from app.models import Project
from app.schemas.ingest import IngestEvent, IngestResult
from app.services.ingestion import ingest

router = APIRouter(tags=["ingestion"])


@router.post(
    "/ingest/events",
    response_model=IngestResult,
    status_code=202,
    responses=error_responses(401, 413, 422, 429),
    openapi_extra={
        "requestBody": {
            "content": {"application/json": {"schema": IngestEvent.model_json_schema()}}
        }
    },
)
async def ingest_event(
    request: Request, project: Project = Depends(get_api_key_project), db: Session = Depends(get_db)
) -> IngestResult:
    """Accept one event from an SDK. Authenticated by the project API key."""
    ingest_limiter.hit(str(project.id))
    # Enforce the size limit before parsing, reading at most limit + 1 bytes.
    limit = get_settings().max_event_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise AppError(413, "payload_too_large", f"Events are limited to {limit} bytes.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise AppError(413, "payload_too_large", f"Events are limited to {limit} bytes.")
    try:
        event = IngestEvent.model_validate_json(bytes(raw))
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from None

    # Database work is synchronous; keep it off the event loop.
    return await run_in_threadpool(_persist, db, project, event)


def _persist(db: Session, project: Project, event: IngestEvent) -> IngestResult:
    result = ingest(db, project, event)
    db.commit()
    return result
