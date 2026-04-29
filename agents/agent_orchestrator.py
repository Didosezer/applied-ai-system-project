from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from openai import OpenAI

from pawpal_system import Owner, Task
from tools import pawpal_wrapper, rag_retrieval

_client: OpenAI | None = None
MAX_ITERATIONS = 6


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# ---------------------------------------------------------------------------
# Tool definitions for OpenAI function calling
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Search the PawPal+ knowledge base for specialized pet care guidelines. "
                "Use this for topics covered in the knowledge base: toxic foods, breed-specific care, "
                "vaccination schedules, spay/neuter protocols, dental care, parasite prevention, nail trimming. "
                "Do NOT use for general questions the model already knows."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in English, e.g. 'dog nail trimming frequency'.",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of chunks to return. Default 3.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tasks",
            "description": (
                "Create one or more care tasks for a named pet in PawPal+. "
                "Always call rag_search first to confirm the correct care protocol. "
                "Tasks are staged for human review before being committed to the schedule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_name": {
                        "type": "string",
                        "description": "Exact name of the pet as registered in the system.",
                    },
                    "tasks": {
                        "type": "array",
                        "description": "List of tasks to create.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Short, specific task name, e.g. 'Pre-op fasting' or 'Post-op soft meal'.",
                                },
                                "time": {
                                    "type": "string",
                                    "description": "ISO 8601 datetime string, e.g. '2026-05-04T20:00:00'. Omit if time is unknown.",
                                },
                                "duration_minutes": {
                                    "type": "integer",
                                    "description": "Expected task duration in minutes. Use 0 if unknown.",
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Task category. Use 'vaccination' for any vaccine/booster shot task so the record is auto-saved to the pet's profile when marked done. Other values: 'surgery', 'feeding', 'grooming', 'checkup', or leave empty.",
                                },
                            },
                            "required": ["name", "duration_minutes"],
                        },
                    },
                },
                "required": ["pet_name", "tasks"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    staged_by_pet: dict[str, list[Task]]   # {pet_name: [Task, ...]} — not yet committed
    explanation: str                        # Claude's final natural-language summary
    rag_chunks: list[dict]                  # retrieved knowledge snippets (for UI display)
    iterations: int
    trace_steps: list[dict] = field(default_factory=list)  # Thought/Action/Observation trace


class AgentLoopError(Exception):
    pass


class UnknownToolError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pet_profile_text(pet) -> str:
    lines = [f"- {pet.name}"]
    if pet.breed:
        lines.append(f"  breed: {pet.breed}")
    if pet.age_years is not None:
        lines.append(f"  age: {pet.age_years} years")
    elif pet.birth_date:
        lines.append(f"  birth_date: {pet.birth_date.isoformat()}")
    ns = pet.neuter_record.status
    neuter_label = "neutered/spayed" if ns is True else "intact" if ns is False else "unknown"
    neuter_date = f" (procedure: {pet.neuter_record.date.isoformat()})" if pet.neuter_record.date else ""
    lines.append(f"  neuter_status: {neuter_label}{neuter_date}")
    if pet.vaccinations:
        vax_list = ", ".join(
            f"{v.vaccine_name} ({v.date_given.isoformat()})" if v.date_given else v.vaccine_name
            for v in pet.vaccinations
        )
        lines.append(f"  vaccinations: {vax_list}")
    else:
        lines.append("  vaccinations: none recorded")
    return "\n".join(lines)


def _build_system_prompt(owner: Owner) -> str:
    today = date.today().isoformat()
    schedule = pawpal_wrapper.get_current_schedule(owner)

    pet_profiles = "\n".join(_pet_profile_text(p) for p in owner.pets) if owner.pets else "none"

    schedule_text = (
        json.dumps(schedule, ensure_ascii=False, indent=2)
        if schedule
        else "No tasks scheduled yet."
    )

    return f"""You are PawPal+, a pet care scheduling assistant.

Today's date: {today}
Owner: {owner.name}

Pet profiles:
{pet_profiles}

Current schedule:
{schedule_text}

━━━ TASK CREATION RULES (highest priority) ━━━
- Always call create_tasks immediately without asking any questions first.
- If the user says "tomorrow", use tomorrow's date. Default time is 09:00 if unspecified.
- The ONLY exception: if the pet name is not in the profiles above, ask the owner to add it first.
- After creating tasks, write one short sentence summarising what you scheduled.

━━━ KNOWLEDGE BASE RULES ━━━
- For any care or medical topic, call rag_search first to retrieve relevant guidelines.
- Your advice and task details MUST be based ONLY on what rag_search returns.
- Do NOT add advice, facts, or protocols from your own training knowledge.
- When referencing care guidelines, quote the relevant content from the search result directly.
- If rag_search returns no results, respond with exactly:
  "I don't have specific information on this in my knowledge base."
  Then still create a basic task if the user's intent is clear.

━━━ VACCINATION & PROFILE RULES ━━━
- Use vaccination history and neuter status to personalise recommendations.
- Set category="vaccination" on any vaccine or booster task.

Respond in the same language the user writes in."""


def _dispatch_tool(
    tool_name: str,
    tool_args: dict,
    owner: Owner,
    staged_by_pet: dict[str, list[Task]],
    rag_chunks: list[dict],
) -> str:
    if tool_name == "rag_search":
        results = rag_retrieval.search(
            query=tool_args["query"],
            n_results=tool_args.get("n_results", 3),
        )
        if not results:
            return "KNOWLEDGE BASE RESULT: No relevant guidelines found. Do not invent advice."
        chunks = "\n---\n".join(r["text"] for r in results)
        return f"KNOWLEDGE BASE RESULT (use ONLY this content for your advice):\n\n{chunks}"

    if tool_name == "create_tasks":
        pet_name = tool_args["pet_name"]
        try:
            tasks = pawpal_wrapper.create_tasks(owner, pet_name, tool_args["tasks"])
        except pawpal_wrapper.PetNotFoundError as e:
            return f"Error: {e}"
        staged_by_pet.setdefault(pet_name, []).extend(tasks)
        names = [t.name for t in tasks]
        return f"Staged {len(tasks)} task(s) for {pet_name}: {', '.join(names)}. Awaiting owner approval."

    raise UnknownToolError(f"Unknown tool: '{tool_name}'")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_agent(owner: Owner, user_message: str) -> AgentResult:
    """Run the OpenAI function-calling agent loop.

    Returns an AgentResult with staged tasks and the final explanation.
    Tasks are NOT written to the Owner until commit_staged_tasks() is called.
    """
    messages = [
        {"role": "system", "content": _build_system_prompt(owner)},
        {"role": "user", "content": user_message},
    ]

    staged_by_pet: dict[str, list[Task]] = {}
    rag_chunks: list[dict] = []
    trace_steps: list[dict] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            tools=_TOOLS,
            messages=messages,
            temperature=0.2,
        )
        choice = response.choices[0]

        if choice.finish_reason == "stop":
            explanation = choice.message.content or ""
            trace_steps.append({"type": "final", "content": explanation})
            return AgentResult(staged_by_pet, explanation, rag_chunks, iteration, trace_steps)

        if choice.finish_reason == "tool_calls":
            # Capture any reasoning text the model emitted alongside the tool call
            thought_text = (choice.message.content or "").strip()
            if thought_text:
                trace_steps.append({"type": "thought", "content": thought_text})

            messages.append(choice.message)
            for tool_call in choice.message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                trace_steps.append({
                    "type": "action",
                    "tool": tool_call.function.name,
                    "args": args,
                })
                tool_result = _dispatch_tool(
                    tool_call.function.name,
                    args,
                    owner,
                    staged_by_pet,
                    rag_chunks,
                )
                trace_steps.append({
                    "type": "observation",
                    "tool": tool_call.function.name,
                    "content": tool_result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
            continue

        # Unexpected finish reason — treat remaining content as final answer
        explanation = choice.message.content or ""
        trace_steps.append({"type": "final", "content": explanation})
        return AgentResult(staged_by_pet, explanation, rag_chunks, iteration, trace_steps)

    raise AgentLoopError(
        f"Agent did not finish within {MAX_ITERATIONS} iterations. "
        f"Staged so far: {list(staged_by_pet.keys())}"
    )
