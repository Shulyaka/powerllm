"""Permanent memory tool."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from ..const import CONF_MEMORY_PROMPTS
from ..llm_tools import PowerLLMTool

_LOGGER = logging.getLogger(__name__)


class MemoryTool(PowerLLMTool):
    """Tool that allows LLM to remember facts about the user."""

    name = "memory"
    description = (
        "Use this tool to remember personal facts about the user that would allow a "
        "more personalized assistance. Call it every time the user tells you anything "
        "about themselves that could still be relevant for future interactions, even "
        "when not explicitly asked to do so. Also include implicitly inferresd traits "
        "of the user even when the user does not consciously states them"
    )
    parameters = vol.Schema(
        {
            vol.Required(
                "text",
                description="the text to remember, will be included into the system "
                "prompt",
            ): cv.string,
        }
    )

    def __init__(self, config_entry):
        """Initialize the tool."""
        self._config_entry = config_entry

    @callback
    def async_is_applicable(self, hass: HomeAssistant, llm_context: LLMContext) -> bool:
        """Check the tool applicability."""
        return (
            llm_context.context is not None and llm_context.context.user_id is not None
        )

    @callback
    def prompt(self, hass: HomeAssistant, llm_context: LLMContext) -> str | None:
        """Additional system prompt for this tool."""
        memory_prompts_by_id = {
            user_id: prompt
            for user_name, prompts in self._config_entry.options.get(
                CONF_MEMORY_PROMPTS, {}
            ).items()
            for user_id, prompt in prompts.items()
        }
        return f"<memory tool remembered user facts>\n{
            memory_prompts_by_id.get(llm_context.context.user_id)
        }\n</memory tool remembered user facts>"

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Save a memory item."""

        if llm_context.context.user_id is None:
            raise HomeAssistantError("Empty user id")

        options = self._config_entry.options.copy()
        options[CONF_MEMORY_PROMPTS] = options.get(CONF_MEMORY_PROMPTS, {}).copy()
        user_name = None
        for name, prompts in options[CONF_MEMORY_PROMPTS].items():
            if llm_context.context.user_id in prompts:
                user_name = name
                options[CONF_MEMORY_PROMPTS][name] = prompts.copy()
                break

        if user_name is None:
            user_name = (
                await hass.auth.async_get_user(llm_context.context.user_id)
            ).name or llm_context.context.user_id

        if (
            prompt := options[CONF_MEMORY_PROMPTS]
            .setdefault(user_name, {})
            .get(llm_context.context.user_id)
        ):
            prompt += "\n"
        else:
            prompt = ""
        options[CONF_MEMORY_PROMPTS][user_name][llm_context.context.user_id] = (
            prompt + tool_input.tool_args["text"]
        )
        hass.config_entries.async_update_entry(self._config_entry, options=options)

        return {"success": True}
