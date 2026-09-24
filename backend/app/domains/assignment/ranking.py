"""Pure candidate ranking for initial auto-assignment (C022.01/.02/.03).

Kept separate from ``repository.py``/``service.py`` for the same reason as
``workflow/state_machine.py`` and ``workflow/serializer.py``: this is the one
piece of C022 with no SQLAlchemy/Pydantic/HTTP dependency, so it is the one
piece that can actually be *executed* (not merely syntax-checked) in an
environment without third-party packages.

The SQL in ``AssignmentRepository.list_candidate_engineers`` already applies
the eligibility filter from C022.01 (ACTIVE, ``is_available = 1``, Tier 1
only, skill match on the ticket's category); ``rank_candidates`` is the
authoritative order (belt-and-suspenders -- it does not trust that every
future caller of the repository method preserves a particular row order,
e.g. after the rows pass through a cache or a test double) and is what
``AssignmentService.assign_new_ticket`` actually calls to pick a winner.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candidate:
    """One Tier 1 engineer eligible for this ticket's category.

    ``active_load`` must already be computed per C022.02: only tickets
    currently ``ASSIGNED``, ``IN_PROGRESS``, ``PENDING_VENDOR`` or
    ``REOPENED`` and assigned to this engineer count -- ``PENDING_USER``,
    ``RESOLVED`` and ``CLOSED`` do not (a ticket waiting on the requester,
    or already wrapped up, is not consuming this engineer's attention right
    now). Deliberately not the same set dashboard/repository.py uses for
    its own, differently-scoped "current load" display column.
    """

    user_id: int
    active_load: int
    last_assigned_at: datetime | None


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """C022.03: active_load ASC, then last_assigned_at ASC with NULL first
    (never-yet-assigned engineers go before anyone with a real timestamp,
    so a fresh Tier 1 hire is not perpetually skipped by a low-load
    colleague with a stale non-null timestamp), then user_id ASC to make
    the order fully deterministic when both of the above tie.
    """
    return sorted(
        candidates,
        key=lambda c: (
            c.active_load,
            0 if c.last_assigned_at is None else 1,
            c.last_assigned_at or datetime.min,
            c.user_id,
        ),
    )


def pick_winner(candidates: list[Candidate]) -> Candidate | None:
    """C022.05: an empty candidate list is a legitimate "no eligible
    engineer" outcome, not an error -- the caller (AssignmentService) is
    responsible for keeping that outcome distinct from a database error,
    which must propagate rather than being swallowed into a fake ``None``.
    """
    ranked = rank_candidates(candidates)
    return ranked[0] if ranked else None
