"""Initial ticket assignment contract.

Implemented by app.domains.assignment.service.AssignmentService (C022).

The scaffold originally typed the second parameter ``category_id: int``,
but ``categories`` (backend/database/schema.sql) has no numeric surrogate
key -- ``category_code`` (VARCHAR, e.g. "NETWORK") is the table's actual
primary key, and it is what every other C module (workflow, sla, audit)
already treats as the category identifier. Fixed here rather than left
inconsistent with the schema this contract is meant to describe; flagged
for B/D awareness since this file is a cross-domain contract, not
something owned by C alone.
"""

from typing import Protocol


class InitialAssignmentService(Protocol):
    def assign_new_ticket(self, *, ticket_id: int, category_code: str) -> int | None: ...
