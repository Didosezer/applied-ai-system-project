from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Union, Tuple
from uuid import uuid4


@dataclass
class Task:
    """Represents a single task for a pet.

    Attributes:
        id: unique identifier
        name: short description of the task
        time: optional scheduled datetime for the task
        is_done: whether the task is completed
    """
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    time: Optional[datetime] = None
    is_done: bool = False
    duration_minutes: int = 0      # task duration; used by Validator to detect window overlaps
    category: str = ""             # e.g. "vaccination", "surgery", "feeding" — used for auto-extraction

    def mark_done(self) -> None:
        """Mark the task as completed."""
        self.is_done = True


@dataclass
class NeuterRecord:
    """Neuter/spay status and optional procedure date."""
    status: Optional[bool] = None   # True = neutered/spayed, False = intact, None = unknown
    date: Optional[date] = None


@dataclass
class VaccinationRecord:
    """A single vaccination entry."""
    vaccine_name: str = ""
    date_given: Optional[date] = None


@dataclass
class Pet:
    """A pet which can have multiple tasks."""
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    breed: str = ""
    birth_date: Optional[date] = None
    neuter_record: NeuterRecord = field(default_factory=NeuterRecord)
    vaccinations: List[VaccinationRecord] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)

    def add_vaccination(self, record: VaccinationRecord) -> None:
        self.vaccinations.append(record)

    def get_vaccination(self, vaccine_name: str) -> Optional[VaccinationRecord]:
        for v in self.vaccinations:
            if v.vaccine_name == vaccine_name:
                return v
        return None

    @property
    def age_years(self) -> Optional[int]:
        """Current age in full years, or None if birth_date is not set."""
        if self.birth_date is None:
            return None
        today = date.today()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    @property
    def age_months(self) -> Optional[int]:
        """Current age in full months, or None if birth_date is not set."""
        if self.birth_date is None:
            return None
        today = date.today()
        months = (today.year - self.birth_date.year) * 12 + (today.month - self.birth_date.month)
        if today.day < self.birth_date.day:
            months -= 1
        return max(months, 0)

    def age_display(self) -> str:
        """Age as 'X years Y months', dropping zero parts."""
        months = self.age_months
        if months is None:
            return "—"
        years, mo = divmod(months, 12)
        if years and mo:
            return f"{years}y {mo}mo"
        if years:
            return f"{years}y"
        return f"{mo}mo"

    def add_task(self, task: Task) -> None:
        """Add a Task to this pet's task list."""
        self.tasks.append(task)

    def get_task_by_name(self, name: str) -> Optional[Task]:
        for t in self.tasks:
            if t.name == name:
                return t
        return None

    def get_task_by_id(self, id: str) -> Optional[Task]:
        for t in self.tasks:
            if t.id == id:
                return t
        return None

    def remove_task(self, task_or_id_or_name: Union[Task, str]) -> bool:
        """Remove a task by object, id, or by name. Returns True if removed."""
        if isinstance(task_or_id_or_name, Task):
            if task_or_id_or_name in self.tasks:
                self.tasks.remove(task_or_id_or_name)
                return True
            return False
        # otherwise assume string id or name
        for t in list(self.tasks):
            if t.id == task_or_id_or_name or t.name == task_or_id_or_name:
                self.tasks.remove(t)
                return True
        return False


@dataclass
class Owner:
    """Owner of pets."""
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    pets: List[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        self.pets.append(pet)

    def get_pet_by_name(self, name: str) -> Optional[Pet]:
        for p in self.pets:
            if p.name == name:
                return p
        return None

    def get_pet_by_id(self, id: str) -> Optional[Pet]:
        for p in self.pets:
            if p.id == id:
                return p
        return None

    def remove_pet(self, pet_or_id_or_name: Union[Pet, str]) -> bool:
        """Remove a pet by object, id, or by name. Returns True if removed."""
        if isinstance(pet_or_id_or_name, Pet):
            if pet_or_id_or_name in self.pets:
                self.pets.remove(pet_or_id_or_name)
                return True
            return False
        for p in list(self.pets):
            if p.id == pet_or_id_or_name or p.name == pet_or_id_or_name:
                self.pets.remove(p)
                return True
        return False


@dataclass
class Scheduler:
    """Simple scheduler that computes an owner's schedule.

    get_schedule returns a list of (Pet, Task) tuples filtered by optional
    date and include_done flag, sorted by task time.
    """
    owner: Owner

    def get_schedule(self, date_filter: Optional[date] = None, include_done: bool = False) -> List[Tuple[Pet, Task]]:
        schedule: List[Tuple[Pet, Task]] = []
        for pet in self.owner.pets:
            for task in pet.tasks:
                if not include_done and task.is_done:
                    continue
                if date_filter and task.time:
                    if task.time.date() != date_filter:
                        continue
                schedule.append((pet, task))
        # sort by task time, placing tasks without time last
        schedule.sort(key=lambda pt: pt[1].time or datetime.max)
        return schedule
