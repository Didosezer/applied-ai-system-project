import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
import pytest
from pawpal_system import Owner, Pet, Task
from tools.pawpal_wrapper import (
    create_tasks,
    commit_staged_tasks,
    get_current_schedule,
    PetNotFoundError,
)


@pytest.fixture
def owner_with_pet():
    owner = Owner(name="Alice")
    owner.add_pet(Pet(name="Doudou"))
    return owner


def test_create_tasks_returns_task_objects(owner_with_pet):
    tasks = create_tasks(owner_with_pet, "Doudou", [
        {"name": "Morning walk", "time": "2026-05-04T08:00:00", "duration_minutes": 30},
    ])
    assert len(tasks) == 1
    assert isinstance(tasks[0], Task)
    assert tasks[0].name == "Morning walk"


def test_create_tasks_does_not_write_to_pet(owner_with_pet):
    create_tasks(owner_with_pet, "Doudou", [
        {"name": "Feed", "duration_minutes": 10},
    ])
    assert len(owner_with_pet.get_pet_by_name("Doudou").tasks) == 0


def test_create_tasks_parses_iso_time(owner_with_pet):
    tasks = create_tasks(owner_with_pet, "Doudou", [
        {"name": "Surgery", "time": "2026-05-04T09:00:00", "duration_minutes": 120},
    ])
    assert tasks[0].time == datetime(2026, 5, 4, 9, 0, 0)


def test_create_tasks_duration_stored(owner_with_pet):
    tasks = create_tasks(owner_with_pet, "Doudou", [
        {"name": "Bath", "duration_minutes": 45},
    ])
    assert tasks[0].duration_minutes == 45


def test_create_tasks_unknown_pet_raises(owner_with_pet):
    with pytest.raises(PetNotFoundError):
        create_tasks(owner_with_pet, "NoSuchPet", [{"name": "Walk", "duration_minutes": 0}])


def test_commit_staged_tasks_writes_to_pet(owner_with_pet):
    staged = create_tasks(owner_with_pet, "Doudou", [
        {"name": "Feed", "duration_minutes": 10},
        {"name": "Walk", "duration_minutes": 30},
    ])
    commit_staged_tasks(owner_with_pet, "Doudou", staged)
    pet = owner_with_pet.get_pet_by_name("Doudou")
    assert len(pet.tasks) == 2
    assert pet.tasks[0].name == "Feed"


def test_get_current_schedule_json_safe(owner_with_pet):
    staged = create_tasks(owner_with_pet, "Doudou", [
        {"name": "Walk", "time": "2026-05-04T08:00:00", "duration_minutes": 30},
    ])
    commit_staged_tasks(owner_with_pet, "Doudou", staged)
    schedule = get_current_schedule(owner_with_pet)
    assert len(schedule) == 1
    entry = schedule[0]
    assert entry["pet"] == "Doudou"
    assert entry["task"] == "Walk"
    assert isinstance(entry["time"], str)
    assert isinstance(entry["duration_minutes"], int)
