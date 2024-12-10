"""Test powerllm config flow."""

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm


@pytest.fixture
def llm_context() -> llm.LLMContext:
    """Return tool input context."""
    return llm.LLMContext(
        platform="test_platform",
        context=Context(),
        user_prompt=None,
        language=None,
        assistant=None,
        device_id=None,
    )


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


async def test_python_script_tool(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test python script tool."""
    api = await llm.async_get_api(hass, "powerllm", llm_context)

    source = """
output["test"] = "passed"
output["test2"] = "passed2"
    """

    tool_input = llm.ToolInput(
        tool_name="python_code_execute",
        tool_args={"source": source},
    )

    response = await api.async_call_tool(tool_input)

    assert response == {"output": {"test": "passed", "test2": "passed2"}}


async def test_python_script_tool_import(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test python script tool with import."""
    api = await llm.async_get_api(hass, "powerllm", llm_context)

    source = """
import math
output["test"] = math.cos(0)
    """

    tool_input = llm.ToolInput(
        tool_name="python_code_execute",
        tool_args={"source": source},
    )

    response = await api.async_call_tool(tool_input)

    assert response == {"output": {"test": 1.0}}


async def test_python_script_tool_print(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test print in python script tool."""
    api = await llm.async_get_api(hass, "powerllm", llm_context)

    source = """
print("test1")
def test2():
    print("test2")

test2()
    """

    tool_input = llm.ToolInput(
        tool_name="python_code_execute",
        tool_args={"source": source},
    )

    response = await api.async_call_tool(tool_input)

    assert response == {"printed": "test1\ntest2\n"}
