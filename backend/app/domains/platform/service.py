"""API-01 health readiness service."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.config import get_settings
from app.core.errors import ApplicationError
from app.domains.platform.schema import HealthChecks, HealthData, HealthResponse


class PlatformService:
    def health(self, database: Session) -> HealthResponse:
        try:
            database.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            database.rollback()
            raise ApplicationError(
                "SERVICE_UNAVAILABLE",
                "The backend database is not ready.",
                503,
            ) from exc

        settings = get_settings()
        return HealthResponse(
            data=HealthData(
                status="ok",
                service="it-service-desk-backend",
                version=settings.release_version,
                timestamp=utc_now(),
                checks=HealthChecks(database="ok"),
            )
        )
