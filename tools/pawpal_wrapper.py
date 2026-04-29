from __future__ import annotations

from datetime import datetime
from typing import Any

from pawpal_system import Owner, Pet, Task, Scheduler


class PetNotFoundError(Exception):
    pass


_VALID_PRIORITIES = {"low", "medium", "high", "critical"}


def create_tasks(owner: Owner, pet_name: str, tasks_spec: list[dict[str, Any]]) -> list[Task]:
    """Construct Task objects from Agent-supplied specs and return them as a staged list.

    Tasks are NOT written to the pet yet — call commit_staged_tasks() after human approval.

    Raises PetNotFoundError if pet_name is not registered under owner.
    """
    pet = owner.get_pet_by_name(pet_name)
    if pet is None:
        raise PetNotFoundError(f"Pet '{pet_name}' not found for owner '{owner.name}'.")

    staged: list[Task] = []
    for spec in tasks_spec:
        time_val: datetime | None = None
        if spec.get("time"):
            time_val = datetime.fromisoformat(spec["time"])

        duration = int(spec.get("duration_minutes", 0))

        task = Task(
            name=str(spec["name"]),
            time=time_val,
            duration_minutes=duration,
            category=str(spec.get("category", "")),
        )
        staged.append(task)

    return staged


def commit_staged_tasks(owner: Owner, pet_name: str, staged_tasks: list[Task]) -> None:
    """Write previously staged tasks into the pet's task list after human approval."""
    pet = owner.get_pet_by_name(pet_name)
    if pet is None:
        raise PetNotFoundError(f"Pet '{pet_name}' not found for owner '{owner.name}'.")

    for task in staged_tasks:
        pet.add_task(task)


def get_current_schedule(owner: Owner) -> list[dict[str, Any]]:
    """Return the owner's full schedule as a JSON-serialisable list of dicts."""
    scheduler = Scheduler(owner=owner)
    entries = scheduler.get_schedule(include_done=False)

    result = []
    for pet, task in entries:
        result.append({
            "pet": pet.name,
            "task": task.name,
            "time": task.time.isoformat() if task.time else None,
            "duration_minutes": task.duration_minutes,
            "is_done": task.is_done,
        })
    return result
