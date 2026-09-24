"""Role-specific reference-data coverage."""

from app.common.request_context import RequestContext
from app.core.enums import TicketStatus, UserRole
from app.domains.reference_data.service import ReferenceDataService


def test_vendor_only_receives_vendor_visible_ticket_statuses():
    service = ReferenceDataService(object())
    service.repository.reference_data = lambda: (
        {
            "attachment_max_size_bytes": 10_485_760,
            "upload_url_ttl_seconds": 900,
            "download_url_ttl_seconds": 300,
            "engineering_sla_hours": 48,
            "at_risk_percent": 80,
            "user_response_hours": 120,
            "resolved_window_hours": 168,
        },
        [],
    )

    response = service.get_reference_data(
        RequestContext(
            user_id=50,
            role=UserRole.EXTERNAL_VENDOR,
            vendor_org_id=7,
        )
    )

    assert response.data.ticket_statuses == [
        TicketStatus.IN_PROGRESS,
        TicketStatus.PENDING_VENDOR,
        TicketStatus.CLOSED,
    ]
