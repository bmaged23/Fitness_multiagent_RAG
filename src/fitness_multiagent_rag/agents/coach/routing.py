from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt

_AGENT_DIR      = Path(__file__).parent
_ROUTING_PROMPT = load_agent_prompt(_AGENT_DIR, "routing_prompts.md")

INTENTS = (
    "new_plan",       # trainee wants a brand-new workout program
    "revision",       # trainee wants to change their existing plan
    "exercise_lookup",# question about specific exercises / muscles (not a full plan)
    "log_progress",   # trainee reporting a completed workout or body-weight update
    "plan_question",  # question about their current plan (today's session, week number, etc.)
    "general_chat",   # fitness / nutrition / health conversation, motivation
    "intake",         # new trainee or profile update needed
)


class _IntentResult(BaseModel):
    intent: str
    confidence: float


def classify_intent(
    user_message: str,
    has_active_plan: bool,
    memory_snippet: str = "",
) -> str:
    """Return the most likely intent string for the given user message.
    Falls back to 'general_chat' on any parsing failure.
    """
    prompt = (
        _ROUTING_PROMPT
        .replace("{user_message}", user_message)
        .replace("{has_active_plan}", str(has_active_plan))
        .replace("{memory_snippet}", memory_snippet[:400] if memory_snippet else "none")
    )
    try:
        result = structured_chat(
            [
                SystemMessage(content="You are an intent classifier for a fitness coaching system."),
                HumanMessage(content=prompt),
            ],
            _IntentResult,
        )
        return result.intent if result.intent in INTENTS else "general_chat"
    except Exception:
        return "general_chat"
