from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from openai import OpenAI

from pawpal_system import Owner, Pet, Task

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


@dataclass
class ConflictWarning:
    severity: str                          # "low" | "medium" | "high"
    message: str
    conflicting_task_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule layer — pure time arithmetic, no AI
# ---------------------------------------------------------------------------

def _task_end(task: Task) -> datetime | None:
    if task.time is None:
        return None
    return task.time + timedelta(minutes=max(task.duration_minutes, 1))


def _tasks_overlap(a: Task, b: Task) -> bool:
    """Return True if two timed tasks have overlapping windows."""
    if a.time is None or b.time is None:
        return False
    a_end = _task_end(a)
    b_end = _task_end(b)
    return a.time < b_end and b.time < a_end


def check_same_pet_overlap(
    pet_name: str, staged: list[Task], existing: list[Task]
) -> list[ConflictWarning]:
    """Detect time-window overlaps among tasks assigned to the same pet."""
    all_tasks = staged + existing
    warnings: list[ConflictWarning] = []
    seen: set[tuple[str, str]] = set()

    for i, a in enumerate(all_tasks):
        for b in all_tasks[i + 1 :]:
            pair = tuple(sorted([a.id, b.id]))
            if pair in seen:
                continue
            seen.add(pair)
            if _tasks_overlap(a, b):
                warnings.append(ConflictWarning(
                    severity="high",
                    message=(
                        f"[{pet_name}] Time overlap: '{a.name}'"
                        f" ({a.time.strftime('%m-%d %H:%M') if a.time else '?'}, {a.duration_minutes} min)"
                        f" overlaps with '{b.name}'"
                        f" ({b.time.strftime('%m-%d %H:%M') if b.time else '?'})"
                    ),
                    conflicting_task_names=[a.name, b.name],
                ))
    return warnings


def check_cross_pet_overlap(
    owner: Owner, staged_by_pet: dict[str, list[Task]]
) -> list[ConflictWarning]:
    """Detect cases where the owner is needed by two different pets at the same time."""
    # Build a flat list of (pet_name, task) for all timed tasks
    all_timed: list[tuple[str, Task]] = []
    for pet in owner.pets:
        for task in pet.tasks:
            if task.time:
                all_timed.append((pet.name, task))
    for pet_name, tasks in staged_by_pet.items():
        for task in tasks:
            if task.time:
                all_timed.append((pet_name, task))

    warnings: list[ConflictWarning] = []
    seen: set[tuple[str, str]] = set()

    for i, (pet_a, task_a) in enumerate(all_timed):
        for pet_b, task_b in all_timed[i + 1 :]:
            if pet_a == pet_b:
                continue
            pair = tuple(sorted([task_a.id, task_b.id]))
            if pair in seen:
                continue
            seen.add(pair)
            if _tasks_overlap(task_a, task_b):
                warnings.append(ConflictWarning(
                    severity="medium",
                    message=(
                        f"Cross-pet conflict: {pet_a} '{task_a.name}'"
                        f" ({task_a.time.strftime('%m-%d %H:%M')})"
                        f" and {pet_b} '{task_b.name}'"
                        f" ({task_b.time.strftime('%m-%d %H:%M')})"
                        f" both require owner presence at the same time"
                    ),
                    conflicting_task_names=[task_a.name, task_b.name],
                ))
    return warnings


# ---------------------------------------------------------------------------
# AI layer — GPT analyses task semantics
# ---------------------------------------------------------------------------

def _serialize_tasks(tasks: list[Task], pet_name: str) -> list[dict[str, Any]]:
    return [
        {
            "pet": pet_name,
            "task": t.name,
            "time": t.time.isoformat() if t.time else None,
            "duration_minutes": t.duration_minutes,
        }
        for t in tasks
    ]


def check_semantic_conflicts(
    owner: Owner,
    staged_by_pet: dict[str, list[Task]],
) -> list[ConflictWarning]:
    """Use GPT to detect care-logic conflicts (medical, nutritional, behavioural)."""
    staged_list: list[dict] = []
    for pet_name, tasks in staged_by_pet.items():
        staged_list.extend(_serialize_tasks(tasks, pet_name))

    existing_list: list[dict] = []
    for pet in owner.pets:
        existing_list.extend(_serialize_tasks(pet.tasks, pet.name))

    if not staged_list:
        return []

    prompt = f"""You are a professional pet care schedule reviewer.

Analyze the following tasks-to-be-added and the existing schedule, and identify all care conflicts.
Conflicts include but are not limited to:
- Feeding scheduled during a fasting period
- Surgery scheduled without a prior fasting task the evening before
- Vigorous exercise scheduled during post-surgery recovery
- Medication timing incompatible with meal times
- Any other arrangement that poses a health risk to the pet

Tasks to be added:
{json.dumps(staged_list, ensure_ascii=False, indent=2)}

Existing schedule:
{json.dumps(existing_list, ensure_ascii=False, indent=2)}

Return ONLY a JSON object with a "conflicts" key containing an array. Each conflict must have:
- severity: "low" | "medium" | "high"
- message: one sentence describing the conflict in English
- conflicting_task_names: list of task names involved

If there are no conflicts, return {{"conflicts": []}}."""

    response = _get_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)

    # GPT may return {"conflicts": [...]} or directly [...]
    items = data if isinstance(data, list) else data.get("conflicts", data.get("warnings", []))

    warnings: list[ConflictWarning] = []
    for item in items:
        warnings.append(ConflictWarning(
            severity=item.get("severity", "medium"),
            message=item.get("message", ""),
            conflicting_task_names=item.get("conflicting_task_names", []),
        ))
    return warnings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate(
    owner: Owner,
    staged_by_pet: dict[str, list[Task]],
    use_ai: bool = True,
) -> list[ConflictWarning]:
    """Run both rule-based and AI-based conflict checks.

    Args:
        owner: the Owner object with existing pets/tasks
        staged_by_pet: {pet_name: [staged Task, ...]} — not yet committed
        use_ai: set False to skip the GPT call (useful in tests)

    Returns:
        Combined list of ConflictWarnings; empty = no conflicts found.
    """
    warnings: list[ConflictWarning] = []

    # Rule layer
    for pet_name, staged_tasks in staged_by_pet.items():
        pet = owner.get_pet_by_name(pet_name)
        existing = pet.tasks if pet else []
        warnings += check_same_pet_overlap(pet_name, staged_tasks, existing)

    warnings += check_cross_pet_overlap(owner, staged_by_pet)

    # AI layer
    if use_ai:
        warnings += check_semantic_conflicts(owner, staged_by_pet)

    return warnings
