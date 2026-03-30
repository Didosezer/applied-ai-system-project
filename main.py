from datetime import datetime, date, timedelta
from pawpal_system import Owner, Pet, Task, Scheduler


def _today_dt(hour: int, minute: int = 0) -> datetime:
    now = datetime.now()
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def main() -> None:
    owner = Owner(name="Alice")

    # create pets
    fido = Pet(name="Fido")
    mittens = Pet(name="Mittens")
    owner.add_pet(fido)
    owner.add_pet(mittens)

    # create tasks (two for today, one for tomorrow)
    walk = Task(name="Morning walk", time=_today_dt(8, 0))
    feed = Task(name="Feed", time=_today_dt(12, 30))
    vet = Task(name="Vet appointment", time=(_today_dt(9, 0) + timedelta(days=1)))

    fido.add_task(walk)
    fido.add_task(vet)
    mittens.add_task(feed)

    # optional: use Scheduler if available
    entries = []
    try:
        scheduler = Scheduler(owner=owner)
        schedule = scheduler.get_schedule(date_filter=date.today(), include_done=False)
        # scheduler returns list[tuple[Pet, Task]]
        for pet, task in schedule:
            if task.time is None:
                continue
            entries.append((task.time, pet, task))
    except Exception:
        # fallback: traverse owner -> pets -> tasks directly
        for pet in owner.pets:
            for task in pet.tasks:
                if task.time and task.time.date() == date.today() and not task.is_done:
                    entries.append((task.time, pet, task))

    # sort and print
    entries.sort(key=lambda x: x[0])
    print("Today's Schedule:")
    if not entries:
        print("  (no tasks for today)")
    for when, pet, task in entries:
        status = "done" if task.is_done else "pending"
        print(f"  {when.strftime('%H:%M')}  - {pet.name}: {task.name} [{status}]")


if __name__ == "__main__":
    main()