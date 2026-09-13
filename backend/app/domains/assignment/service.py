"""Initial auto-assignment service (C022).

Implements ``app.contracts.initial_assignment.InitialAssignmentService``.
Only chooses an assignee; it never writes the ticket row itself (status,
``assignee_id``, the first SLA cycle, or the ``TICKET_CREATED``/
``AUTO_ASSIGNED`` audit events all stay the create-ticket transaction's
job -- that wiring is C023, into Member B's API-15 handler). Keeping this
service scoped to selection alone lets C023 call it from inside whatever
shape B's create-ticket transaction ends up taking, without this service
assuming it.
"""

from app.core.clock import utc_now
from app.domains.assignment.ranking import Candidate, pick_winner
from app.domains.assignment.repository import AssignmentRepository


class AssignmentService:
    def __init__(self, database) -> None:
        self.database = database
        self.repository = AssignmentRepository(database)

    def assign_new_ticket(self, *, ticket_id: int, category_code: str) -> int | None:
        """C022.04: lock the ``assignment_control`` singleton first, then
        read candidates and update the winner's ``last_assigned_at``
        inside that same locked transaction -- the caller commits.

        ``ticket_id`` is accepted (and not otherwise used) purely to match
        the frozen ``InitialAssignmentService`` Protocol signature; the
        selection algorithm itself only needs the category.

        Returns ``None`` only for a genuine "no eligible engineer" outcome
        (C022.05) -- a database error propagates as an exception rather
        than being disguised as a normal ``None``/UNASSIGNED result.
        """
        self.repository.lock_assignment_control()
        rows = self.repository.list_candidate_engineers(category_code)
        candidates = [
            Candidate(
                user_id=row["user_id"],
                active_load=row["active_load"],
                last_assigned_at=row["last_assigned_at"],
            )
            for row in rows
        ]
        winner = pick_winner(candidates)
        if winner is None:
            return None
        self.repository.mark_last_assigned(user_id=winner.user_id, when=utc_now())
        return winner.user_id
