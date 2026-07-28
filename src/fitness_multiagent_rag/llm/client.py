from __future__ import annotations

from typing import TypeVar
from pydantic import BaseModel
from langchain_core.messages import BaseMessage

from .model import get_model

T = TypeVar("T", bound=BaseModel)


def chat(messages: list[BaseMessage]) -> str:
    response = get_model().invoke(messages)
    return response.content.strip()


def structured_chat(messages: list[BaseMessage], schema: type[T]) -> T:
    """Call the model and parse the response directly into a Pydantic model."""
    return get_model().with_structured_output(schema).invoke(messages)
