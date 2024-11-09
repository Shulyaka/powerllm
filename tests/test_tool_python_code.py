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
    """Test function tools with async function."""
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
