"""Config flow for Power LLM custom integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import CONF_PROMPT_ENTITIES, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROMPT_ENTITIES, default=True): bool,
    }
)

DEFAULT_OPTIONS = {
    CONF_PROMPT_ENTITIES: True,
}


class PowerLLMBaseFlow:
    """Handle both config and option flow for Power LLM."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Config flow entry point."""
        errors = {}
        if user_input is not None:
            self.data = user_input
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()
            return await self.async_step_init()  # data is done, advance to options

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options flow entry point."""
        errors = {}
        if user_input is not None:
            self.options = user_input
            return self.async_create_entry(
                title=self.data[CONF_NAME], data=self.data, options=self.options
            )

        schema = self.add_suggested_values_to_schema(
            OPTIONS_SCHEMA,
            self.options,
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


class PowerLLMOptionsFlow(PowerLLMBaseFlow, OptionsFlow):
    """Handle an options flow for Power LLM."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.data: Mapping[str, Any] = config_entry.data
        self.options: Mapping[str, Any] = config_entry.options

    @callback
    def async_create_entry(
        self,
        *,
        data: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
        **kwargs,
    ) -> ConfigFlowResult:
        """Return result entry for option flow."""
        return super().async_create_entry(data=options, **kwargs)


class PowerLLMConfigFlow(PowerLLMBaseFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Power LLM."""

    def __init__(self) -> None:
        """Initialize config flow."""
        self.data: Mapping[str, Any] = {}
        self.options: Mapping[str, Any] = DEFAULT_OPTIONS

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return PowerLLMOptionsFlow(config_entry)
