"""
Interactive test runner for the Program Designer agent.

Runs the full 3-stage flow with clean visual separation between:
  - Internal tool calls (dim, one-liner)
  - Designer messages to the user (boxed)
  - User input prompts (clearly marked)

The runner maintains a shared VFS backend across all 3 stages so
write_file / read_file work naturally between Stage 1 → 2 → 3.

Usage:
    python main.py                          # default request, trainee_id=1
    python main.py "your custom request"    # custom request, trainee_id=1
    python main.py "request" 3              # custom request, trainee_id=3
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_SRC_DIR.parent))

from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from deepagents.backends import FilesystemBackend

from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import Trainee
from fitness_multiagent_rag.agents.designer.agent import build_designer_agent

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

DEFAULT_REQUEST = (
    "Create a 3-day beginner full-body workout plan for muscle building "
    "using dumbbell-only equipment, 8 weeks."
)

TEST_TRAINEE = Trainee(
    name="Test User",
    secondary_id="test@example.com",
    age=25,
    gender="Male",
    fitness_level="Beginner",
    equipment_available=["Dumbbell Only"],
    injuries_limitations=None,
    goal="Bodybuilding",
)

# ── ANSI styles ─────────────────────────────────────────────────────
_DIM   = "\033[2m"       # dim gray — for internal tool lines
_BOLD  = "\033[1m"
_CYAN  = "\033[96m"
_RST   = "\033[0m"


# ── Display helpers ──────────────────────────────────────────────────

def _strip_tokens(text: str) -> str:
    text = re.sub(r"<\|channel>.*?<channel\|>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[|]?channel[|]?[^>]*>", "", text)
    return text.strip()


def _internal(msg: str) -> None:
    """Dim one-liner for tool calls / results — clearly internal."""
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


def _box(text: str, label: str = "Designer") -> None:
    """Print the designer's message to the user in a bordered box."""
    lines = text.strip().split("\n")
    inner = max(64, *(len(l) for l in lines)) + 2
    bar   = "═" * inner

    print()
    print(f"{_CYAN}╔{bar}╗{_RST}")
    hdr = f"  {_BOLD}{label}{_RST}{_CYAN}"
    print(f"{_CYAN}║{hdr}{' ' * (inner - 2 - len(label))}║{_RST}")
    print(f"{_CYAN}╠{bar}╣{_RST}")
    for line in lines:
        pad = " " * (inner - 2 - len(line))
        print(f"{_CYAN}║{_RST}  {line}{pad}  {_CYAN}║{_RST}")
    print(f"{_CYAN}╚{bar}╝{_RST}")
    print()


def _stage_banner(title: str) -> None:
    print(f"\n  {_DIM}{'─' * 66}{_RST}")
    print(f"  {_DIM}{title}{_RST}")
    print(f"  {_DIM}{'─' * 66}{_RST}\n")


def _prompt_user(hint: str = "approve or describe changes — Enter to approve") -> str:
    """Prompt the user for input with a clear visual marker."""
    print(f"  {_CYAN}{'─' * 66}{_RST}")
    try:
        answer = input(f"  {_BOLD}You › {_RST}").strip()
    except EOFError:
        answer = ""
    print()
    return answer


# ── Setup ────────────────────────────────────────────────────────────

def _ensure_test_trainee(trainee_id: int) -> Trainee:
    trainee = crud.get_trainee_by_id(trainee_id)
    if trainee:
        return trainee
    created = crud.create_trainee(TEST_TRAINEE)
    _internal(f"[setup] Created test trainee id={created.id} — '{created.name}'")
    return created


# ── Core streaming helper ────────────────────────────────────────────

def _stream_turn(
    agent,
    messages: list,
) -> tuple[str, list, dict[str, str]]:
    """Stream one agent invocation.

    Returns:
        final_answer   — last non-tool-call AI text (shown in the box)
        new_messages   — all messages emitted this turn (for history accumulation)
        tool_results   — {tool_name: raw_content}
    """
    new_messages: list = []
    tool_results: dict[str, str] = {}
    final_answer = ""
    step = 0

    for update in agent.stream(
        {"messages": messages},
        stream_mode="updates",
    ):
        for _node, state in update.items():
            if not state:
                continue
            for msg in state.get("messages", []):
                new_messages.append(msg)

                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            step += 1
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


# ── State extraction ─────────────────────────────────────────────────

def _extract_structure_json(tool_results: dict[str, str]) -> str:
    raw = tool_results.get("propose_plan_structure", "")
    if not raw:
        return ""
    try:
        return json.loads(raw).get("structure_json", "")
    except Exception:
        return ""


def _extract_week1_plan_json(tool_results: dict[str, str]) -> str:
    raw = tool_results.get("synthesize_week_one", "")
    if not raw:
        return ""
    try:
        return json.loads(raw).get("week1_plan_json", "")
    except Exception:
        return ""


# ── Main interactive runner ──────────────────────────────────────────

def run_interactive(request: str, trainee_id: int = 1) -> None:
    trainee = _ensure_test_trainee(trainee_id)

    print(f"\n{_CYAN}{'═' * 70}{_RST}")
    print(f"{_CYAN}  {_BOLD}PROGRAM DESIGNER — INTERACTIVE{_RST}{_CYAN}  {_RST}")
    print(f"{_CYAN}{'═' * 70}{_RST}")
    print(f"  Trainee  : {trainee.name} (id={trainee.id})")
    print(f"  Level    : {trainee.fitness_level}  |  Goal: {trainee.goal}")
    print(f"  Equipment: {', '.join(trainee.equipment_available or [])}")
    print(f"  Request  : {request}")
    print(f"{_CYAN}{'═' * 70}{_RST}\n")

    # Shared VFS backend — plan_structure.json and plan_week1.json persist
    # across all 3 stages so Stage 2/3 can read_file what Stage 1/2 wrote.
    backend = FilesystemBackend(root_dir=str(_PROJECT_ROOT), virtual_mode=True)

    # ── Phase 1: Stage 0 pre-flight + Stage 1 structure proposal ──────────
    # Multi-turn: the agent may pause at Stage 0 to ask profile questions,
    # then continue to Stage 1 after the user answers.
    _stage_banner("Stage 0 + 1  —  Pre-flight check & structure proposal")

    messages: list = [HumanMessage(content=f"trainee_id: {trainee.id}\nrequest: {request}")]
    structure_json = ""

    for _turn in range(6):
        _, new_msgs, tool_results = _stream_turn(build_designer_agent(backend), messages)
        messages.extend(new_msgs)

        structure_json = _extract_structure_json(tool_results)
        if structure_json:
            break  # Stage 1 complete

        # Agent is waiting for user input (Stage 0 questions or clarification)
        user_input = _prompt_user("your answer")
        if user_input.lower() in ("quit", "exit", "done", "q"):
            return
        messages.append(HumanMessage(content=user_input))

    if not structure_json:
        print("  [No structure proposed — check the output above.]\n")
        return

    # User approves or modifies the structure
    user_input1 = _prompt_user("approve the structure or describe changes")
    if user_input1.lower() in ("quit", "exit", "done", "q"):
        return

    # ── Phase 2: Stage 2 — Week 1 exercises ───────────────────────────────
    _stage_banner("Stage 2  —  Generating Week 1 exercises")

    msg2 = (
        f"STAGE 2\n"
        f"trainee_id: {trainee.id}\n"
        f"The user reviewed the structure and said: "
        f"\"{user_input1 or 'Looks good, proceed to exercises.'}\"\n"
        f"Apply any requested changes, then call synthesize_week_one."
    )
    _, _, tool_results2 = _stream_turn(
        build_designer_agent(backend),
        [HumanMessage(content=msg2)],
    )
    week1_plan_json = _extract_week1_plan_json(tool_results2)

    if not week1_plan_json:
        print("  [No Week 1 plan generated — check the output above.]\n")
        return

    # User approves or requests final changes
    user_input2 = _prompt_user("approve Week 1 or request final changes")
    if user_input2.lower() in ("quit", "exit", "done", "q"):
        return

    # ── Phase 3: Stage 3 — Validate and save ──────────────────────────────
    _stage_banner("Stage 3  —  Validating and saving")

    msg3 = (
        f"STAGE 3\n"
        f"trainee_id: {trainee.id}\n"
        f"The user confirmed: \"{user_input2 or 'Looks good, save the plan.'}\"\n"
        f"Apply any final changes, then validate and save."
    )
    _stream_turn(
        build_designer_agent(backend),
        [HumanMessage(content=msg3)],
    )

    print(f"\n{_CYAN}{'═' * 70}{_RST}")
    print(f"  {_BOLD}Plan saved successfully!{_RST}")
    print(f"{_CYAN}{'═' * 70}{_RST}\n")


if __name__ == "__main__":
    request    = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REQUEST
    trainee_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    run_interactive(request, trainee_id)
