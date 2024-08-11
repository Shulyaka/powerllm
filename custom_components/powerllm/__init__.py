"""Power LLM."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .http import LLMToolsApiView, LLMToolsListView, LLMToolView

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


class PowerLLMTool(llm.Tool):
    """Base class for Power LLM Tools."""

    @callback
    def prompt(self, hass: HomeAssistant, llm_context: llm.LLMContext) -> str | None:
        """Additional system prompt for this tool."""

    @callback
    def async_is_applicable(
        self, hass: HomeAssistant, llm_context: llm.LLMContext
    ) -> bool:
        """Check the tool applicability."""
        return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""

    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the LLM Tools API with the HTTP interface."""
    hass.http.register_view(LLMToolsApiView)
    hass.http.register_view(LLMToolsListView)
    hass.http.register_view(LLMToolView)

    return True
