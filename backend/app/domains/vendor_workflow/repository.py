"""Raw-SQL reads/writes for ``vendor_requests``/``vendor_organisations``
(C029 onward).

Same raw-SQL-against-the-physical-table pattern as every other C
repository, since Member B's ORM models don't exist yet. Scoped to the
two tables this domain owns outright; the ``tickets.status_code``
transition that goes with Request Vendor is still written through
``WorkflowRepository.apply_status_change`` (single-column update,
already built for C025's Start) rather than duplicated here.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.contracts.vendor_binding import ActiveVendorBinding


class VendorWorkflowRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_vendor_organisation(self, vendor_org_id: int) -> Mapping[str, Any] | None:
        """C029.02: does the target organisation even exist, and can it
        currently receive new requests. No row lock -- this is read-only
        reference data, not part of the ticket's own row lock.
        """
        return (
            self.database.execute(
                text(
                    "SELECT vendor_org_id, name, is_active "
                    "FROM vendor_organisations WHERE vendor_org_id = :vendor_org_id"
                ),
                {"vendor_org_id": vendor_org_id},
            )
            .mappings()
            .one_or_none()
        )

    def create_active_request(
        self,
        *,
        ticket_id: int,
        vendor_org_id: int,
        requested_by_id: int,
        vendor_message: str,
    ) -> int:
        """C029.03: insert the new ACTIVE request and return its id.

        Deliberately does not pre-check for an existing ACTIVE row itself
        -- ``state_machine``'s own ``has_active_vendor_request`` check
        (evaluated against the ticket row lock the caller already holds)
        is the ordinary-case guard, and schema.sql's
        ``uq_vendor_requests_one_active_per_ticket`` generated-column
        unique key is the final, race-proof guard for the C029.05
        two-concurrent-requests case: a second INSERT under that race
        raises ``IntegrityError``, which the caller (not this method)
        catches and translates -- this method never swallows or
        reinterprets a database error itself.
        """
        result = self.database.execute(
            text(
                """
                INSERT INTO vendor_requests
                    (ticket_id, vendor_org_id, requested_by_id, vendor_message, status)
                VALUES
                    (:ticket_id, :vendor_org_id, :requested_by_id, :vendor_message, 'ACTIVE')
                """
            ),
            {
                "ticket_id": ticket_id,
                "vendor_org_id": vendor_org_id,
                "requested_by_id": requested_by_id,
                "vendor_message": vendor_message,
            },
        )
        return int(result.lastrowid)

    def get_active_binding(self, *, ticket_id: int) -> ActiveVendorBinding | None:
        """Implements ``app.contracts.vendor_binding.VendorBindingReader``
        (C029.06) -- Member A's dashboard code (or any other future
        consumer) reads a ticket's current vendor binding through this
        method rather than querying ``vendor_requests`` directly.
        """
        row = (
            self.database.execute(
                text(
                    "SELECT vendor_request_id, vendor_org_id FROM vendor_requests "
                    "WHERE ticket_id = :ticket_id AND status = 'ACTIVE'"
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ActiveVendorBinding(
            vendor_request_id=int(row["vendor_request_id"]),
            vendor_org_id=int(row["vendor_org_id"]),
        )

    def mark_request_responded(self, *, vendor_request_id: int, responded_at: datetime) -> None:
        """C030.02: flip the ACTIVE request to RESPONDED. This clears
        ``active_ticket_guard`` (schema.sql: NULL unless status='ACTIVE'),
        which is what actually lets a future Request Vendor (C029) start
        a new ACTIVE request on this same ticket once it is back in
        IN_PROGRESS -- there is no separate "release the guard" step.
        """
        self.database.execute(
            text(
                "UPDATE vendor_requests "
                "SET status = 'RESPONDED', responded_at = :responded_at "
                "WHERE vendor_request_id = :vendor_request_id"
            ),
            {"vendor_request_id": vendor_request_id, "responded_at": responded_at},
        )

    def create_response(
        self, *, vendor_request_id: int, responder_id: int, message: str
    ) -> int:
        """C030.03: insert the one-and-only response row for this request
        -- schema.sql's ``uq_vendor_responses_request`` unique key means a
        second INSERT for the same ``vendor_request_id`` is itself
        impossible at the database level, on top of state_machine's own
        ``has_active_vendor_request`` check already refusing a second
        Vendor Response once the request is no longer ACTIVE.
        """
        result = self.database.execute(
            text(
                "INSERT INTO vendor_responses (vendor_request_id, responder_id, message) "
                "VALUES (:vendor_request_id, :responder_id, :message)"
            ),
            {
                "vendor_request_id": vendor_request_id,
                "responder_id": responder_id,
                "message": message,
            },
        )
        return int(result.lastrowid)
