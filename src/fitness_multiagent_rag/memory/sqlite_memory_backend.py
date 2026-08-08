from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage

from config.settings import (
    MEMORY_TRUNCATION_SESSION_COUNT,
    MEMORY_TRUNCATION_CHAR_THRESHOLD,
)
from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import CoachMemory
from fitness_multiagent_rag.llm.client import chat


_SALIENCE_SYSTEM = (
    "You are a coaching assistant compressing session notes into a concise memory summary."
)
_SALIENCE_PROMPT = """Compress the coaching notes below into a concise summary (max 500 words).

Keep: trainee goals, injuries, preferences, recurring struggles, achievements, key coaching decisions.
Drop: generic motivational exchanges, routine confirmations, repeated check-ins.

Notes:
{text}

Return only the compressed summary — no headers, no bullet labels."""


class CoachMemoryBackend:
    """Reads and writes coach_memory via SQLite. Triggers salience truncation automatically."""

    def load(self, trainee_id: int) -> str:
        mem = crud.get_memory(trainee_id)
        return mem.summary_text if mem else ""

    def save(self, trainee_id: int, new_content: str) -> None:
        mem = crud.get_memory(trainee_id)
        if mem:
            combined = (mem.summary_text + "\n\n" + new_content).strip()
            mem.summary_text = combined
        else:
            mem = CoachMemory(trainee_id=trainee_id, summary_text=new_content)
        crud.upsert_memory(mem)

    def end_session(self, trainee_id: int) -> bool:
        """Increment session counter; run salience pass if thresholds exceeded.
        Returns True if truncation occurred."""
        count = crud.increment_session_count(trainee_id)
        mem = crud.get_memory(trainee_id)
        if not mem:
            return False
        should_truncate = (
            count >= MEMORY_TRUNCATION_SESSION_COUNT
            or len(mem.summary_text) > MEMORY_TRUNCATION_CHAR_THRESHOLD
        )
        if should_truncate:
            compressed = self._salience_pass(mem.summary_text)
            mem.summary_text = compressed
            mem.session_count_since_truncation = 0
            crud.upsert_memory(mem)
            crud.reset_session_count(trainee_id)
            return True
        return False

    def _salience_pass(self, text: str) -> str:
        prompt = _SALIENCE_PROMPT.replace("{text}", text)
        return chat([
            SystemMessage(content=_SALIENCE_SYSTEM),
            HumanMessage(content=prompt),
        ])
