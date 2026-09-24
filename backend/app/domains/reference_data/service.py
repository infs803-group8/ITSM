"""Reference data and vendor directory services."""

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.enums import (
    AttachmentVisibility,
    Category,
    CommentVisibility,
    Priority,
    TicketStatus,
    UserRole,
)
from app.core.errors import ApplicationError
from app.domains.reference_data.repository import ReferenceDataRepository
from app.domains.reference_data.schema import (
    AttachmentConfig,
    AttachmentTypeRule,
    ReferenceData,
    ReferenceDataResponse,
    TimerConfig,
    VendorListResponse,
    VendorOrganisation,
)


class ReferenceDataService:
    def __init__(self, database: Session) -> None:
        self.repository = ReferenceDataRepository(database)

    def get_reference_data(self, actor: RequestContext) -> ReferenceDataResponse:
        config, allowed = self.repository.reference_data()
        engineer_or_manager = actor.role in {
            UserRole.ENGINEER_TIER1,
            UserRole.ENGINEER_TIER2,
            UserRole.SERVICE_DESK_MANAGER,
        }
        comment_visibilities = (
            []
            if actor.role == UserRole.EXTERNAL_VENDOR
            else [CommentVisibility.USER_VISIBLE]
        )
        attachment_visibilities = (
            [AttachmentVisibility.VENDOR_SHARED]
            if actor.role == UserRole.EXTERNAL_VENDOR
            else [AttachmentVisibility.USER_VISIBLE]
        )
        if engineer_or_manager:
            comment_visibilities.append(CommentVisibility.INTERNAL_ONLY)
            attachment_visibilities.append(AttachmentVisibility.INTERNAL_ONLY)
        if actor.role in {UserRole.ENGINEER_TIER2, UserRole.SERVICE_DESK_MANAGER}:
            attachment_visibilities.append(AttachmentVisibility.VENDOR_SHARED)
        statuses = list(TicketStatus)
        if actor.role == UserRole.USER:
            statuses.remove(TicketStatus.PENDING_VENDOR)
        return ReferenceDataResponse(
            data=ReferenceData(
                categories=list(Category),
                priorities=list(Priority),
                ticket_statuses=statuses,
                comment_visibilities=comment_visibilities,
                attachment_visibilities=attachment_visibilities,
                attachment=AttachmentConfig(
                    max_size_bytes=int(config["attachment_max_size_bytes"]),
                    upload_url_ttl_seconds=int(config["upload_url_ttl_seconds"]),
                    download_url_ttl_seconds=int(config["download_url_ttl_seconds"]),
                    allowed_types=[AttachmentTypeRule(**row) for row in allowed],
                ),
                timers=TimerConfig(
                    engineering_sla_hours=int(config["engineering_sla_hours"]),
                    at_risk_percent=int(config["at_risk_percent"]),
                    user_response_hours=int(config["user_response_hours"]),
                    resolved_window_hours=int(config["resolved_window_hours"]),
                ),
            )
        )

    def list_vendors(
        self,
        actor: RequestContext,
        *,
        page: int,
        page_size: int,
        search: str | None,
        is_active: bool | None,
    ) -> VendorListResponse:
        if actor.role not in {UserRole.ENGINEER_TIER2, UserRole.SERVICE_DESK_MANAGER}:
            raise ApplicationError(
                "DATA_SCOPE_DENIED", "Vendor directory access is not permitted.", 403
            )
        rows, total = self.repository.list_vendors(
            page=page, page_size=page_size, search=search, is_active=is_active
        )
        return VendorListResponse(
            data=[VendorOrganisation(**row) for row in rows],
            meta=PaginationMeta.from_total(page=page, page_size=page_size, total=total),
        )
