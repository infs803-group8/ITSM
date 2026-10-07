"""Cross-domain read of a ticket's current ACTIVE vendor binding.

C029.06: "safe internal interface for A to read the current Active Binding" -- Member A's
dashboard code (and any other future consumer) should read this through
the ``ActiveVendorBinding`` shape below rather than querying
``vendor_requests`` directly, so it never needs to know that table's
schema or its one-ACTIVE-per-ticket invariant.

Implemented by ``app.domains.vendor_workflow.repository.
VendorWorkflowRepository.get_active_binding``.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ActiveVendorBinding:
    vendor_request_id: int
    vendor_org_id: int


class VendorBindingReader(Protocol):
    def get_active_binding(self, *, ticket_id: int) -> ActiveVendorBinding | None: ...
