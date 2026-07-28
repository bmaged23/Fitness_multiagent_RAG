"""
Run the Retriever agent with full streaming output.

Shows every tool call (name + args), its result, and the final LLM answer.

Usage:
    python main.py                          # uses the default hardcoded query
    python main.py "your custom query here"
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

from fitness_multiagent_rag.agents.retriever.agent import build_retriever_agent


DIVIDER  = "─" * 60
HDIVIDER = "═" * 60


def _fmt_args(args: dict) -> str:
    try:
        return json.dumps(args, indent=2, ensure_ascii=False)
    except Exception:
        return str(args)


def _strip_model_tokens(text: str) -> str:
    """Remove Gemma internal channel/thought tokens from model output."""
    text = re.sub(r'<\|channel>.*?<channel\|>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[|]?channel[|]?[^>]*>', '', text)
    return text.strip()


def _fmt_result(content: str, max_chars: int = 500) -> str:
    content = str(content)
    if len(content) > max_chars:
        return content[:max_chars] + f"\n  ... [{len(content) - max_chars} chars truncated]"
    return content


def run(query: str) -> None:
    print(f"\n{HDIVIDER}")
    print(f"  RETRIEVER AGENT")
    print(f"{HDIVIDER}")
    print(f"  Query: {query}")
    print(f"{HDIVIDER}\n")

    agent = build_retriever_agent()
    step  = 0

    for update in agent.stream(
        {"messages": [HumanMessage(content=query)]},
        stream_mode="updates",
    ):
        for node_name, state in update.items():
            if not state:
                continue
            messages = state.get("messages", [])

            for msg in messages:

                # ── Agent reasoning: tool calls it decided to make ──────────
                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            step += 1
                            print(f"[Step {step}] TOOL CALL  →  {tc['name']}")
                            print(DIVIDER)
                            print(_fmt_args(tc["args"]))
                            print()

                    elif msg.content:
                        print(DIVIDER)
                        print("FINAL ANSWER")
                        print(DIVIDER)
                        print(_strip_model_tokens(msg.content))
                        print(f"\n{HDIVIDER}\n")

                # ── Tool result ──────────────────────────────────────────────
                elif isinstance(msg, ToolMessage):
                    print(f"[Step {step}] TOOL RESULT ←  {msg.name}")
                    print(DIVIDER)
                    print(_fmt_result(msg.content))
                    print()


if __name__ == "__main__":
    DEFAULT_QUERY = (
    "I need a 3-day beginner workout program for muscle building using only dumbbells at home"
    )
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    run(query)

