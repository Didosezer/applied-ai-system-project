import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
import chromadb

from pawpal_system import Owner, Pet
from agents.agent_orchestrator import run_agent, AgentLoopError, AgentResult


# ---------------------------------------------------------------------------
# Helpers — build mock OpenAI responses
# ---------------------------------------------------------------------------

def _tool_call(name: str, args: dict, call_id: str = "tc_001"):
    tc = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )
    msg = SimpleNamespace(tool_calls=[tc], content=None, role="assistant")
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="tool_calls", message=msg)]
    )


def _stop_response(text: str):
    msg = SimpleNamespace(tool_calls=None, content=text, role="assistant")
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=msg)]
    )


@pytest.fixture
def owner():
    o = Owner(name="Alice")
    o.add_pet(Pet(name="Doudou"))
    return o


def _patch_rag(monkeypatch, collection_name: str):
    import tools.rag_retrieval as rag
    col = chromadb.Client().get_or_create_collection(collection_name)
    monkeypatch.setattr(rag, "_collection", col)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("agents.agent_orchestrator._get_client")
def test_run_agent_returns_agent_result(mock_get_client, owner, monkeypatch):
    _patch_rag(monkeypatch, "agt_col_001")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _tool_call("rag_search", {"query": "Golden Retriever surgery"}),
        _tool_call("create_tasks", {
            "pet_name": "Doudou",
            "tasks": [{"name": "Pre-op fasting", "time": "2026-05-03T20:00:00", "duration_minutes": 0}],
        }, call_id="tc_002"),
        _stop_response("Schedule arranged. Fasting starts at 8 PM."),
    ]

    result = run_agent(owner, "My dog needs surgery next week.")
    assert isinstance(result, AgentResult)
    assert result.explanation == "Schedule arranged. Fasting starts at 8 PM."
    assert result.iterations == 3


@patch("agents.agent_orchestrator._get_client")
def test_run_agent_tasks_staged_not_committed(mock_get_client, owner, monkeypatch):
    _patch_rag(monkeypatch, "agt_col_002")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _tool_call("create_tasks", {
            "pet_name": "Doudou",
            "tasks": [{"name": "Walk", "duration_minutes": 30}],
        }),
        _stop_response("Done."),
    ]

    run_agent(owner, "Schedule a walk for Doudou.")
    assert len(owner.get_pet_by_name("Doudou").tasks) == 0


@patch("agents.agent_orchestrator._get_client")
def test_run_agent_staged_by_pet_populated(mock_get_client, owner, monkeypatch):
    _patch_rag(monkeypatch, "agt_col_003")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _tool_call("create_tasks", {
            "pet_name": "Doudou",
            "tasks": [{"name": "Feed", "duration_minutes": 10}],
        }),
        _stop_response("Done."),
    ]

    result = run_agent(owner, "Feed Doudou.")
    assert "Doudou" in result.staged_by_pet
    assert result.staged_by_pet["Doudou"][0].name == "Feed"


@patch("agents.agent_orchestrator._get_client")
def test_run_agent_max_iterations_raises(mock_get_client, owner, monkeypatch):
    _patch_rag(monkeypatch, "agt_col_004")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.return_value = _tool_call(
        "rag_search", {"query": "test"}
    )

    with pytest.raises(AgentLoopError):
        run_agent(owner, "Keep searching forever.")


@patch("agents.agent_orchestrator._get_client")
def test_run_agent_unknown_pet_does_not_crash(mock_get_client, owner, monkeypatch):
    _patch_rag(monkeypatch, "agt_col_005")
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _tool_call("create_tasks", {
            "pet_name": "GhostPet",
            "tasks": [{"name": "Walk", "duration_minutes": 0}],
        }),
        _stop_response("Could not find the pet."),
    ]

    result = run_agent(owner, "Schedule walk for GhostPet.")
    assert result.staged_by_pet == {}
