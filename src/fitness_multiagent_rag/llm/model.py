from __future__ import annotations

from langchain_groq import ChatGroq

from config.settings import (   # or `from config.settings import` until you move it
    GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE,
    GROQ_TIMEOUT, GROQ_MAX_TOKENS, GROQ_MAX_RETRIES,
)

_model: ChatGroq | None = None


def get_model() -> ChatGroq:
    global _model
    if _model is None:
        if not GROQ_API_KEY:
            raise EnvironmentError("GROQ_API_KEY is not set. Add it to your .env file.")
        _model = ChatGroq(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            temperature=GROQ_TEMPERATURE,
            timeout=GROQ_TIMEOUT,
            max_tokens=GROQ_MAX_TOKENS,
            max_retries=GROQ_MAX_RETRIES,
        )
    return _model

