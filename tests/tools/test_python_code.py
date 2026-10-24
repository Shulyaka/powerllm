"""Test python script tool."""

import asyncio
import logging
from threading import Barrier
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.powerllm.tools import python_code

SCRIPT_LOGGER_NAME = "custom_components.powerllm.tools.python_code.script"


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
    logger = logging.getLogger(SCRIPT_LOGGER_NAME)
    handlers = logger.handlers.copy()

    with pytest.raises(HomeAssistantError, match=message):
        await async_call_tool("python_code_execute", source=source)

    assert logger.handlers == handlers


@pytest.mark.parametrize(
    ("source", "logger_name"),
    [
        ("logger.info('value %s', 42)", SCRIPT_LOGGER_NAME),
        (
            "import logging\nlogging.getLogger('another.name').info('value %s', 42)",
            SCRIPT_LOGGER_NAME,
        ),
        (
            "logger.getChild('child').getChild('nested').info('value %s', 42)",
            f"{SCRIPT_LOGGER_NAME}.child.nested",
        ),
        (
            "import logging\nlogging.getLogger('other').getChild('child').info('value %s', 42)",
            f"{SCRIPT_LOGGER_NAME}.child",
        ),
    ],
)
async def test_python_script_logs_are_per_call(
    async_call_tool,
    caplog: pytest.LogCaptureFixture,
    source: str,
    logger_name: str,
) -> None:
    """Keep previous messages out of later results while propagating HA logs."""
    logger = logging.getLogger(SCRIPT_LOGGER_NAME)
    handlers = logger.handlers.copy()
    logger_names = {
        name
        for name in logging.Logger.manager.loggerDict
        if name.startswith(SCRIPT_LOGGER_NAME)
    }

    with caplog.at_level(logging.DEBUG, logger=SCRIPT_LOGGER_NAME):
        logger.setLevel(logging.WARNING)
        first = await async_call_tool("python_code_execute", source=source)
        second = await async_call_tool(
            "python_code_execute", source="output['value'] = 2"
        )
        assert logger.level == logging.WARNING

    assert first == {"output": {}, "logs": [{"level": logging.INFO, "msg": "value 42"}]}
    assert second == {"output": {"value": 2}}
    assert any(
        record.name == logger_name and record.getMessage() == "value 42"
        for record in caplog.records
    )
    assert logger.handlers == handlers
    assert {
        name
        for name in logging.Logger.manager.loggerDict
        if name.startswith(SCRIPT_LOGGER_NAME)
    } == logger_names


async def test_python_script_respects_disabled_logging(async_call_tool) -> None:
    """Honor the application's global logging threshold for new executions."""
    threshold = logging.Logger.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        response = await async_call_tool(
            "python_code_execute", source="logger.warning('disabled-call')"
        )
    finally:
        logging.disable(threshold)

    assert response == {"output": {}}


async def test_python_script_failed_logs_do_not_leak(async_call_tool) -> None:
    """Discard failed execution capture before another request starts."""
    logger = logging.getLogger(SCRIPT_LOGGER_NAME)
    handlers = logger.handlers.copy()

    with pytest.raises(HomeAssistantError, match="ZeroDivisionError"):
        await async_call_tool(
            "python_code_execute", source="logger.warning('failed-call')\n1 / 0"
        )

    response = await async_call_tool(
        "python_code_execute", source="output['value'] = 2"
    )

    assert response == {"output": {"value": 2}}
    assert logger.handlers == handlers


async def test_python_script_concurrent_logs_are_isolated(async_call_tool) -> None:
    """Capture only the requesting execution even while both calls are logging."""
    started = Barrier(2)
    finished = Barrier(2)
    execute = python_code.execute

    def concurrent_execute(*args, **kwargs):
        started.wait(timeout=10)
        result = execute(*args, **kwargs)
        finished.wait(timeout=10)
        return result

    with patch.object(python_code, "execute", side_effect=concurrent_execute):
        first, second = await asyncio.gather(
            async_call_tool(
                "python_code_execute",
                source="logger.getChild('shared').info('first-call')",
            ),
            async_call_tool(
                "python_code_execute",
                source="import logging\nlogging.getLogger('other').getChild('shared').warning('second-call')",
            ),
        )

    assert first == {
        "output": {},
        "logs": [{"level": logging.INFO, "msg": "first-call"}],
    }
    assert second == {
        "output": {},
        "logs": [{"level": logging.WARNING, "msg": "second-call"}],
    }
