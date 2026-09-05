"""Power LLM API for tools that complement Assist."""

from __future__ import annotations

import slugify as unicode_slug
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEFAULT, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm

from .const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_SCRIPT_EXPOSED_ONLY,
    CONF_TOOL_SELECTION,
    DOMAIN,
)
from .llm_tools import PowerLLMTool
from .tools.duckduckgo import DDGNewsTool, DDGTextSearchTool
from .tools.get_state import GetStateTool
from .tools.memory import MemoryTool
from .tools.script import DynamicScriptTool


class PowerLLMAPI(llm.API):
    """API exposing PowerLLM tools to LLMs."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the API."""
        super().__init__(
            hass=hass,
            id=unicode_slug.slugify(config_entry.data[CONF_NAME], separator="_"),
            name=config_entry.data[CONF_NAME],
        )
        self.config_entry = config_entry

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the tools and prompts applicable to this request."""
        tools = self._async_get_tools(llm_context)
        prompts = [
            prompt
            for tool in tools
            if (prompt := tool.prompt(self.hass, llm_context)) is not None
        ]
        return llm.APIInstance(
            api=self,
            api_prompt="\n".join(prompts),
            llm_context=llm_context,
            tools=tools,
            custom_serializer=llm.selector_serializer,
        )

    @callback
    def _async_get_tools(self, llm_context: llm.LLMContext) -> list[PowerLLMTool]:
        """Return enabled tools applicable to the request."""
        tools: list[PowerLLMTool] = [
            GetStateTool(),
            DynamicScriptTool(self.config_entry.options[CONF_SCRIPT_EXPOSED_ONLY]),
            DDGTextSearchTool(self.config_entry.options[CONF_DUCKDUCKGO_REGION]),
            DDGNewsTool(self.config_entry.options[CONF_DUCKDUCKGO_REGION]),
            MemoryTool(self.config_entry),
            *self.hass.data.get(DOMAIN, {}).values(),
        ]
        tool_selection = self.config_entry.options.get(CONF_TOOL_SELECTION, {})
        tool_selection_default = tool_selection.get(CONF_DEFAULT, True)
        return [
            tool
            for tool in tools
            if tool.async_is_applicable(self.hass, llm_context)
            and tool_selection.get(tool.name, tool_selection_default)
        ]
