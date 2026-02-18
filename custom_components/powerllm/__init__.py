"""Power LLM."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.helpers.typing import ConfigType

from .api import PowerLLMAPI
from .const import CONF_MEMORY_PROMPTS, DOMAIN
from .http import LLMToolsApiView, LLMToolsListView, LLMToolView
from .llm_tools import (  # noqa: F401
    PowerLLMTool as PowerLLMTool,
    async_register_tool as async_register_tool,
    deferred_register_tools,
    llm_tool as llm_tool,
)
from .tools.web_scrape import setup as setup_web_scrape_tool

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
    setup_web_scrape_tool(hass)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate entry."""
    _LOGGER.debug("Migrating from version %s:%s", entry.version, entry.minor_version)

    if entry.version > 1:
        # This means the user has downgraded from a future version
        return False

    if entry.version == 1 and entry.minor_version == 1:
        # Move memory prompts to separate sections
        new_options = {**entry.options}
        memory_prompts = new_options.pop(CONF_MEMORY_PROMPTS, {})
        new_options[CONF_MEMORY_PROMPTS] = {
            (await hass.auth.async_get_user(user_id)).name: {user_id: prompt}
            for user_id, prompt in memory_prompts.items()
        }
        hass.config_entries.async_update_entry(
            entry, options=new_options, minor_version=2
        )

    _LOGGER.debug(
        "Migration to version %s:%s successful", entry.version, entry.minor_version
    )

    return True
