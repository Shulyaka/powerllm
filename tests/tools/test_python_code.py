"""Test python script tool."""


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


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
