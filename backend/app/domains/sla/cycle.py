"""Pure Engineering-SLA cycle math (baseline v6.0 §4.2, task C017).

Computes cycle numbers and window timestamps only. No SQL, no clock
reads -- the caller always supplies ``now`` -- and no side effects.
Threshold *detection* (is a ticket at/past 80% or 100% right now) is a
separate task (C035, the SLA monitor); this module only computes the
window a cycle occupies once it is known to start.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SlaConfig:
    """Mirrors the single ``service_config`` row (schema.sql)."""

    engineering_sla_hours: int
    at_risk_percent: int


@dataclass(frozen=True)
class CycleWindow:
    cycle_no: int
    started_at: datetime
    deadline: datetime
    at_risk_at: datetime


def start_cycle(*, cycle_no: int, started_at: datetime, config: SlaConfig) -> CycleWindow:
    """Compute the window for cycle number ``cycle_no`` starting at ``started_at``.

    Every Engineering SLA cycle is ``engineering_sla_hours`` (48h) long;
    AT_RISK fires at ``at_risk_percent`` (80%) of the cycle -- baseline §4.2.
    """
    if cycle_no < 1:
        raise ValueError("cycle_no must be >= 1")
    duration = timedelta(hours=config.engineering_sla_hours)
    at_risk_offset = duration * config.at_risk_percent / 100
    return CycleWindow(
        cycle_no=cycle_no,
        started_at=started_at,
        deadline=started_at + duration,
        at_risk_at=started_at + at_risk_offset,
    )


def first_cycle(*, started_at: datetime, config: SlaConfig) -> CycleWindow:
    """Initial assignment: cycle_no = 1 (baseline §4.2 "the first cycle is 1")."""
    return start_cycle(cycle_no=1, started_at=started_at, config=config)


def next_cycle(*, previous_cycle_no: int, started_at: datetime, config: SlaConfig) -> CycleWindow:
    """Resume, Reopen, or any other cycle+1 event: a fresh window from ``started_at``.

    Escalation, Manager reassignment and Vendor request/response do NOT
    call this -- baseline §4.2 says they keep the current cycle.
    """
    return start_cycle(cycle_no=previous_cycle_no + 1, started_at=started_at, config=config)


def user_response_deadline(*, started_at: datetime, user_response_hours: int) -> datetime:
    """The 120h User Timer deadline (PENDING_USER), independent of the Engineering cycle."""
    return started_at + timedelta(hours=user_response_hours)


def auto_close_deadline(*, resolved_at: datetime, resolved_window_hours: int) -> datetime:
    """The 7-day (168h) ``auto_close_at``, set every time a ticket enters RESOLVED."""
    return resolved_at + timedelta(hours=resolved_window_hours)
