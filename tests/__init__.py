"""Tests for the Power LLM integration."""

from typing import Any

from homeassistant.helpers import llm


def tool_result_data(result: Any) -> Any:
    """Validate successful API results and return their JSON data across versions."""
    if tool_result_type := getattr(llm, "ToolResult", None):
        assert isinstance(result, tool_result_type)
        assert result.error is False
        return result.data
    return result
