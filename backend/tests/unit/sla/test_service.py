from datetime import UTC, datetime

from app.domains.sla.cycle import SlaConfig
from app.domains.sla.service import SlaCycleService

CONFIG = SlaConfig(engineering_sla_hours=48, at_risk_percent=80)
NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)


class RepositoryFake:
    def __init__(self):
        self.apply_calls: list[dict] = []
        self.status_calls: list[tuple[int, str]] = []

    def apply_cycle_window(self, ticket_id, window, *, sla_status):
        self.apply_calls.append(
            {"ticket_id": ticket_id, "window": window, "sla_status": sla_status}
        )

    def mark_sla_status(self, ticket_id, sla_status):
        self.status_calls.append((ticket_id, sla_status))


class AuditFake:
    def __init__(self):
        self.events: list[dict] = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)


def sla_service() -> tuple[SlaCycleService, RepositoryFake, AuditFake]:
    service = SlaCycleService(None)
    repository = RepositoryFake()
    audit = AuditFake()
    service.repository = repository
    service.audit = audit
    return service, repository, audit


def test_start_first_cycle_writes_cycle_one_and_an_sla_cycle_started_event():
    service, repository, audit = sla_service()
    window = service.start_first_cycle(ticket_id=5001, actor_id=None, now=NOW, config=CONFIG)
    assert window.cycle_no == 1
    assert repository.apply_calls[0]["sla_status"] == "ON_TRACK"
    assert audit.events[0]["event_type"].value == "SLA_CYCLE_STARTED"
    assert audit.events[0]["cycle_no"] == 1


def test_start_new_cycle_increments_and_resets_status_to_on_track():
    service, repository, audit = sla_service()
    window = service.start_new_cycle(
        ticket_id=5001, previous_cycle_no=2, actor_id=1001, now=NOW, config=CONFIG
    )
    assert window.cycle_no == 3
    assert repository.apply_calls[0]["sla_status"] == "ON_TRACK"
    assert audit.events[0]["actor_id"] == 1001


def test_pause_current_cycle_does_not_touch_the_cycle_window():
    service, repository, audit = sla_service()
    service.pause_current_cycle(ticket_id=5001, cycle_no=1, actor_id=2001)
    assert repository.apply_calls == []
    assert repository.status_calls == [(5001, "PAUSED")]
    assert audit.events[0]["event_type"].value == "SLA_PAUSED"


def test_mark_overdue_is_system_generated():
    service, repository, audit = sla_service()
    service.mark_overdue(ticket_id=5001, cycle_no=1)
    assert repository.status_calls == [(5001, "OVERDUE")]
    assert audit.events[0]["actor_id"] is None
    assert audit.events[0]["event_type"].value == "SLA_OVERDUE"


def test_mark_at_risk_is_system_generated():
    service, repository, audit = sla_service()
    service.mark_at_risk(ticket_id=5001, cycle_no=1)
    assert repository.status_calls == [(5001, "AT_RISK")]
    assert audit.events[0]["event_type"].value == "SLA_AT_RISK"


def test_mark_met_records_the_actor_who_submitted_the_resolution():
    service, repository, audit = sla_service()
    service.mark_met(ticket_id=5001, cycle_no=1, actor_id=2001)
    assert repository.status_calls == [(5001, "MET")]
    assert audit.events[0]["actor_id"] == 2001
