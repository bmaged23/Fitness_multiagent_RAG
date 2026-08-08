"""
Interactive runner for the Coach agent.

Usage:
    python main.py        # shows login / sign-up menu
"""
from __future__ import annotations

import json
import re
import sys
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
from fitness_multiagent_rag.agents.coach.routing import classify_intent
from fitness_multiagent_rag.agents.coach.identity import COACH_NAME

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

# ── ANSI styles ───────────────────────────────────────────────────────────────
_DIM  = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[96m"
_RST  = "\033[0m"


# ── Display helpers ───────────────────────────────────────────────────────────

def _strip_tokens(text: str) -> str:
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
    lines = text.strip().split("\n")
    inner = max(64, *(len(l) for l in lines)) + 2
    bar   = "═" * inner
    print()
    print(f"{_CYAN}╔{bar}╗{_RST}")
    hdr = f"  {_BOLD}{COACH_NAME}{_RST}{_CYAN}"
    print(f"{_CYAN}║{hdr}{' ' * (inner - 2 - len(COACH_NAME))}║{_RST}")
    print(f"{_CYAN}╠{bar}╣{_RST}")
    for line in lines:
        pad = " " * (inner - 2 - len(line))
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

def _stream_turn(agent, messages: list) -> tuple[str, list, dict[str, str]]:
    new_messages: list = []
    tool_results: dict[str, str] = {}
    final_answer = ""

    for update in agent.stream({"messages": messages}, stream_mode="updates"):
        for _node, state in update.items():
            if not state:
                continue
            for msg in state.get("messages", []):
                new_messages.append(msg)
                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            _internal(f"[ → ] {tc['name']}({_brief_args(tc['args'])})")
                    elif msg.content:
                        content = _strip_tokens(msg.content)
                        if content:
                            final_answer = content
                            _box(content)
                elif isinstance(msg, ToolMessage):
                    tool_results[msg.name] = msg.content
                    _internal(f"[ ← ] {msg.name}: {_brief_result(msg.content)}")

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

            active_plan = crud.get_active_plan(trainee.id)
            intent = classify_intent(
                user_input,
                has_active_plan=active_plan is not None,
                memory_snippet=memory[:400],
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
