from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from pawpal_system import Owner, Pet, Task, NeuterRecord, VaccinationRecord

_OWNERS_DIR = Path(__file__).parent.parent / "data" / "owners"
_OWNERS_DIR.mkdir(parents=True, exist_ok=True)


def _owner_path(name: str) -> Path:
    safe = name.strip().replace(" ", "_").replace("/", "_")
    return _OWNERS_DIR / f"{safe}.json"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _ser_date(d) -> str | None:
    return d.isoformat() if d else None

def _ser_datetime(dt) -> str | None:
    return dt.isoformat() if dt else None

def _de_date(s) -> date | None:
    return date.fromisoformat(s) if s else None

def _de_datetime(s) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "time": _ser_datetime(t.time),
        "is_done": t.is_done,
        "duration_minutes": t.duration_minutes,
        "category": t.category,
    }

def _task_from_dict(d: dict) -> Task:
    return Task(
        id=d["id"],
        name=d["name"],
        time=_de_datetime(d.get("time")),
        is_done=d.get("is_done", False),
        duration_minutes=d.get("duration_minutes", 0),
        category=d.get("category", ""),
    )

def _vax_to_dict(v: VaccinationRecord) -> dict:
    return {"vaccine_name": v.vaccine_name, "date_given": _ser_date(v.date_given)}

def _vax_from_dict(d: dict) -> VaccinationRecord:
    return VaccinationRecord(
        vaccine_name=d["vaccine_name"],
        date_given=_de_date(d.get("date_given")),
    )

def _pet_to_dict(p: Pet) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "breed": p.breed,
        "birth_date": _ser_date(p.birth_date),
        "neuter_record": {
            "status": p.neuter_record.status,
            "date": _ser_date(p.neuter_record.date),
        },
        "vaccinations": [_vax_to_dict(v) for v in p.vaccinations],
        "tasks": [_task_to_dict(t) for t in p.tasks],
    }

def _pet_from_dict(d: dict) -> Pet:
    nr = d.get("neuter_record", {})
    pet = Pet(
        id=d["id"],
        name=d["name"],
        breed=d.get("breed", ""),
        birth_date=_de_date(d.get("birth_date")),
        neuter_record=NeuterRecord(
            status=nr.get("status"),
            date=_de_date(nr.get("date")),
        ),
        vaccinations=[_vax_from_dict(v) for v in d.get("vaccinations", [])],
        tasks=[_task_from_dict(t) for t in d.get("tasks", [])],
    )
    return pet

def _owner_to_dict(o: Owner) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "pets": [_pet_to_dict(p) for p in o.pets],
    }

def _owner_from_dict(d: dict) -> Owner:
    owner = Owner(id=d["id"], name=d["name"])
    owner.pets = [_pet_from_dict(p) for p in d.get("pets", [])]
    return owner


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_owner(owner: Owner) -> None:
    path = _owner_path(owner.name)
    path.write_text(json.dumps(_owner_to_dict(owner), ensure_ascii=False, indent=2))


def load_owner(name: str) -> Owner | None:
    path = _owner_path(name)
    if not path.exists():
        return None
    return _owner_from_dict(json.loads(path.read_text()))


def list_owners() -> list[str]:
    return sorted(p.stem.replace("_", " ") for p in _OWNERS_DIR.glob("*.json"))
