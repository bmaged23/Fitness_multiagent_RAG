
from __future__ import annotations

import json
import os
import re
from typing import TypeVar

from groq import BadRequestError
from pydantic import BaseModel, ValidationError
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
)

from .model import get_model


T = TypeVar("T", bound=BaseModel)

_STRUCTURED_METHOD = os.getenv(
    "GROQ_STRUCTURED_METHOD",
    "function_calling",
)


# --------------------------------------------------
# Plain text completion
# --------------------------------------------------

def chat(messages: list[BaseMessage]) -> str:
    """Generate a plain text response."""
    response = get_model().invoke(messages)

    content = response.content

    if isinstance(content, str):
        return content.strip()

    return str(content).strip()


# --------------------------------------------------
# Groq error helpers
# --------------------------------------------------

def _failed_generation(err: BadRequestError) -> str | None:
    """Extract raw model output from Groq tool_use_failed errors."""

    body = getattr(err, "body", None)

    if not isinstance(body, dict):
        return None

    error = body.get("error", body)

    if not isinstance(error, dict):
        return None

    raw = error.get("failed_generation")

    return raw if isinstance(raw, str) else None


def _is_tool_use_failed(err: BadRequestError) -> bool:
    """Identify Groq's specific tool-calling failure."""

    body = getattr(err, "body", None)

    if not isinstance(body, dict):
        return False

    error = body.get("error", body)

    if not isinstance(error, dict):
        return False

    return error.get("code") == "tool_use_failed"


# --------------------------------------------------
# JSON parsing
# --------------------------------------------------

def _extract_json(text: str):
    """Extract the first valid JSON object or array from model text."""

    text = text.strip()

    # First try parsing the entire response.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Handle Markdown code fences.
    fence = re.search(
        r"```(?:json)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Find valid JSON after explanatory or reasoning text.
    decoder = json.JSONDecoder()

    for index, char in enumerate(text):
        if char not in "{[":
            continue

        try:
            result, _ = decoder.raw_decode(text[index:])
            return result
        except json.JSONDecodeError:
            continue

    raise ValueError("No valid JSON object or array found in model output")


def _parse(raw: str, schema: type[T]) -> T:
    """Parse model-generated JSON into the requested Pydantic schema."""

    data = _extract_json(raw)

    # Support single-field schemas wrapping a list.
    if isinstance(data, list) and len(schema.model_fields) == 1:
        field_name = next(iter(schema.model_fields))
        data = {field_name: data}

    return schema.model_validate(data)


def _content_to_text(content) -> str:
    """Convert LangChain message content into text."""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)

            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))

        return "\n".join(parts)

    return str(content)


# --------------------------------------------------
# JSON fallback
# --------------------------------------------------

def _json_fallback(
    messages: list[BaseMessage],
    schema: type[T],
) -> T:
    """
    Request a JSON response without forcing a tool call.

    The returned content is still validated against
    the requested Pydantic schema.
    """

    schema_json = json.dumps(
        schema.model_json_schema(),
        ensure_ascii=False,
    )

    instructions = (
        "Return exactly one valid JSON object matching this schema:\n"
        f"{schema_json}\n\n"
        "Use JSON booleans true/false, not TRUE/FALSE.\n"
        "Do not return Markdown, explanations, or reasoning.\n"
        "Do not return a bare boolean or bare string."
    )

    fallback_messages = [
        SystemMessage(content=instructions),
        *messages,
    ]

    response = get_model().invoke(fallback_messages)

    raw = _content_to_text(response.content)

    if not raw.strip():
        raise ValueError(
            f"Empty model response for {schema.__name__}"
        )

    return _parse(raw, schema)


# --------------------------------------------------
# Structured output
# --------------------------------------------------

def structured_chat(
    messages: list[BaseMessage],
    schema: type[T],
    retries: int = 1,
) -> T:
    """
    Generate structured output with:
    1. Native structured output.
    2. Groq failed-generation recovery.
    3. Plain JSON fallback.
    4. Pydantic validation.
    """

    model = get_model()

    runnable = model.with_structured_output(
        schema,
        method=_STRUCTURED_METHOD,
    )

    last_err: Exception | None = None

    for attempt in range(retries + 1):

        try:
            result = runnable.invoke(messages)

            if result is None:
                raise ValueError(
                    f"Model returned None for {schema.__name__}"
                )

            if isinstance(result, schema):
                return result

            if isinstance(result, str):
                return _parse(result, schema)

            return schema.model_validate(result)

        except BadRequestError as error:

            # Only recover from the known Groq tool-use failure.
            # Other HTTP 400 errors should propagate unchanged.
            if not _is_tool_use_failed(error):
                raise

            last_err = error

            raw = _failed_generation(error)

            if raw:
                try:
                    return _parse(raw, schema)
                except (ValidationError, ValueError) as parse_error:
                    last_err = parse_error

            print(
                f"[structured_chat] "
                f"{schema.__name__} "
                f"attempt {attempt + 1}/{retries + 1}: "
                f"{last_err}",
                flush=True,
            )

        except (ValidationError, ValueError) as error:

            last_err = error

            print(
                f"[structured_chat] "
                f"{schema.__name__} "
                f"attempt {attempt + 1}/{retries + 1}: "
                f"{error}",
                flush=True,
            )

        # Fallback after a structured-output formatting failure.
        try:
            return _json_fallback(messages, schema)

        except BadRequestError:
            # Do not hide Groq HTTP errors such as rate limits
            # or unsupported request parameters.
            raise

        except (ValidationError, ValueError) as fallback_error:

            last_err = fallback_error

            print(
                f"[structured_chat] "
                f"JSON fallback failed for {schema.__name__}: "
                f"{fallback_error}",
                flush=True,
            )

    raise ValueError(
        f"Structured output for {schema.__name__} "
        f"failed after {retries + 1} attempts: {last_err}"
    )


