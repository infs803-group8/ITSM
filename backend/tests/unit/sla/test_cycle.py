from datetime import UTC, datetime, timedelta

import pytest

from app.domains.sla.cycle import (
    SlaConfig,
    auto_close_deadline,
    first_cycle,
    next_cycle,
    start_cycle,
    user_response_deadline,
)

CONFIG = SlaConfig(engineering_sla_hours=48, at_risk_percent=80)
NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)


def test_first_cycle_is_cycle_one():
    window = first_cycle(started_at=NOW, config=CONFIG)
    assert window.cycle_no == 1
    assert window.started_at == NOW


def test_first_cycle_deadline_is_48_hours_later():
    window = first_cycle(started_at=NOW, config=CONFIG)
    assert window.deadline == NOW + timedelta(hours=48)


def test_at_risk_fires_at_80_percent_of_the_cycle():
    window = first_cycle(started_at=NOW, config=CONFIG)
    assert window.at_risk_at == NOW + timedelta(hours=38, minutes=24)  # 80% of 48h


def test_next_cycle_increments_from_the_previous_cycle_no():
    window = next_cycle(previous_cycle_no=3, started_at=NOW, config=CONFIG)
    assert window.cycle_no == 4
    assert window.started_at == NOW
    assert window.deadline == NOW + timedelta(hours=48)


def test_start_cycle_rejects_a_non_positive_cycle_no():
    with pytest.raises(ValueError):
        start_cycle(cycle_no=0, started_at=NOW, config=CONFIG)


def test_start_cycle_respects_a_different_config():
    short_config = SlaConfig(engineering_sla_hours=24, at_risk_percent=50)
    window = start_cycle(cycle_no=1, started_at=NOW, config=short_config)
    assert window.deadline == NOW + timedelta(hours=24)
    assert window.at_risk_at == NOW + timedelta(hours=12)


def test_user_response_deadline_is_120_hours_by_default_config():
    deadline = user_response_deadline(started_at=NOW, user_response_hours=120)
    assert deadline == NOW + timedelta(hours=120)


def test_auto_close_deadline_is_168_hours_after_resolution():
    resolved_at = NOW
    deadline = auto_close_deadline(resolved_at=resolved_at, resolved_window_hours=168)
    assert deadline == resolved_at + timedelta(days=7)


def test_escalation_does_not_go_through_this_module():
    """Escalation/reassignment/vendor round-trips keep the current cycle
    (baseline §4.2) -- there is deliberately no "same cycle, later start
    time" helper here, since nothing should ever call one.
    """
    import app.domains.sla.cycle as cycle_module

    assert not hasattr(cycle_module, "keep_cycle")
    assert not hasattr(cycle_module, "extend_cycle")
