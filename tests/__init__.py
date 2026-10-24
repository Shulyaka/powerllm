"""Tests for the Power LLM integration."""

from typing import Any

from homeassistant.helpers import llm


def tool_result_data(result: llm.ToolResult) -> dict[str, Any]:
    """Validate a successful native result and return its JSON object."""
    assert isinstance(result, llm.ToolResult)
    assert result.error is False
    assert isinstance(result.data, dict)
    return result.data
