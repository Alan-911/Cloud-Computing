from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["Item 42 was not found."])
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "unavailable"]


_DESCRIPTIONS = {
    404: "Resource not found",
    409: "Conflict with an existing resource",
    422: "Request validation failed",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` entries that document the error envelope."""
    return {
        c: {"model": ErrorResponse, "description": _DESCRIPTIONS.get(c, "Error")} for c in codes
    }
