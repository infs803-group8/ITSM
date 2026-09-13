from datetime import UTC, datetime, timedelta

from app.domains.workflow.deadline_service import (
    DeadlineService,
    PendingUserSnapshot,
    ResolvedSnapshot,
)
from app.domains.workflow.state_machine import PendingUserReason, ResolutionType

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)


class RepositoryFake:
    def __init__(self):
        self.auto_resolve_calls: list[dict] = []
        self.auto_close_calls: list[dict] = []

    def apply_auto_resolution(self, **kwargs):
        self.auto_resolve_calls.append(kwargs)

    def apply_auto_close(self, **kwargs):
        self.auto_close_calls.append(kwargs)


class AuditFake:
    def __init__(self):
        self.events: list[dict] = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)


def deadline_service() -> tuple[DeadlineService, RepositoryFake, AuditFake]:
    service = DeadlineService(None)
    repository = RepositoryFake()
    audit = AuditFake()
    service.repository = repository
    service.audit = audit
    return service, repository, audit


def pending_snapshot(**overrides) -> PendingUserSnapshot:
    values = dict(
        ticket_id=5001,
        pending_user_reason=PendingUserReason.INFORMATION_REQUIRED,
        pending_user_deadline=NOW,
        resolution_summary=None,
        assignee_id=2001,
    )
    values.update(overrides)
    return PendingUserSnapshot(**values)


def test_before_the_deadline_nothing_is_written():
    service, repository, audit = deadline_service()
    result = service.check_pending_user_timeout(
        pending_snapshot(pending_user_deadline=NOW + timedelta(hours=1)),
        now=NOW,
        resolved_window_hours=168,
    )
    assert result.applied is False
    assert repository.auto_resolve_calls == []
    assert audit.events == []


def test_information_required_timeout_writes_auto_no_user_response():
    service, repository, audit = deadline_service()
    result = service.check_pending_user_timeout(
        pending_snapshot(pending_user_reason=PendingUserReason.INFORMATION_REQUIRED),
        now=NOW,
        resolved_window_hours=168,
    )
    assert result.applied
    assert result.resolution_type == ResolutionType.AUTO_NO_USER_RESPONSE
    assert result.auto_close_at == NOW + timedelta(days=7)
    call = repository.auto_resolve_calls[0]
    assert call["resolution_type"] == ResolutionType.AUTO_NO_USER_RESPONSE
    assert "automatically resolved" in call["resolution_summary"]
    assert audit.events[0]["event_type"].value == "AUTO_RESOLVED_NO_USER_RESPONSE"


def test_resolution_confirmation_timeout_keeps_the_engineers_summary():
    service, repository, audit = deadline_service()
    result = service.check_pending_user_timeout(
        pending_snapshot(
            pending_user_reason=PendingUserReason.RESOLUTION_CONFIRMATION,
            resolution_summary="Replaced the faulty network cable.",
        ),
        now=NOW,
        resolved_window_hours=168,
    )
    assert result.applied
    assert result.resolution_type == ResolutionType.AUTO_CONFIRMATION_TIMEOUT
    call = repository.auto_resolve_calls[0]
    assert call["resolution_summary"] == "Replaced the faulty network cable."
    assert audit.events[0]["event_type"].value == "RESOLUTION_CONFIRMATION_TIMEOUT"


def test_auto_resolve_sets_last_resolved_assignee_from_the_snapshot():
    service, repository, _audit = deadline_service()
    service.check_pending_user_timeout(
        pending_snapshot(assignee_id=3003), now=NOW, resolved_window_hours=168
    )
    assert repository.auto_resolve_calls[0]["last_resolved_assignee_id"] == 3003


def test_before_auto_close_at_nothing_is_written():
    service, repository, audit = deadline_service()
    result = service.check_resolved_auto_close_timeout(
        ResolvedSnapshot(ticket_id=5001, auto_close_at=NOW + timedelta(hours=1)), now=NOW
    )
    assert result.applied is False
    assert repository.auto_close_calls == []
    assert audit.events == []


def test_auto_close_at_or_after_the_window_closes_the_ticket():
    service, repository, audit = deadline_service()
    result = service.check_resolved_auto_close_timeout(
        ResolvedSnapshot(ticket_id=5001, auto_close_at=NOW), now=NOW
    )
    assert result.applied
    assert result.closed_at == NOW
    assert repository.auto_close_calls[0]["ticket_id"] == 5001
    assert audit.events[0]["event_type"].value == "TICKET_CLOSED_AUTO"
    assert audit.events[0]["actor_id"] is None
