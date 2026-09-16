"""Unit tests for app.domains.assignment.service.AssignmentService (C022).

Same fake-repository pattern as tests/unit/sla/test_service.py. This module
imports app.domains.assignment.repository, which imports SQLAlchemy, so
(per this project's established convention) it is syntax-checked only
(py_compile) in an environment without pip access, not executed.
"""

from datetime import UTC, datetime

from app.domains.assignment.service import AssignmentService

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)


class RepositoryFake:
    def __init__(self, candidate_rows):
        self.candidate_rows = candidate_rows
        self.locked = False
        self.requested_category_codes: list[str] = []
        self.mark_last_assigned_calls: list[dict] = []

    def lock_assignment_control(self):
        self.locked = True

    def list_candidate_engineers(self, category_code):
        self.requested_category_codes.append(category_code)
        return self.candidate_rows

    def mark_last_assigned(self, *, user_id, when):
        self.mark_last_assigned_calls.append({"user_id": user_id, "when": when})


def assignment_service(candidate_rows) -> tuple[AssignmentService, RepositoryFake]:
    service = AssignmentService(None)
    repository = RepositoryFake(candidate_rows)
    service.repository = repository
    return service, repository


def test_assign_new_ticket_locks_before_reading_candidates():
    service, repository = assignment_service(
        [{"user_id": 1, "active_load": 0, "last_assigned_at": None}]
    )
    service.assign_new_ticket(ticket_id=42, category_code="NETWORK")
    assert repository.locked is True
    assert repository.requested_category_codes == ["NETWORK"]


def test_assign_new_ticket_returns_the_lowest_load_candidate():
    service, repository = assignment_service(
        [
            {"user_id": 1, "active_load": 3, "last_assigned_at": None},
            {"user_id": 2, "active_load": 1, "last_assigned_at": None},
        ]
    )
    winner = service.assign_new_ticket(ticket_id=42, category_code="HARDWARE")
    assert winner == 2
    assert repository.mark_last_assigned_calls == [
        {"user_id": 2, "when": repository.mark_last_assigned_calls[0]["when"]}
    ]


def test_assign_new_ticket_marks_only_the_winner_as_last_assigned():
    service, repository = assignment_service(
        [
            {"user_id": 1, "active_load": 0, "last_assigned_at": None},
            {"user_id": 2, "active_load": 5, "last_assigned_at": None},
        ]
    )
    winner = service.assign_new_ticket(ticket_id=1, category_code="SOFTWARE")
    assert winner == 1
    assert len(repository.mark_last_assigned_calls) == 1
    assert repository.mark_last_assigned_calls[0]["user_id"] == 1


def test_assign_new_ticket_returns_none_and_writes_nothing_when_no_candidates():
    service, repository = assignment_service([])
    winner = service.assign_new_ticket(ticket_id=1, category_code="ACCOUNT")
    assert winner is None
    assert repository.mark_last_assigned_calls == []
