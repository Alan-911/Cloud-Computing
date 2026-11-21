from fastapi import APIRouter, Response, status

from app.api.deps import DatabaseDep, SettingsDep
from app.schemas.common import HealthResponse, LivenessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness",
    description="The process is up. Does not touch the database, so a database outage "
    "does not cause restarts.",
)
def live() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "",
    response_model=HealthResponse,
    summary="Readiness",
    description="Version and database reachability. Returns 503 when the database does "
    "not answer, so load balancers stop routing to this instance. "
    "Also served at `/health/ready`.",
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
@router.get("/ready", response_model=HealthResponse, include_in_schema=False)
def ready(settings: SettingsDep, db: DatabaseDep, response: Response) -> HealthResponse:
    db_ok = db.ping()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=settings.version,
        environment=settings.environment,
        database="ok" if db_ok else "unavailable",
    )
