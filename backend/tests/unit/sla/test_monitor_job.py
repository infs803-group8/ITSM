"""Unit tests for app.domains.sla.monitor_job.SlaMonitorJob (C036).

Same fake-collaborator pattern as every other C service test: construct
the job with database=None, then replace its three internal
collaborators (.sla, .workflow_repository, .deadlines) with fakes before
calling run_once()/the private _scan_* methods. Imports sqlalchemy
transitively (via app.domains.sla.service), so syntax-checked only
(py_compile), not executed -- same sandbox limitation as every other
test file this stack has added.
"""

from datetime import UTC, datetime, timedelta

from app.domains.sla.cycle import SlaConfig
from app.domains.sla.monitor_job import CategoryCounts, SlaMonitorJob

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
CONFIG = SlaConfig(engineering_sla_hours=48, at_risk_percent=80)


def PENDING_USER_ROW(ticket_id: int) -> dict:
    """A row-shaped dict with every field PendingUserSnapshot.from_row reads."""
    return {
        "ticket_id": ticket_id,
        "pending_user_reason": "INFORMATION_REQUIRED",
        "pending_user_deadline": NOW - timedelta(hours=1),
        "resolution_summary": None,
        "assignee_id": 10,
    }


def RESOLVED_ROW(ticket_id: int) -> dict:
    """A row-shaped dict with every field ResolvedSnapshot.from_row reads."""
    return {"ticket_id": ticket_id, "auto_close_at": NOW - timedelta(hours=1)}


class DatabaseFake:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class SlaRepositoryFake:
    def __init__(self, *, pages: list[list[int]], resolved_window_hours: int = 168):
        self._pages = list(pages)
        self.resolved_window_hours = resolved_window_hours
        self.calls: list[dict] = []

    def get_threshold_scan_candidates(self, *, now, at_risk_cutoff, limit, after_ticket_id):
        self.calls.append({"now": now, "at_risk_cutoff": at_risk_cutoff, "after_ticket_id": after_ticket_id})
        if not self._pages:
            return []
        return self._pages.pop(0)

    def get_resolved_window_hours(self):
        return self.resolved_window_hours


class SlaServiceFake:
    def __init__(self, *, pages: list[list[int]] = (), outcomes: dict[int, object] | None = None):
        self.repository = SlaRepositoryFake(pages=list(pages))
        self.outcomes = outcomes or {}
        self.evaluated: list[int] = []

    def load_config(self):
        return CONFIG

    def evaluate_threshold_scan(self, *, ticket_id, now):
        self.evaluated.append(ticket_id)
        outcome = self.outcomes.get(ticket_id, "raise-if-missing")
        if outcome == "raise-if-missing":
            raise AssertionError(f"unexpected ticket_id {ticket_id}")
        return outcome


class WorkflowRepositoryFake:
    def __init__(
        self,
        *,
        pending_user_pages: list[list[int]] = (),
        auto_close_pages: list[list[int]] = (),
        pending_user_snapshots: dict[int, dict | None] | None = None,
        resolved_snapshots: dict[int, dict | None] | None = None,
    ):
        self._pending_user_pages = list(pending_user_pages)
        self._auto_close_pages = list(auto_close_pages)
        self.pending_user_snapshots = pending_user_snapshots or {}
        self.resolved_snapshots = resolved_snapshots or {}

    def get_pending_user_timeout_candidates(self, *, now, limit, after_ticket_id):
        if not self._pending_user_pages:
            return []
        return self._pending_user_pages.pop(0)

    def get_auto_close_candidates(self, *, now, limit, after_ticket_id):
        if not self._auto_close_pages:
            return []
        return self._auto_close_pages.pop(0)

    def get_pending_user_snapshot(self, ticket_id):
        return self.pending_user_snapshots.get(ticket_id)

    def get_resolved_snapshot(self, ticket_id):
        return self.resolved_snapshots.get(ticket_id)


class Outcome:
    def __init__(self, applied):
        self.applied = applied


class DeadlineServiceFake:
    def __init__(self, *, pending_user_outcomes=None, auto_close_outcomes=None):
        self.pending_user_outcomes = pending_user_outcomes or {}
        self.auto_close_outcomes = auto_close_outcomes or {}
        self.pending_user_calls: list[int] = []
        self.auto_close_calls: list[int] = []

    def check_pending_user_timeout(self, snapshot, *, now, resolved_window_hours):
        self.pending_user_calls.append(snapshot["ticket_id"])
        return self.pending_user_outcomes[snapshot["ticket_id"]]

    def check_resolved_auto_close_timeout(self, snapshot, *, now):
        self.auto_close_calls.append(snapshot["ticket_id"])
        return self.auto_close_outcomes[snapshot["ticket_id"]]


def job_with(*, sla=None, workflow_repository=None, deadlines=None, database=None):
    database = database or DatabaseFake()
    job = SlaMonitorJob(None)
    job.database = database
    job.sla = sla or SlaServiceFake()
    job.workflow_repository = workflow_repository or WorkflowRepositoryFake()
    job.deadlines = deadlines or DeadlineServiceFake()
    return job, database


def test_a_run_with_no_candidates_anywhere_is_all_zero():
    job, database = job_with()
    summary = job.run_once(now=NOW)
    assert summary.total_processed == 0
    assert summary.total_skipped == 0
    assert summary.total_failed == 0
    assert summary.run_id
    assert summary.started_at == NOW


def test_threshold_candidates_are_processed_or_skipped_and_paginate_by_keyset():
    sla = SlaServiceFake(
        pages=[[101, 102], [103], []],
        outcomes={101: "AT_RISK-outcome", 102: None, 103: "OVERDUE-outcome"},
    )
    job, database = job_with(sla=sla)
    counts = job._scan_thresholds(now=NOW, limit=200)
    assert isinstance(counts, CategoryCounts)
    assert counts.processed == 2
    assert counts.skipped == 1
    assert counts.failed == 0
    assert sla.evaluated == [101, 102, 103]
    # Each page's after_ticket_id cursor is the previous page's last id.
    assert [call["after_ticket_id"] for call in sla.repository.calls] == [0, 102, 103]
    # 48h * 80% = 38h24m before now, computed from the (fake, but real-shaped) config.
    assert sla.repository.calls[0]["at_risk_cutoff"] == NOW - timedelta(hours=38, minutes=24)


def test_pending_user_candidate_already_moved_on_is_skipped_not_processed():
    """The candidate query believed ticket 501 was still PENDING_USER and
    overdue; by the time this ticket's own lock is taken, a concurrent
    action already moved it elsewhere -- get_pending_user_snapshot
    correctly returns None, and that must count as a skip, not a
    processed write.
    """
    workflow_repository = WorkflowRepositoryFake(
        pending_user_pages=[[501], []], pending_user_snapshots={}
    )
    job, database = job_with(workflow_repository=workflow_repository)
    counts = job._scan_pending_user_timeouts(now=NOW, limit=200)
    assert counts == CategoryCounts(processed=0, skipped=1, failed=0)


def test_pending_user_timeout_applied_commits_and_counts_as_processed():
    workflow_repository = WorkflowRepositoryFake(
        pending_user_pages=[[501], []],
        pending_user_snapshots={501: PENDING_USER_ROW(501)},
    )
    deadlines = DeadlineServiceFake(pending_user_outcomes={501: Outcome(applied=True)})
    job, database = job_with(workflow_repository=workflow_repository, deadlines=deadlines)
    counts = job._scan_pending_user_timeouts(now=NOW, limit=200)
    assert counts == CategoryCounts(processed=1, skipped=0, failed=0)
    assert database.commits == 1
    assert database.rollbacks >= 1  # the pre-page rollback plus none on the processed item


def test_pending_user_timeout_not_yet_actually_expired_is_a_skip():
    """Defence in depth: even though the SQL candidate query already
    filters on pending_user_deadline <= now, a race between reading the
    candidate list and locking the row could in principle leave
    check_pending_user_timeout finding now still before the deadline --
    applied=False must still be a skip, not a processed write.
    """
    workflow_repository = WorkflowRepositoryFake(
        pending_user_pages=[[501], []],
        pending_user_snapshots={501: PENDING_USER_ROW(501)},
    )
    deadlines = DeadlineServiceFake(pending_user_outcomes={501: Outcome(applied=False)})
    job, database = job_with(workflow_repository=workflow_repository, deadlines=deadlines)
    counts = job._scan_pending_user_timeouts(now=NOW, limit=200)
    assert counts == CategoryCounts(processed=0, skipped=1, failed=0)


def test_auto_close_candidate_applies_and_is_processed():
    workflow_repository = WorkflowRepositoryFake(
        auto_close_pages=[[901], []],
        resolved_snapshots={901: RESOLVED_ROW(901)},
    )
    deadlines = DeadlineServiceFake(auto_close_outcomes={901: Outcome(applied=True)})
    job, database = job_with(workflow_repository=workflow_repository, deadlines=deadlines)
    counts = job._scan_auto_close(now=NOW, limit=200)
    assert counts == CategoryCounts(processed=1, skipped=0, failed=0)


def test_a_single_ticket_failure_is_isolated_counted_and_does_not_abort_the_batch():
    """C036.03/.05: one candidate raising must not stop the rest of the
    same page from being attempted, and must show up as failed rather
    than silently vanishing.
    """
    sla = SlaServiceFake(pages=[[201, 202]], outcomes={202: "processed-outcome"})

    class RaisingSlaService(SlaServiceFake):
        def evaluate_threshold_scan(self, *, ticket_id, now):
            if ticket_id == 201:
                raise RuntimeError("boom")
            return super().evaluate_threshold_scan(ticket_id=ticket_id, now=now)

    raising = RaisingSlaService(pages=[[201, 202]], outcomes={202: "processed-outcome"})
    job, database = job_with(sla=raising)
    counts = job._scan_thresholds(now=NOW, limit=200)
    assert counts.failed == 1
    assert counts.processed == 1
    assert counts.skipped == 0


def test_run_once_aggregates_all_three_categories_and_totals_failures():
    sla = SlaServiceFake(pages=[[301]], outcomes={301: "outcome"})
    workflow_repository = WorkflowRepositoryFake(
        pending_user_pages=[[401]],
        pending_user_snapshots={401: PENDING_USER_ROW(401)},
        auto_close_pages=[[402]],
        resolved_snapshots={402: RESOLVED_ROW(402)},
    )
    deadlines = DeadlineServiceFake(
        pending_user_outcomes={401: Outcome(applied=True)},
        auto_close_outcomes={402: Outcome(applied=False)},
    )
    job, database = job_with(sla=sla, workflow_repository=workflow_repository, deadlines=deadlines)
    summary = job.run_once(now=NOW)
    assert summary.threshold.processed == 1
    assert summary.pending_user.processed == 1
    assert summary.auto_close.skipped == 1
    assert summary.total_processed == 2
    assert summary.total_failed == 0
    assert summary.finished_at >= summary.started_at


def test_a_default_now_falls_back_to_the_real_clock():
    job, database = job_with()
    summary = job.run_once()
    assert summary.started_at is not None
    assert summary.finished_at >= summary.started_at
