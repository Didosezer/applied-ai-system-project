import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
import pytest
from pawpal_system import Owner, Pet, Task
from evaluators.schedule_validator import (
    validate,
    check_same_pet_overlap,
    check_cross_pet_overlap,
)


@pytest.fixture
def owner():
    o = Owner(name="Alice")
    o.add_pet(Pet(name="Doudou"))
    o.add_pet(Pet(name="Mimi"))
    return o


# ---------------------------------------------------------------------------
# Same-pet time overlap (rule layer)
# ---------------------------------------------------------------------------

def test_no_conflict_returns_empty(owner):
    staged = {
        "Doudou": [
            Task(name="Morning walk", time=datetime(2026, 5, 4, 8, 0), duration_minutes=30),
            Task(name="Feed",         time=datetime(2026, 5, 4, 12, 0), duration_minutes=10),
        ]
    }
    warnings = validate(owner, staged, use_ai=False)
    assert warnings == []


def test_same_pet_overlap_detected(owner):
    staged = {
        "Doudou": [
            Task(name="Surgery",         time=datetime(2026, 5, 4, 9, 0),  duration_minutes=120),
            Task(name="Post-op feeding", time=datetime(2026, 5, 4, 10, 0), duration_minutes=15),
        ]
    }
    warnings = validate(owner, staged, use_ai=False)
    assert len(warnings) >= 1
    assert any("Surgery" in w.conflicting_task_names for w in warnings)


def test_same_pet_overlap_severity_is_high(owner):
    staged = {
        "Doudou": [
            Task(name="A", time=datetime(2026, 5, 4, 9, 0),  duration_minutes=60),
            Task(name="B", time=datetime(2026, 5, 4, 9, 30), duration_minutes=10),
        ]
    }
    warnings = validate(owner, staged, use_ai=False)
    assert all(w.severity == "high" for w in warnings)


def test_tasks_without_time_do_not_conflict(owner):
    staged = {
        "Doudou": [
            Task(name="Task A", time=None, duration_minutes=60),
            Task(name="Task B", time=None, duration_minutes=60),
        ]
    }
    warnings = validate(owner, staged, use_ai=False)
    assert warnings == []


# ---------------------------------------------------------------------------
# Cross-pet conflict (rule layer)
# ---------------------------------------------------------------------------

def test_cross_pet_conflict_detected(owner):
    staged = {
        "Doudou": [Task(name="Surgery", time=datetime(2026, 5, 4, 9, 0),  duration_minutes=120)],
        "Mimi":   [Task(name="Bath",    time=datetime(2026, 5, 4, 9, 30), duration_minutes=30)],
    }
    warnings = validate(owner, staged, use_ai=False)
    assert any("Doudou" in w.message and "Mimi" in w.message for w in warnings)


def test_cross_pet_conflict_severity_is_medium(owner):
    staged = {
        "Doudou": [Task(name="Vet",  time=datetime(2026, 5, 4, 10, 0), duration_minutes=60)],
        "Mimi":   [Task(name="Groom", time=datetime(2026, 5, 4, 10, 0), duration_minutes=60)],
    }
    warnings = validate(owner, staged, use_ai=False)
    cross = [w for w in warnings if "Doudou" in w.message and "Mimi" in w.message]
    assert all(w.severity == "medium" for w in cross)


def test_same_pet_tasks_do_not_trigger_cross_pet_warning(owner):
    staged = {
        "Doudou": [
            Task(name="Walk", time=datetime(2026, 5, 4, 8, 0),  duration_minutes=120),
            Task(name="Feed", time=datetime(2026, 5, 4, 8, 30), duration_minutes=10),
        ]
    }
    warnings = validate(owner, staged, use_ai=False)
    cross = [w for w in warnings if "Mimi" in w.message]
    assert cross == []


# ---------------------------------------------------------------------------
# ConflictWarning structure
# ---------------------------------------------------------------------------

def test_conflict_warning_has_required_fields(owner):
    staged = {
        "Doudou": [
            Task(name="X", time=datetime(2026, 5, 4, 9, 0),  duration_minutes=60),
            Task(name="Y", time=datetime(2026, 5, 4, 9, 30), duration_minutes=30),
        ]
    }
    warnings = validate(owner, staged, use_ai=False)
    for w in warnings:
        assert hasattr(w, "severity")
        assert hasattr(w, "message")
        assert hasattr(w, "conflicting_task_names")
        assert isinstance(w.conflicting_task_names, list)
