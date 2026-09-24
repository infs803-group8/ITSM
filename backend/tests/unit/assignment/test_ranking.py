"""Unit tests for app.domains.assignment.ranking (C022).

Pure dataclasses only -- actually executed via this project's pytest-shim
convention, not merely syntax-checked.
"""

from datetime import datetime

from app.domains.assignment.ranking import Candidate, pick_winner, rank_candidates


def test_lowest_active_load_wins():
    candidates = [
        Candidate(user_id=1, active_load=3, last_assigned_at=None),
        Candidate(user_id=2, active_load=1, last_assigned_at=None),
        Candidate(user_id=3, active_load=2, last_assigned_at=None),
    ]
    ranked = rank_candidates(candidates)
    assert [c.user_id for c in ranked] == [2, 3, 1]


def test_never_assigned_beats_a_real_timestamp_on_equal_load():
    candidates = [
        Candidate(user_id=1, active_load=0, last_assigned_at=datetime(2020, 1, 1)),
        Candidate(user_id=2, active_load=0, last_assigned_at=None),
    ]
    ranked = rank_candidates(candidates)
    assert [c.user_id for c in ranked] == [2, 1]


def test_older_last_assigned_at_beats_a_newer_one_on_equal_load():
    candidates = [
        Candidate(user_id=1, active_load=0, last_assigned_at=datetime(2026, 1, 1)),
        Candidate(user_id=2, active_load=0, last_assigned_at=datetime(2020, 1, 1)),
    ]
    ranked = rank_candidates(candidates)
    assert [c.user_id for c in ranked] == [2, 1]


def test_user_id_is_the_final_deterministic_tiebreak():
    candidates = [
        Candidate(user_id=5, active_load=0, last_assigned_at=None),
        Candidate(user_id=2, active_load=0, last_assigned_at=None),
        Candidate(user_id=3, active_load=0, last_assigned_at=None),
    ]
    ranked = rank_candidates(candidates)
    assert [c.user_id for c in ranked] == [2, 3, 5]


def test_full_ordering_precedence_load_then_timestamp_then_id():
    candidates = [
        Candidate(user_id=1, active_load=1, last_assigned_at=None),
        Candidate(user_id=2, active_load=0, last_assigned_at=datetime(2025, 6, 1)),
        Candidate(user_id=3, active_load=0, last_assigned_at=None),
        Candidate(user_id=4, active_load=0, last_assigned_at=datetime(2020, 1, 1)),
    ]
    ranked = rank_candidates(candidates)
    assert [c.user_id for c in ranked] == [3, 4, 2, 1]


def test_pick_winner_returns_the_top_ranked_candidate():
    candidates = [
        Candidate(user_id=1, active_load=2, last_assigned_at=None),
        Candidate(user_id=2, active_load=0, last_assigned_at=None),
    ]
    winner = pick_winner(candidates)
    assert winner is not None
    assert winner.user_id == 2


def test_pick_winner_returns_none_for_no_candidates():
    assert pick_winner([]) is None


def test_rank_candidates_does_not_mutate_the_input_list():
    candidates = [
        Candidate(user_id=1, active_load=2, last_assigned_at=None),
        Candidate(user_id=2, active_load=0, last_assigned_at=None),
    ]
    original_order = list(candidates)
    rank_candidates(candidates)
    assert candidates == original_order
