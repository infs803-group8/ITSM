"""Unit tests for app.domains.sla.service.SlaCycleService.evaluate_threshold_scan
(C035).

Same fake-repository/audit pattern as tests/unit/sla/test_service.py, but
this method calls three repository reads too (get_cycle_state,
get_config), so RepositoryFake grows those alongside the existing
write-tracking fields.
"""

from datetime import UTC, datetime, timedelta

from app.domains.sla.cycle import SlaConfig
from app.domains.sla.service import SlaCycleService, ThresholdScanOutcome

CONFIG = SlaConfig(engineering_sla_hours=48, at_risk_percent=80)
STARTED_AT = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
AT_RISK_AT = STARTED_AT + timedelta(hours=38, minutes=24)  # 80% of 48h
DEADLINE = STARTED_AT + timedelta(hours=48)


class RepositoryFake:
    def __init__(self, *, row, config=CONFIG):
        self.row = row
        self.config = config
        self.status_calls: list[tuple[int, str]] = []
        self.locked_ticket_ids: list[int] = []

    def get_cycle_state(self, ticket_id, *, for_update=False):
        assert for_update is True
        self.locked_ticket_ids.append(ticket_id)
        return self.row

    def get_config(self):
        return self.config

    def mark_sla_status(self, ticket_id, sla_status):
        self.status_calls.append((ticket_id, sla_status))


class AuditFake:
    def __init__(self):
        self.events: list[dict] = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)


def scan_row(**overrides):
    row = {
        "ticket_id": 7001,
        "status_code": "IN_PROGRESS",
        "sla_cycle_no": 1,
        "sla_status_code": "ON_TRACK",
        "sla_started_at": STARTED_AT,
        "sla_deadline": DEADLINE,
    }
    row.update(overrides)
    return row


def sla_service(row) -> tuple[SlaCycleService, RepositoryFake, AuditFake]:
    service = SlaCycleService(None)
    repository = RepositoryFake(row=row)
    audit = AuditFake()
    service.repository = repository
    service.audit = audit
    return service, repository, audit


def test_before_either_threshold_is_a_no_op():
    service, repository, audit = sla_service(scan_row())
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=STARTED_AT + timedelta(hours=10))
    assert outcome is None
    assert repository.status_calls == []
    assert audit.events == []
    assert repository.locked_ticket_ids == [7001]


def test_crossing_the_80_percent_mark_writes_at_risk_only():
    service, repository, audit = sla_service(scan_row())
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=AT_RISK_AT)
    assert outcome == ThresholdScanOutcome(
        ticket_id=7001, cycle_no=1, new_sla_status="AT_RISK", backfilled_at_risk=False
    )
    assert repository.status_calls == [(7001, "AT_RISK")]
    assert len(audit.events) == 1
    assert audit.events[0]["event_type"].value == "SLA_AT_RISK"
    assert audit.events[0]["actor_id"] is None


def test_at_risk_uses_greater_than_or_equal_at_the_exact_boundary():
    service, repository, audit = sla_service(scan_row())
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=AT_RISK_AT)
    assert outcome.new_sla_status == "AT_RISK"


def test_crossing_the_deadline_from_already_at_risk_writes_overdue_only():
    service, repository, audit = sla_service(scan_row(sla_status_code="AT_RISK"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE)
    assert outcome == ThresholdScanOutcome(
        ticket_id=7001, cycle_no=1, new_sla_status="OVERDUE", backfilled_at_risk=False
    )
    assert repository.status_calls == [(7001, "OVERDUE")]
    assert len(audit.events) == 1
    assert audit.events[0]["event_type"].value == "SLA_OVERDUE"


def test_a_late_scan_that_skips_straight_from_on_track_to_overdue_backfills_at_risk():
    """Q09 / C035.04: the job missed every run between 80% and 100% --
    both events are written, in order, in the same pass, and neither
    carries a fabricated occurred_at (that's the DB column default's job,
    not this method's -- see the two mark_* calls it delegates to).
    """
    service, repository, audit = sla_service(scan_row(sla_status_code="ON_TRACK"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE + timedelta(hours=5))
    assert outcome == ThresholdScanOutcome(
        ticket_id=7001, cycle_no=1, new_sla_status="OVERDUE", backfilled_at_risk=True
    )
    assert repository.status_calls == [(7001, "AT_RISK"), (7001, "OVERDUE")]
    assert [event["event_type"].value for event in audit.events] == ["SLA_AT_RISK", "SLA_OVERDUE"]


def test_a_ticket_that_is_pending_user_does_not_accrue_engineering_overdue():
    service, repository, audit = sla_service(
        scan_row(status_code="PENDING_USER", sla_status_code="PAUSED")
    )
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE + timedelta(days=30))
    assert outcome is None
    assert repository.status_calls == []
    assert audit.events == []


def test_a_resolved_ticket_is_never_rescanned():
    service, repository, audit = sla_service(scan_row(status_code="RESOLVED", sla_status_code="MET"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE + timedelta(days=1))
    assert outcome is None
    assert repository.status_calls == []


def test_a_closed_ticket_is_never_rescanned():
    service, repository, audit = sla_service(scan_row(status_code="CLOSED", sla_status_code="MET"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE + timedelta(days=1))
    assert outcome is None
    assert repository.status_calls == []


def test_a_ticket_already_overdue_is_not_rescanned_even_well_past_the_deadline():
    """Old-cycle / rerun safety (C035.06): once OVERDUE is recorded, a
    second pass over the same still-current cycle must be a pure no-op --
    the DB's uq_ticket_events_cycle_guard is the last-resort backstop,
    but re-validation here is what actually keeps job re-runs quiet.
    """
    service, repository, audit = sla_service(scan_row(sla_status_code="OVERDUE"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE + timedelta(days=3))
    assert outcome is None
    assert repository.status_calls == []
    assert audit.events == []


def test_a_paused_ticket_is_not_a_scan_candidate_even_if_its_old_deadline_has_passed():
    """Request Info paused the cycle -- schema.sql's sla_deadline column
    still holds whatever it was at pause time, but PAUSED means the
    engineering clock is not running, so no AT_RISK/OVERDUE should ever
    be written against it.
    """
    service, repository, audit = sla_service(scan_row(sla_status_code="PAUSED"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE + timedelta(days=1))
    assert outcome is None
    assert repository.status_calls == []


def test_reopened_tickets_are_scanned_against_their_own_fresh_cycle():
    """C035.01 explicitly includes REOPENED among the active statuses --
    Reopen (C033) always starts cycle_no + 1 with a fresh sla_started_at,
    so this is exactly the same on_track-then_at_risk arithmetic as any
    other active status, just confirming REOPENED is not excluded.
    """
    service, repository, audit = sla_service(scan_row(status_code="REOPENED", sla_cycle_no=2))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=AT_RISK_AT)
    assert outcome.new_sla_status == "AT_RISK"
    assert outcome.cycle_no == 2


def test_an_unassigned_ticket_still_accrues_engineering_sla_from_creation():
    service, repository, audit = sla_service(scan_row(status_code="UNASSIGNED"))
    outcome = service.evaluate_threshold_scan(ticket_id=7001, now=DEADLINE)
    assert outcome.new_sla_status == "OVERDUE"
    assert outcome.backfilled_at_risk is True


def test_a_missing_ticket_returns_none_rather_than_raising():
    service = SlaCycleService(None)
    service.repository = RepositoryFake(row=None)
    service.audit = AuditFake()
    outcome = service.evaluate_threshold_scan(ticket_id=9999, now=STARTED_AT)
    assert outcome is None
