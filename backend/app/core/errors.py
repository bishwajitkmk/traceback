"""Consistent error envelope: {"error": {"code", "message", "details"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Raise from services; translated into the error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


class NotFound(AppError):
    def __init__(self, resource: str = "resource") -> None:
        # Same response whether the resource is missing or belongs to another project,
        # so UUIDs from other projects cannot be probed.
        super().__init__(404, "not_found", f"The requested {resource} was not found.")


class ValidationFailed(AppError):
    """A business-rule validation error on one request-body field."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(
            422,
            "validation_error",
            "Request validation failed.",
            details=[FieldError(field=f"body.{field}", message=message)],
        )


class RateLimited(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            429,
            "rate_limited",
            "Too many requests. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


def _envelope(
    status_code: int, body: ErrorBody, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=body).model_dump(exclude_none=True),
        headers=headers,
    )


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
}


def _clean_message(msg: str) -> str:
    # Pydantic prefixes custom validator messages with "Value error, ".
    return msg.removeprefix("Value error, ")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        body = ErrorBody(code=exc.code, message=exc.message, details=exc.details)
        return _envelope(exc.status_code, body, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, ErrorBody(code=code, message=str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            FieldError(
                field=".".join(str(p) for p in err["loc"]), message=_clean_message(err["msg"])
            )
            for err in exc.errors()
        ]
        body = ErrorBody(
            code="validation_error", message="Request validation failed.", details=details
        )
        return _envelope(422, body)


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` helper documenting the error envelope."""
    return {code: {"model": ErrorResponse} for code in status_codes}
