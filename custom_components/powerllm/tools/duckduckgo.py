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
                tool_input.tool_args["query"],
                region=self._region,
                max_results=tool_input.tool_args["max_results"],
            ) or {"error": "No results returned"}
        except DuckDuckGoSearchException as e:
            raise HomeAssistantError(str(e)) from e


class DDGNewsTool(DDGBaseTool):
    """DuckDuckGo news tool."""

    name = "news"
    description = "Get the latest news from the internet"
    parameters = vol.Schema(
        {
            vol.Required("keywords", description="keywords for query"): cv.string,
            vol.Optional(
                "max_results", default=5, description="Number of results requested"
            ): vol.Coerce(int),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Execute news search."""
        try:
            return await self._ddg.anews(
                tool_input.tool_args["keywords"],
                region=self._region,
                max_results=tool_input.tool_args["max_results"],
            ) or {"error": "No results returned"}
        except DuckDuckGoSearchException as e:
            raise HomeAssistantError(str(e)) from e


class DDGMapsSearchTool(DDGBaseTool):
    """DuckDuckGo maps search tool."""

    name = "maps_search"
    description = "Search for places on the map"
    parameters = vol.Schema(
        {
            vol.Required("keywords", description="keywords for the search"): cv.string,
            vol.Optional(
                "place", description="if set, the other parameters are not used"
            ): cv.string,
            vol.Optional("street", description="house number/street"): cv.string,
            vol.Optional("city", description="city of search"): cv.string,
            vol.Optional("county", description="county of search"): cv.string,
            vol.Optional("state", description="state of search"): cv.string,
            vol.Optional("country", description="country of search"): cv.string,
            vol.Optional("postalcode", description="postalcode of search"): cv.string,
            vol.Optional(
                "latitude", description="geographic coordinate (north-south position)"
            ): cv.string,
            vol.Optional(
                "longitude",
                description="geographic coordinate (east-west position); if latitude "
                "and longitude are set, the other parameters are not used",
            ): cv.string,
            vol.Optional(
                "radius",
                description="expand the search square by the distance in kilometers",
            ): vol.Coerce(int),
            vol.Optional(
                "max_results", default=5, description="Number of results requested"
            ): vol.Coerce(int),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Execute news search."""
        kwargs = tool_input.tool_args.copy()
        if all(
            kwargs.get(x) is None
            for x in [
                "place",
                "street",
                "city",
                "county",
                "state",
                "country",
                "postalcode",
                "latitude",
                "longitude",
            ]
        ):
            kwargs["latitude"] = str(hass.config.latitude)
            kwargs["longitude"] = str(hass.config.longitude)

        try:
            return await self._ddg.amaps(**kwargs) or {"error": "No results returned"}
        except DuckDuckGoSearchException as e:
            raise HomeAssistantError(str(e)) from e
