"""
Interactive runner for the Coach agent.

Usage:
    python main.py        # shows login / sign-up menu
"""
from __future__ import annotations

import json
import re
import sys
import shutil
import textwrap
from uuid import uuid4
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_SRC_DIR.parent))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from deepagents.backends import FilesystemBackend

from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import Trainee
from fitness_multiagent_rag.agents.coach.agent import build_coach_agent
from fitness_multiagent_rag.agents.coach.auth import authenticate
from fitness_multiagent_rag.agents.coach.memory import memory_backend
from fitness_multiagent_rag.agents.coach.routing import classify_intent, draft_action, plan_topic
from fitness_multiagent_rag.agents.coach.identity import COACH_NAME

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

# ── ANSI styles ───────────────────────────────────────────────────────────────
_DIM  = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[96m"
_RST  = "\033[0m"


# ── Display helpers ───────────────────────────────────────────────────────────

def _strip_tokens(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<\|channel>.*?<channel\|>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[|]?channel[|]?[^>]*>", "", text)
    return text.strip()


def _internal(msg: str) -> None:
    print(f"  {_DIM}{msg}{_RST}")


def _brief_args(args: dict) -> str:
    out = []
    for k, v in list(args.items())[:3]:
        s = str(v)
        out.append(f"{k}={repr(s[:40] + '…' if len(s) > 40 else s)}")
    suffix = ", …" if len(args) > 3 else ""
    return ", ".join(out) + suffix


def _brief_result(content: str) -> str:
    s = content.replace("\n", " ").strip()
    return s[:100] + "…" if len(s) > 100 else s


def _box(text: str) -> None:
    width = max(20, min(100, shutil.get_terminal_size(fallback=(80, 24)).columns - 6))
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    lines = []
    for paragraph in text.strip().split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=width) or [""])
    inner = max(len(COACH_NAME), *(len(line) for line in lines)) + 4
    bar   = "═" * inner
    print()
    print(f"{_CYAN}╔{bar}╗{_RST}")
    hdr = f"  {_BOLD}{COACH_NAME}{_RST}{_CYAN}"
    print(f"{_CYAN}║{hdr}{' ' * (inner - 2 - len(COACH_NAME))}║{_RST}")
    print(f"{_CYAN}╠{bar}╣{_RST}")
    for line in lines:
        pad = " " * (inner - 4 - len(line))
        print(f"{_CYAN}║{_RST}  {line}{pad}  {_CYAN}║{_RST}")
    print(f"{_CYAN}╚{bar}╝{_RST}")
    print()


def _prompt_user() -> str:
    print(f"  {_CYAN}{'─' * 66}{_RST}")
    try:
        answer = input(f"  {_BOLD}You › {_RST}").strip()
    except EOFError:
        answer = ""
    print()
    return answer


# ── Core streaming helper ─────────────────────────────────────────────────────

def _stream_turn(agent, messages: list, *, show_trace: bool = True, on_reply=None) -> tuple[str, list, dict[str, str]]:
    new_messages: list = []
    tool_results: dict[str, str] = {}
    final_answer = ""
    calls = {}
    failed_calls = set()
    from fitness_multiagent_rag.utils.tool_errors import tool_result_error

    from config.settings import RECURSION_LIMIT
    from fitness_multiagent_rag.agents.retriever.agent import _release_search_budget

    request_id = str(uuid4())
    try:
        updates = agent.stream(
            {"messages": messages},
            config={"configurable": {"retriever_request_id": request_id},
                    "recursion_limit": RECURSION_LIMIT},
            stream_mode="updates",
        )
        for update in updates:
            for _node, state in update.items():
                if not state:
                    continue
                for msg in state.get("messages", []):
                    new_messages.append(msg)
                    if isinstance(msg, AIMessage):
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                calls[tc["id"]] = (tc["name"], json.dumps(tc["args"], sort_keys=True))
                                if show_trace:
                                    _internal(f"[ → ] {tc['name']}({_brief_args(tc['args'])})")
                        elif msg.content:
                            content = _strip_tokens(msg.content)
                            if content:
                                final_answer = content
                                if on_reply:
                                    on_reply(content)
                                elif show_trace:
                                    _box(content)
                    elif isinstance(msg, ToolMessage):
                        tool_results[msg.name] = msg.content
                        error = tool_result_error(msg)
                        if show_trace:
                            _internal(f"[ ← ] {msg.name}: {error or _brief_result(msg.content)}")
                        signature = calls.get(msg.tool_call_id)
                        if error and signature:
                            if signature in failed_calls:
                                final_answer = "I couldn't complete that update because it failed repeatedly. Your program has not been completed."
                                new_messages.append(AIMessage(content=final_answer))
                                if on_reply:
                                    on_reply(final_answer)
                                elif show_trace:
                                    _box(final_answer)
                                return final_answer, new_messages, tool_results
                            failed_calls.add(signature)

    finally:
        _release_search_budget(request_id)

    return final_answer, new_messages, tool_results


# ── Session context block ─────────────────────────────────────────────────────

def _build_context_block(trainee: Trainee, memory: str) -> str:
    lines = [
        f"SESSION START — trainee: {trainee.name} | username: {trainee.username}",
        f"trainee_id: {trainee.id}",
        f"goal: {trainee.goal or 'not set'}",
        f"level: {trainee.fitness_level or 'not set'}",
        f"equipment: {', '.join(trainee.equipment_available or []) or 'not set'}",
        f"injuries: {trainee.injuries_limitations or 'none'}",
    ]

    # Body stats (show if any are set)
    stats = []
    if trainee.height_cm:
        stats.append(f"height={trainee.height_cm}cm")
    if trainee.weight_kg:
        stats.append(f"weight={trainee.weight_kg}kg")
    if trainee.body_fat_pct:
        stats.append(f"body_fat={trainee.body_fat_pct}%")
    if trainee.muscle_pct:
        stats.append(f"muscle={trainee.muscle_pct}%")
    if stats:
        lines.append(f"body stats: {', '.join(stats)}")

    active_plan = crud.get_active_plan(trainee.id)
    if active_plan:
        pj = active_plan.plan_json
        lines.append(
            f"active_plan: plan_id={active_plan.id}, goal={pj.get('goal')}, "
            f"difficulty={pj.get('difficulty')}, duration={pj.get('duration_weeks')} weeks"
        )
    else:
        lines.append("active_plan: none")

    if memory:
        lines.append(f"\nMemory from past sessions:\n{memory}")
    else:
        lines.append("Memory: none (first session or no prior notes)")

    return "\n".join(lines)



def _nutrition_response(trainee_id: int, user_input: str, previous_reply: str = "") -> str | None:
    """Display stored meal details exactly, without regeneration or workout routing."""
    if plan_topic(user_input, previous_reply) != "nutrition":
        return None
    if not re.search(r"\b(show|see|view|display|details|detailed)\b", user_input, re.IGNORECASE):
        return None
    if re.search(r"\b(new|change|replace|revise|different)\b", user_input, re.IGNORECASE):
        return None
    from fitness_multiagent_rag.db import nutrition
    active = nutrition.get_plan(trainee_id)
    draft = nutrition.get_plan(trainee_id, "draft")
    record = draft if "draft" in user_input.casefold() else active or draft
    if not record:
        return "You don't have a stored nutrition plan yet. Would you like to create one?"
    plan = record["plan_json"]
    targets = plan["daily_targets"]
    lines = [f"Your nutrition plan ({record['status']}) — {plan['goal']}",
             f"Daily targets: {targets['calories_kcal']:g} kcal, {targets['protein_g']:g} g protein, "
             f"{targets['carbohydrate_g']:g} g carbohydrates, {targets['fat_g']:g} g fat.", ""]
    for meal in plan["meals"]:
        lines.append(meal["name"] + ":")
        for food in meal["foods"]:
            lines.append(f"  • {food['name']}: {food['portion']}")
            if food.get("alternatives"):
                lines.append("    Alternatives: " + ", ".join(food["alternatives"]))
        if meal.get("notes"):
            lines.append(meal["notes"])
        lines.append("")
    for field, label in [("dietary_preferences", "Preferences"), ("allergies", "Allergies"), ("restrictions", "Restrictions")]:
        lines.append(label + ": " + (", ".join(plan[field]) or "None recorded"))
    lines.append(f"Start: {plan['start_date']}. Review: {plan['review_date']}.")
    if plan.get("notes"):
        lines.append(plan["notes"])
    if record["status"] == "draft":
        lines.append("Would you like to activate this nutrition plan?")
    elif draft:
        lines.append("You also have a pending nutrition draft; ask to see it before approving changes.")
    return "\n".join(lines)

def _draft_response(trainee_id: int, user_input: str, previous_reply: str = "") -> str | None:
    from fitness_multiagent_rag.agents.designer.drafts import read_draft
    from fitness_multiagent_rag.agents.designer.agent import synthesize_week_one

    if plan_topic(user_input, previous_reply) == "nutrition":
        return None
    draft = read_draft(trainee_id)
    action = draft_action(user_input, draft, previous_reply)
    if action == "show_week1":
        return draft["week1_summary"] + "\n\nWould you like me to save this program?"
    if action != "generate_week1":
        return None
    _internal("[plan] Generating workout details from your existing structure.")
    try:
        result = json.loads(synthesize_week_one.invoke({
            "trainee_id": trainee_id, "structure_json": draft["structure_json"],
            "chunks_json": draft.get("chunks", []), "user_feedback": user_input,
        }))
        if result.get("error"):
            raise ValueError(result["error"])
        return result["week1_summary"] + "\n\nWould you like me to save this program?"
    except Exception as exc:
        _internal(f"[plan error] {type(exc).__name__}: {exc}")
        return "I couldn't generate the workout details this time. Your proposed structure is still stored."


# ── Main session loop ─────────────────────────────────────────────────────────

def run_session(trainee: Trainee) -> None:
    memory = memory_backend.load(trainee.id)

    print(f"\n{_CYAN}{'═' * 70}{_RST}")
    print(f"{_CYAN}  {_BOLD}FITNESS COACH — {COACH_NAME.upper()}{_RST}{_CYAN}  {_RST}")
    print(f"{_CYAN}{'═' * 70}{_RST}")
    print(f"  Trainee : {trainee.name}  (id={trainee.id})")
    print(f"  Memory  : {'loaded' if memory else 'empty (first session)'}")
    print(f"{_CYAN}{'═' * 70}{_RST}\n")

    backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT), virtual_mode=True)
    agent   = build_coach_agent(backend)

    context_block = _build_context_block(trainee, memory)
    messages: list = [HumanMessage(content=context_block)]

    # Determine if the fitness profile needs onboarding
    needs_intake = not trainee.goal or not trainee.fitness_level or not trainee.equipment_available
    if needs_intake:
        messages.append(HumanMessage(
            content="[intent: intake]\nI just signed up and need to set up my fitness profile."
        ))
        _, new_msgs, _ = _stream_turn(agent, messages)
        messages.extend(new_msgs)

    # Main conversation loop — runs until Ctrl+C
    try:
        while True:
            user_input = _prompt_user()
            if not user_input:
                continue

            previous_reply = next((str(m.content) for m in reversed(messages) if isinstance(m, AIMessage)), "")
            draft_reply = _nutrition_response(trainee.id, user_input, previous_reply)
            if draft_reply is None:
                draft_reply = _draft_response(trainee.id, user_input, previous_reply)
            if draft_reply is not None:
                messages.extend([HumanMessage(content=user_input), AIMessage(content=draft_reply)])
                _box(draft_reply)
                continue

            active_plan = crud.get_active_plan(trainee.id)
            intent = classify_intent(
                user_input,
                has_active_plan=active_plan is not None,
                memory_snippet=memory[:400],
                previous_reply=previous_reply,
            )
            _internal(f"[intent: {intent}]")

            full_msg = f"[intent: {intent}]\n{user_input}"
            messages.append(HumanMessage(content=full_msg))
            _, new_msgs, tr = _stream_turn(agent, messages)
            messages.extend(new_msgs)
    except KeyboardInterrupt:
        print(f"\n{_CYAN}  Session interrupted.{_RST}")
    finally:
        _finalize_session(trainee.id)


def _finalize_session(trainee_id: int) -> None:
    truncated = memory_backend.end_session(trainee_id)
    if truncated:
        _internal("[memory] Salience pass completed — old notes compressed.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        trainee = authenticate()
    except KeyboardInterrupt:
        print("\n  Goodbye!\n")
        sys.exit(0)

    if trainee is None:
        sys.exit(0)

    run_session(trainee)
