"""Test python script tool."""

import logging

import pytest
from homeassistant.exceptions import HomeAssistantError


async def test_python_script_tool(async_call_tool) -> None:
    """Test python script tool."""

    source = """
output["test"] = "passed"
output["test2"] = "passed2"
    """

    response = await async_call_tool("python_code_execute", source=source)

    assert response == {"output": {"test": "passed", "test2": "passed2"}}


async def test_python_script_tool_import(async_call_tool) -> None:
    """Test python script tool with import."""

    source = """
import math
output["test"] = math.cos(0)
    """

    response = await async_call_tool("python_code_execute", source=source)

    assert response == {"output": {"test": 1.0}}


async def test_python_script_tool_print(async_call_tool) -> None:
    """Test print in python script tool."""

    source = """
print("test1")
def test2():
    print("test2")

test2()
    """

    response = await async_call_tool("python_code_execute", source=source)

    assert response == {"printed": "test1\ntest2\n"}


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("output[", "Compile error"),
        ("output['result'] = 1 / 0", "ZeroDivisionError"),
        ("hass.async_stop()", "Not allowed to access async methods"),
    ],
)
async def test_python_script_tool_error(
    async_call_tool, source: str, message: str
) -> None:
    """Propagate script failures and always remove the temporary log handler."""
    logger = logging.getLogger("custom_components.powerllm.tools.python_code.script")
    handlers = logger.handlers.copy()

    with pytest.raises(HomeAssistantError, match=message):
        await async_call_tool("python_code_execute", source=source)

    assert logger.handlers == handlers
