"""Duckduckgo search tools."""

import logging

import probatio as vol
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import LLMContext, ToolInput, ToolResult
from primp import PrimpError

from ..llm_tools import PowerLLMTool

_LOGGER = logging.getLogger(__name__)


class DDGBaseTool(PowerLLMTool):
    """DuckDuckGo base tool class."""

    def __init__(self, region: str = "wt-wt"):
        """Initialize the tool."""
        self._region = region

    def __deepcopy__(self, memo):
        """Implement deepcopy support for conversaton trace as_dict."""
        return type(self)(self._region)


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
    ) -> ToolResult:
        """Execute text search."""
        args = self.parameters(tool_input.tool_args)
        try:
            results = await hass.async_add_executor_job(
                lambda: DDGS().text(
                    args["query"],
                    region=self._region,
                    max_results=args["max_results"],
                    backend="duckduckgo",
                ),
            )
        except (DDGSException, PrimpError) as e:
            raise HomeAssistantError(str(e)) from e
        return ToolResult(data={"results": results or []})


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
    ) -> ToolResult:
        """Execute news search."""
        args = self.parameters(tool_input.tool_args)
        try:
            results = await hass.async_add_executor_job(
                lambda: DDGS().news(
                    args["keywords"],
                    region=self._region,
                    max_results=args["max_results"],
                    backend="duckduckgo",
                ),
            )
        except (DDGSException, PrimpError) as e:
            raise HomeAssistantError(str(e)) from e
        return ToolResult(data={"results": results or []})
