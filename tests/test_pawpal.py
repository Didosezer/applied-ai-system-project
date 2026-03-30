import pytest

from pawpal_system import Pet, Task


def test_task_mark_done_changes_status() -> None:
	"""Task Completion: calling mark_done() should set is_done to True."""
	t = Task(name="test task")
	assert not t.is_done
	t.mark_done()
	assert t.is_done


def test_pet_add_task_increases_task_count() -> None:
	"""Task Addition: adding a Task to a Pet increases its tasks length."""
	p = Pet(name="Buddy")
	assert len(p.tasks) == 0
	t = Task(name="feed")
	p.add_task(t)
	assert len(p.tasks) == 1
	assert p.tasks[0] is t
