from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import re
from difflib import get_close_matches

from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage

from fitness_multiagent_rag.llm.client import structured_chat
from fitness_multiagent_rag.utils.prompt_loader import load_agent_prompt

_AGENT_DIR      = Path(__file__).parent
_ROUTING_PROMPT = load_agent_prompt(_AGENT_DIR, "routing_prompts.md")

INTENTS = (
    "nutrition_plan", # create, show, approve, or revise a nutrition/meal plan
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



def plan_topic(user_message: str, previous_reply: str = "") -> str | None:
    """Resolve explicit plan subjects, including nutrition typos, before context."""
    words = re.findall(r"[a-z]+", user_message.casefold())
    nutrition_words = {"nutrition", "nutritional", "diet", "dietary", "meal", "meals", "food", "calories", "macros"}
    if any(w in nutrition_words or (len(w) >= 7 and get_close_matches(w, ["nutrition"], n=1, cutoff=.72)) for w in words):
        return "nutrition"
    if set(words) & {"workout", "fitness", "exercise", "exercises", "training"}:
        return "workout"
    if previous_reply:
        return plan_topic(previous_reply)
    return None

def classify_intent(
    user_message: str,
    has_active_plan: bool,
    memory_snippet: str = "",
    previous_reply: str = "",
) -> str:
    """Return the most likely intent string for the given user message.
    Falls back to 'general_chat' on any parsing failure.
    """
    if plan_topic(user_message, previous_reply) == "nutrition":
        return "nutrition_plan"
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


def draft_action(user_message: str, draft: dict, previous_reply: str = "") -> str | None:
    """Resolve requests to view an existing draft before classifying a new plan."""
    import re
    text = ' '.join(re.findall(r"[\w']+", user_message.casefold()))
    if plan_topic(user_message, previous_reply) == "nutrition":
        return None
    if not draft or re.search(r'\b(new|another|different|restart|replace|change|instead)\b', text):
        return None
    asks_to_view = bool(re.search(r'\b(show|see|view|display|details|detailed)\b', text))
    mentions_plan = bool(re.search(r'\b(program|plan|workout|routine|exercises|details)\b', text))
    approves_structure = text in {'yes', 'okay', 'ok', 'sure', 'go ahead', 'looks good', 'yes please'}
    if draft.get('stage') == 'structure' and ((asks_to_view and mentions_plan) or approves_structure):
        return 'generate_week1'
    if draft.get('stage') == 'week1' and asks_to_view and mentions_plan:
        return 'show_week1'
    return None
