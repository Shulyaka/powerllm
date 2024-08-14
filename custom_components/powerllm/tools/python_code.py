"""Dynamic script execution tool."""

import logging

from homeassistant.components.python_script import execute
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..llm_tools import llm_tool

_LOGGER = logging.getLogger(__name__)


class MyHandler(logging.Handler):
    """Log handler that saves the logs in memory."""

    logs: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord):
        """Save the record."""
        self.logs.append(record)


def async_setup_tool(hass: HomeAssistant):
    """Add the tool."""

    @llm_tool(hass)
    def python_code_execute(hass: HomeAssistant, source: str, data: dict | None = None):
        """Execute python code in a restricted environment.

        Use this tool for math calculations among other things.
        Use `output` dictionary for output and `logger` object for logging.
        """
        log_handler = MyHandler()
        logger = logging.getLogger("homeassistant.components.python_script.source")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(log_handler)
        try:
            output = execute(hass, "source", source, data, return_response=True)
        except HomeAssistantError as e:
            output = {"error": type(e).__name__}
            if str(e):
                output["error_text"] = str(e)
        logger.removeHandler(log_handler)

        result = {"output": output}
        logs = [
            {"level": record.levelno, "msg": record.getMessage()}
            for record in log_handler.logs
        ]
        if logs:
            result["logs"] = logs
        return result
