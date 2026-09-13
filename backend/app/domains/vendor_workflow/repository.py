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
