import pytest
from pydantic import ValidationError

from app.domains.tickets.schema import TicketCreateRequest, TicketUpdateRequest


def test_ticket_create_trims_text_and_rejects_extra_fields():
    request = TicketCreateRequest(
        title="  VPN issue  ",
        description="  Cannot connect  ",
        category="NETWORK",
        priority="HIGH",
    )
    assert request.title == "VPN issue"
    assert request.description == "Cannot connect"
    with pytest.raises(ValidationError):
        TicketCreateRequest(
            title="VPN",
            description="Broken",
            category="NETWORK",
            priority="HIGH",
            status="CLOSED",
        )


@pytest.mark.parametrize("payload", [{}, {"title": None}, {"description": "   "}])
def test_ticket_update_requires_a_non_null_non_blank_field(payload):
    with pytest.raises(ValidationError):
        TicketUpdateRequest(**payload)

