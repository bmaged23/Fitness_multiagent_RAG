from __future__ import annotations

from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import (
    LLM_PROVIDER,  # default provider name, e.g. "groq" or "ollama"
    GROQ_API_KEY, GROQ_MODEL, GROQ_TEMPERATURE,
    GROQ_TIMEOUT, GROQ_MAX_TOKENS, GROQ_MAX_RETRIES,
    OLLAMA_API_KEY, OLLAMA_MODEL, OLLAMA_BASE_URL,
)

_models: dict[str, BaseChatModel] = {}


# --------------------------------------------------
# Provider builders (imports are lazy, so an
# unused provider's package doesn't need installing)
# --------------------------------------------------

def _build_groq() -> BaseChatModel:
    from langchain_groq import ChatGroq

    if not GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY is not set. Add it to your .env file.")

    return ChatGroq(
        model=GROQ_MODEL,
        api_key=GROQ_API_KEY,
        temperature=GROQ_TEMPERATURE,
        timeout=GROQ_TIMEOUT,
        max_tokens=GROQ_MAX_TOKENS,
        max_retries=GROQ_MAX_RETRIES,
    )


def _build_ollama() -> BaseChatModel:
    from langchain_ollama import ChatOllama

    kwargs = {}
    if OLLAMA_API_KEY:  # needed for ollama.com cloud, not for a local daemon
        kwargs["client_kwargs"] = {
            "headers": {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
        }

    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
        **kwargs,
    )


# --------------------------------------------------
# Registry: add a new provider here
# --------------------------------------------------

_PROVIDERS: dict[str, Callable[[], BaseChatModel]] = {
    "groq": _build_groq,
    "ollama": _build_ollama,
}


def get_model(provider: str | None = None) -> BaseChatModel:
    """Return a cached chat model for `provider`.

    Falls back to LLM_PROVIDER from settings when `provider` is None.
    """
    name = (provider or LLM_PROVIDER).strip().lower()

    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider '{name}'. "
            f"Available: {', '.join(sorted(_PROVIDERS))}"
        )

    if name not in _models:
        _models[name] = _PROVIDERS[name]()

    return _models[name]


