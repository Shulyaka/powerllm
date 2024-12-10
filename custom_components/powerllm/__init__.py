"""Power LLM."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.helpers.typing import ConfigType

from .api import PowerLLMAPI
from .const import DOMAIN
from .http import LLMToolsApiView, LLMToolsListView, LLMToolView
from .llm_tools import (  # noqa: F401
    PowerLLMTool as PowerLLMTool,
    async_register_tool as async_register_tool,
    deferred_register_tools,
    llm_tool as llm_tool,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    api = PowerLLMAPI(hass, entry)
    llm.async_register_api(hass, api)
    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the LLM Tools API with the HTTP interface."""
    hass.http.register_view(LLMToolsApiView)
    hass.http.register_view(LLMToolsListView)
    hass.http.register_view(LLMToolView)
    deferred_register_tools(hass)

    return True
