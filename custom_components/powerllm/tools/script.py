"""Dynamic script execution tool."""

import asyncio
import logging

import probatio as vol
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolAnnotations, ToolInput, ToolResult
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.util.yaml import dump, parse_yaml

from ..const import DOMAIN
from ..llm_tools import PowerLLMTool

_LOGGER = logging.getLogger(__name__)

SCRIPT_TIMEOUT = 3


class DynamicScriptTool(PowerLLMTool):
    """Tool to execute LLM-written scripts."""

    name = "homeassistant_script"
    title = "Run a Home Assistant script"
    annotations = ToolAnnotations(
        read_only=False, destructive=True, idempotent=False, open_world=True
    )
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

    @callback
    def prompt(self, hass: HomeAssistant, llm_context: LLMContext) -> str | None:
        """Map exposed entity IDs to names for generated scripts."""
        entities = {
            state.entity_id: state.name
            for state in sorted(
                hass.states.async_all(), key=lambda state: state.entity_id
            )
            if async_should_expose(hass, llm_context.assistant, state.entity_id)
        }
        if not entities:
            return None
        return "Entity IDs for scripts (entity_id: name):\n" + dump(entities)

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        """Execute a script in Home Assistant."""
        args = self.parameters(tool_input.tool_args)
        context = llm_context.context
        script = args["script"]

        try:
            if isinstance(script, str):
                script = parse_yaml(script)
            else:
                parsed_actions = [parse_yaml(action) for action in script]
                script = [
                    item
                    for action in parsed_actions
                    for item in (action if isinstance(action, list) else [action])
                ]
        except HomeAssistantError as err:
            raise ServiceValidationError(f"Invalid script YAML: {err}") from err

        if not isinstance(script, (dict, list)):
            raise ServiceValidationError(
                "Script must be an action or a list of actions"
            )
        if isinstance(script, dict):
            if "trigger" in script or "triggers" in script:
                raise ServiceValidationError(
                    "This is a script, not an automation. "
                    "Please rewrite without triggers."
                )
            if "sequence" in script:
                action = cv.determine_script_action(script)
                if action != cv.SCRIPT_ACTION_SEQUENCE:
                    raise ServiceValidationError(
                        f'The "{action}" action should be inside the "sequence" list, '
                        "please rewrite the script"
                    )
                if set(script) == {"sequence"}:
                    script = script["sequence"]

        try:
            sequence = cv.SCRIPT_SCHEMA(script)
            sequence = await async_validate_actions_config(hass, sequence)
        except vol.Invalid as err:
            raise ServiceValidationError(f"Invalid script: {err}") from err

        _LOGGER.debug("Parsed sequence: %s", sequence)

        script = Script(
            hass, sequence=sequence, name="convesation_scipt", domain=DOMAIN
        )

        if self._exposed_only:
            for entity_id in script.referenced_entities:
                if not async_should_expose(hass, llm_context.assistant, entity_id):
                    raise ServiceValidationError(
                        f"Referencing unknown or unexposed entity {entity_id}, please "
                        "rewrite the script"
                    )

        try:
            async with asyncio.timeout(SCRIPT_TIMEOUT):
                result = await asyncio.shield(
                    asyncio.create_task(script.async_run(context=context))
                )
        except TimeoutError:
            return ToolResult(
                data={
                    "success": True,
                    "message": "The script is scheduled to execute in background",
                }
            )

        if result is not None and result.service_response:
            return ToolResult(data={"service_response": result.service_response})

        return ToolResult(data={"success": True})
