from fastapi import APIRouter, Response, status

from app.api.deps import DatabaseDep, SettingsDep
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health",
    description="Reports version and whether the database answers. Returns 503 when it does not.",
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
def health(settings: SettingsDep, db: DatabaseDep, response: Response) -> HealthResponse:
    db_ok = db.ping()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=settings.version,
        environment=settings.environment,
        database="ok" if db_ok else "unavailable",
    )
