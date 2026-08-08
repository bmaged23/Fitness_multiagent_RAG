from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

import httpx
from langchain_openai import ChatOpenAI
from config.settings import (
    VLLM_BASE_URL,
    VLLM_MODEL,
    VLLM_API_KEY,
    VLLM_TIMEOUT,
    VLLM_TEMPERATURE,
    VLLM_MAX_CONCURRENT_REQUESTS,
)

_model: ChatOpenAI | None = None


def get_model() -> ChatOpenAI:
    global _model
    if _model is None:
        _model = ChatOpenAI(
            base_url=VLLM_BASE_URL,
            api_key=VLLM_API_KEY,
            model=VLLM_MODEL,
            temperature=VLLM_TEMPERATURE,
            timeout=VLLM_TIMEOUT,
            http_client=httpx.Client(
                limits=httpx.Limits(
                    max_connections=VLLM_MAX_CONCURRENT_REQUESTS,
                    max_keepalive_connections=VLLM_MAX_CONCURRENT_REQUESTS,
                )
            ),
        )
    return _model
