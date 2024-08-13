"""Dynamic script execution tool."""

import logging
from asyncio import create_task, shield, timeout

import voluptuous as vol
from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.helpers.script import Script
from homeassistant.util.json import JsonObjectType
from homeassistant.util.yaml.loader import parse_yaml

from ..const import DOMAIN
from ..llm_tools import PowerLLMTool

_LOGGER = logging.getLogger(__name__)

SCRIPT_TIMEOUT = 3


class DynamicScriptTool(PowerLLMTool):
    """Tool to execute LLM-written scripts."""

    name = "homeassistant_script"
    description = (
        "Execute arbitrary scripts in this Home Assistant instance. Only use this "
        "function if other tools do not provide required functionality or fail."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                "script",
                description="The script in Home Assistant yaml script format. "
                "This is the same format as the action part of a HA automation. "
                "Don't use milliseconds for delay time.",
            ): vol.Any(cv.string, [cv.string])
        }
    )

    def __init__(self, exposed_only=True):
        """Initialize the tool."""
        self._exposed_only = exposed_only

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Execute a script in Home Assistant."""
        context = llm_context.context
        script = tool_input.tool_args["script"]

        if isinstance(script, str):
            script = parse_yaml(script)

        if isinstance(script, list) and len(script) == 1:
            script = script[0]

        try:
            # check if AI decided to list actions at top level or inside a sequence key
            action = cv.determine_script_action(script)
            if "sequence" in script:
                raise RuntimeError(
                    f'The "{action}" action should be inside the "sequence" list, '
                    "please rewrite the script"
                )
            sequence = [script]
        except ValueError:
            if "trigger" in script:
                raise RuntimeError(
                    "This is a script, not an automation. "
                    "Please rewrite without triggers."
                )
            sequence = script["sequence"]

        _LOGGER.debug("Parsed sequence: %s", sequence)

        script = Script(
            hass, sequence=sequence, name="convesation_scipt", domain=DOMAIN
        )

        if self._exposed_only:
            for entity_id in script.referenced_entities:
                if not async_should_expose(hass, CONVERSATION_DOMAIN, entity_id):
                    raise RuntimeError(
                        f"Referencing unknown or unexposed entity {entity_id}, please "
                        "rewrite the script"
                    )

        try:
            async with timeout(SCRIPT_TIMEOUT):
                result = await shield(create_task(script.async_run(context=context)))
        except TimeoutError:
            return {
                "success": True,
                "message": "The script is scheduled to execute in background",
            }

        if result.service_response:
            return {"service_response": result.service_response}

        return {"success": True}
