import os
import sys
import datetime as _dt
from datetime import date, datetime

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from pawpal_system import Owner, Pet, NeuterRecord, VaccinationRecord
from agents.agent_orchestrator import run_agent, AgentLoopError
from tools.pawpal_wrapper import commit_staged_tasks
from tools.storage import save_owner, load_owner, list_owners
from evaluators.schedule_validator import validate

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "owner" not in st.session_state:
    st.session_state.owner = None
if "staged_by_pet" not in st.session_state:
    st.session_state.staged_by_pet = {}
if "agent_explanation" not in st.session_state:
    st.session_state.agent_explanation = ""
if "conflicts" not in st.session_state:
    st.session_state.conflicts = []

# ---------------------------------------------------------------------------
# Sidebar — owner & pet setup only
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🐾 PawPal+")
    st.subheader("Owner")

    saved = list_owners()
    if saved:
        selected = st.selectbox("Load existing owner", options=["— new —"] + saved, key="owner_select")
    else:
        selected = "— new —"

    owner_name = st.text_input("Owner name", value="Alice", key="owner_name_input")

    if st.button("Load / Create Owner"):
        if selected != "— new —":
            loaded = load_owner(selected)
            if loaded:
                st.session_state.owner = loaded
                st.session_state.staged_by_pet = {}
                st.session_state.agent_explanation = ""
                st.session_state.conflicts = []
                st.success(f"Loaded **{loaded.name}**")
            else:
                st.error("Could not load owner file.")
        else:
            existing = load_owner(owner_name.strip())
            if existing:
                st.session_state.owner = existing
                st.success(f"Loaded existing owner **{existing.name}**")
            else:
                st.session_state.owner = Owner(name=owner_name.strip())
                save_owner(st.session_state.owner)
                st.success(f"Created **{owner_name.strip()}**")
            st.session_state.staged_by_pet = {}
            st.session_state.agent_explanation = ""
            st.session_state.conflicts = []

    if st.session_state.owner:
        st.divider()
        st.subheader("Add a Pet")

        col1, col2 = st.columns(2)
        with col1:
            pet_name = st.text_input("Pet name", key="pet_name_input")
        with col2:
            pet_breed = st.text_input("Breed (optional)", key="breed_input")

        birth_date_input = st.date_input(
            "Birth date (optional)",
            value=None,
            min_value=date(2000, 1, 1),
            max_value=date.today(),
            key="birth_date_input",
        )

        col_ns, col_nd = st.columns(2)
        with col_ns:
            neuter_status = st.selectbox(
                "Neutered / Spayed",
                options=[None, True, False],
                format_func=lambda x: "Unknown" if x is None else ("Yes" if x else "No"),
                key="neutered_input",
            )
        with col_nd:
            neuter_date_input = st.date_input(
                "Procedure date (optional)",
                value=None,
                min_value=date(2000, 1, 1),
                max_value=date.today(),
                key="neuter_date_input",
            )

        if st.button("Add Pet"):
            owner = st.session_state.owner
            if not pet_name.strip():
                st.warning("Please enter a pet name.")
            elif owner.get_pet_by_name(pet_name.strip()):
                st.warning(f"**{pet_name}** is already registered.")
            else:
                pet = Pet(
                    name=pet_name.strip(),
                    breed=pet_breed.strip(),
                    birth_date=birth_date_input if birth_date_input else None,
                    neuter_record=NeuterRecord(
                        status=neuter_status,
                        date=neuter_date_input if neuter_date_input else None,
                    ),
                )
                owner.add_pet(pet)
                save_owner(owner)
                st.success(f"Added **{pet.name}**")

# ---------------------------------------------------------------------------
# Main panel — guard
# ---------------------------------------------------------------------------

st.title("PawPal+ AI Assistant")

if not st.session_state.owner:
    st.info("Set an owner name in the sidebar and click **Create / Switch Owner** to get started.")
    st.stop()

owner = st.session_state.owner

if not owner.pets:
    st.info("Add at least one pet in the sidebar before using the AI assistant.")
    st.stop()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_tasks, tab_pets = st.tabs(["Tasks", "Pet Profiles"])

# ===========================================================================
# Tab 1 — Tasks
# ===========================================================================

with tab_tasks:

    # ---- AI input ----------------------------------------------------------
    st.subheader("Ask the AI")
    user_message = st.text_area(
        "Describe what you need (in any language)",
        placeholder="e.g. Billy needs a bath this weekend.",
        height=80,
        key="user_message",
    )

    if st.button("Send to AI", type="primary"):
        if not user_message.strip():
            st.warning("Please enter a message.")
        elif not os.environ.get("OPENAI_API_KEY"):
            st.error("OPENAI_API_KEY is not set.")
        else:
            st.session_state.staged_by_pet = {}
            st.session_state.agent_explanation = ""
            st.session_state.conflicts = []

            with st.spinner("AI is thinking..."):
                try:
                    result = run_agent(owner, user_message)
                    st.session_state.staged_by_pet = result.staged_by_pet
                    st.session_state.agent_explanation = result.explanation

                    if result.staged_by_pet:
                        st.session_state.conflicts = validate(
                            owner, result.staged_by_pet, use_ai=True
                        )
                except AgentLoopError as e:
                    st.error(f"Agent error: {e}")

    if st.session_state.agent_explanation:
        st.info(st.session_state.agent_explanation)

    # ---- Staged tasks review -----------------------------------------------
    if st.session_state.staged_by_pet:
        st.divider()
        st.subheader("Proposed Tasks — Awaiting Your Approval")

        if st.session_state.conflicts:
            for w in st.session_state.conflicts:
                icon = "🔴" if w.severity == "high" else "🟡"
                st.warning(f"{icon} [{w.severity.upper()}] {w.message}")

        approved_any = False
        to_remove: list[tuple[str, int]] = []   # (pet_name, idx) pairs to drop after loop

        for pet_name, tasks in st.session_state.staged_by_pet.items():
            st.markdown(f"**{pet_name}**")
            for idx, t in enumerate(tasks):
                kp = f"staged_{pet_name}_{idx}"
                with st.container(border=True):
                    # Row 1: name (editable)
                    t.name = st.text_input("Task name", value=t.name, key=f"{kp}_name")

                    # Row 2: date | time | duration
                    col_date, col_time, col_dur = st.columns([3, 3, 2])
                    with col_date:
                        new_date = st.date_input(
                            "Date",
                            value=t.time.date() if t.time else date.today(),
                            key=f"{kp}_date",
                        )
                    with col_time:
                        new_time = st.time_input(
                            "Time",
                            value=t.time.time() if t.time else _dt.time(9, 0),
                            key=f"{kp}_time",
                        )
                    with col_dur:
                        t.duration_minutes = st.number_input(
                            "Duration (min)",
                            min_value=0,
                            value=t.duration_minutes,
                            step=5,
                            key=f"{kp}_dur",
                        )
                    t.time = datetime.combine(new_date, new_time)

                    # Row 3: per-task approve / reject
                    col_ok, col_no, _ = st.columns([1, 1, 4])
                    with col_ok:
                        if st.button("✅ Approve", key=f"{kp}_ok"):
                            commit_staged_tasks(owner, pet_name, [t])
                            save_owner(owner)
                            to_remove.append((pet_name, idx))
                            approved_any = True
                    with col_no:
                        if st.button("❌ Reject", key=f"{kp}_no"):
                            to_remove.append((pet_name, idx))

        # Apply removals (reverse order to keep indices valid)
        for pet_name, idx in sorted(to_remove, key=lambda x: x[1], reverse=True):
            st.session_state.staged_by_pet[pet_name].pop(idx)
        # Drop empty pet entries
        st.session_state.staged_by_pet = {
            k: v for k, v in st.session_state.staged_by_pet.items() if v
        }

        if to_remove:
            if approved_any:
                st.success("Task(s) saved.")
            st.rerun()

        # Bulk actions at the bottom
        if st.session_state.staged_by_pet:
            st.divider()
            col_all, col_none = st.columns(2)
            with col_all:
                if st.button("✅ Approve All", type="primary"):
                    for pn, tasks in st.session_state.staged_by_pet.items():
                        commit_staged_tasks(owner, pn, tasks)
                    save_owner(owner)
                    st.session_state.staged_by_pet = {}
                    st.session_state.conflicts = []
                    st.success("All tasks saved.")
                    st.rerun()
            with col_none:
                if st.button("❌ Reject All"):
                    st.session_state.staged_by_pet = {}
                    st.session_state.conflicts = []
                    st.session_state.agent_explanation = ""
                    st.rerun()

    # ---- Confirmed schedule ------------------------------------------------
    st.divider()
    st.subheader("Schedule")

    all_tasks = [
        (pet, task)
        for pet in owner.pets
        for task in pet.tasks
    ]
    pending = [(p, t) for p, t in all_tasks if not t.is_done]
    done = [(p, t) for p, t in all_tasks if t.is_done]

    if pending:
        pending.sort(key=lambda pt: pt[1].time or datetime.max)
        for _pet, _task in pending:
            col_info, col_btn = st.columns([6, 1])
            with col_info:
                time_str = _task.time.strftime("%Y-%m-%d %H:%M") if _task.time else "No time"
                cat_badge = f" `{_task.category}`" if _task.category else ""
                st.markdown(
                    f"🔲 **{_pet.name}** — {_task.name}{cat_badge}  \n"
                    f"<small>{time_str} · {_task.duration_minutes} min</small>",
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button("Done", key=f"done_{_task.id}"):
                    _task.mark_done()
                    if _task.category == "vaccination":
                        _pet.add_vaccination(VaccinationRecord(
                            vaccine_name=_task.name,
                            date_given=_task.time.date() if _task.time else date.today(),
                        ))
                    save_owner(owner)
                    st.rerun()
    else:
        st.caption("No pending tasks.")

    if done:
        with st.expander(f"Completed tasks ({len(done)})", expanded=False):
            for _pet, _task in done:
                time_str = _task.time.strftime("%Y-%m-%d %H:%M") if _task.time else "—"
                st.markdown(f"✅ **{_pet.name}** — {_task.name} · {time_str}")

# ===========================================================================
# Tab 2 — Pet Profiles
# ===========================================================================

with tab_pets:
    for pet in owner.pets:
        st.subheader(pet.name)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**Breed:** {pet.breed or '—'}")
            st.markdown(f"**Age:** {pet.age_display()}")
            if pet.birth_date:
                st.markdown(f"**Birth date:** {pet.birth_date.isoformat()}")

        with col_b:
            ns = pet.neuter_record.status
            neuter_label = "Neutered / Spayed" if ns is True else "Intact" if ns is False else "Unknown"
            neuter_date = f" ({pet.neuter_record.date.isoformat()})" if pet.neuter_record.date else ""
            st.markdown(f"**Neuter status:** {neuter_label}{neuter_date}")

        st.markdown("**Vaccination history:**")
        if pet.vaccinations:
            for v in pet.vaccinations:
                date_str = v.date_given.isoformat() if v.date_given else "date unknown"
                st.markdown(f"- {v.vaccine_name} · {date_str}")
        else:
            st.caption("No vaccinations recorded yet. Vaccination tasks marked Done will appear here.")

        if len(owner.pets) > 1:
            st.divider()
