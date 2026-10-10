"""Recognize tool failures returned as data by agent tools."""
import json
from typing import Any


def tool_result_error(output: Any) -> str | None:
    if getattr(output, "status", None) == "error":
        return str(getattr(output, "content", output)) or "Tool failed"
    value = getattr(output, "content", output)
    if isinstance(value, str):
        if value.startswith(("Invalid tool input:", "Error invoking tool", "Error:")):
            return value
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict) and value.get("error"):
        return str(value["error"])
    return None
