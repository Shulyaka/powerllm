"""Duckduckgo search tools."""

import logging

import voluptuous as vol
from duckduckgo_search import AsyncDDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput
from homeassistant.util.json import JsonObjectType

from ..llm_tools import PowerLLMTool

_LOGGER = logging.getLogger(__name__)


class DDGBaseTool(PowerLLMTool):
    """DuckDuckGo base tool class."""

    def __init__(self, region: str = "wt-wt"):
        """Initialize the tool."""
        self._ddg = AsyncDDGS()
        self._region = region


class DDGTextSearchTool(DDGBaseTool):
    """DuckDuckGo text search tool."""

    name = "websearch"
    description = "Search the internet. Use this tool to access up-to-date data"
    parameters = vol.Schema(
        {
            vol.Required("query"): cv.string,
            vol.Optional(
                "max_results", default=5, description="Number of results requested"
            ): vol.Coerce(int),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Execute text search."""
        try:
            return await self._ddg.atext(
                tool_input.args["query"],
                region=self._region,
                max_results=tool_input.args["max_results"],
            ) or {"error": "No results returned"}
        except DuckDuckGoSearchException as e:
            raise HomeAssistantError(str(e)) from e
