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
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.util import yaml

from .const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_INTENT_ENTITIES,
    CONF_MEMORY_PROMPTS,
    CONF_PROMPT_ENTITIES,
    CONF_SCRIPT_EXPOSED_ONLY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
    }
)

DDG_REGIONS = {
    "xa-ar": "Arabia",
    "xa-en": "Arabia (en)",
    "ar-es": "Argentina",
    "au-en": "Australia",
    "at-de": "Austria",
    "be-fr": "Belgium (fr)",
    "be-nl": "Belgium (nl)",
    "br-pt": "Brazil",
    "bg-bg": "Bulgaria",
    "ca-en": "Canada",
    "ca-fr": "Canada (fr)",
    "ct-ca": "Catalan",
    "cl-es": "Chile",
    "cn-zh": "China",
    "co-es": "Colombia",
    "hr-hr": "Croatia",
    "cz-cs": "Czech Republic",
    "dk-da": "Denmark",
    "ee-et": "Estonia",
    "fi-fi": "Finland",
    "fr-fr": "France",
    "de-de": "Germany",
    "gr-el": "Greece",
    "hk-tzh": "Hong Kong",
    "hu-hu": "Hungary",
    "in-en": "India",
    "id-id": "Indonesia",
    "id-en": "Indonesia (en)",
    "ie-en": "Ireland",
    "il-he": "Israel",
    "it-it": "Italy",
    "jp-jp": "Japan",
    "kr-kr": "Korea",
    "lv-lv": "Latvia",
    "lt-lt": "Lithuania",
    "xl-es": "Latin America",
    "my-ms": "Malaysia",
    "my-en": "Malaysia (en)",
    "mx-es": "Mexico",
    "nl-nl": "Netherlands",
    "nz-en": "New Zealand",
    "no-no": "Norway",
    "pe-es": "Peru",
    "ph-en": "Philippines",
    "ph-tl": "Philippines (tl)",
    "pl-pl": "Poland",
    "pt-pt": "Portugal",
    "ro-ro": "Romania",
    "ru-ru": "Russia",
    "sg-en": "Singapore",
    "sk-sk": "Slovak Republic",
    "sl-sl": "Slovenia",
    "za-en": "South Africa",
    "es-es": "Spain",
    "se-sv": "Sweden",
    "ch-de": "Switzerland (de)",
    "ch-fr": "Switzerland (fr)",
    "ch-it": "Switzerland (it)",
    "tw-tzh": "Taiwan",
    "th-th": "Thailand",
    "tr-tr": "Turkey",
    "ua-uk": "Ukraine",
    "uk-en": "United Kingdom",
    "us-en": "United States",
    "ue-es": "United States (es)",
    "ve-es": "Venezuela",
    "vn-vi": "Vietnam",
    "wt-wt": "No region",
}

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROMPT_ENTITIES, default=True): bool,
        vol.Required(CONF_INTENT_ENTITIES, default=True): bool,
        vol.Required(CONF_DUCKDUCKGO_REGION, default="wt-wt"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=value, label=label)
                    for value, label in DDG_REGIONS.items()
                ],
                translation_key=CONF_DUCKDUCKGO_REGION,
                multiple=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
        vol.Required(CONF_SCRIPT_EXPOSED_ONLY, default=True): bool,
        vol.Optional(CONF_MEMORY_PROMPTS): selector.TextSelector(
            selector.TextSelectorConfig(
                multiline=True,
                type=selector.TextSelectorType.TEXT,
            ),
        ),
    }
)


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

        schema = self.add_suggested_values_to_schema(
            DATA_SCHEMA, self.suggested_values_from_default(DATA_SCHEMA)
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options flow entry point."""
        errors = {}
        if user_input is not None:
            self.options = user_input
            if (prompts := user_input.get(CONF_MEMORY_PROMPTS)) is not None:
                self.options[CONF_MEMORY_PROMPTS] = yaml.parse_yaml(prompts)

            return self.async_create_entry(
                title=self.data[CONF_NAME], data=self.data, options=self.options
            )

        options = self.options.copy()
        if (prompts := options.get(CONF_MEMORY_PROMPTS)) is not None:
            options[CONF_MEMORY_PROMPTS] = yaml.dump(prompts)

        schema = self.add_suggested_values_to_schema(
            OPTIONS_SCHEMA,
            options,
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
        self.options: Mapping[str, Any] = self.suggested_values_from_default(
            OPTIONS_SCHEMA
        )

    def suggested_values_from_default(
        self, data_schema: vol.Schema | Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Generate suggested values from schema markers."""
        if isinstance(data_schema, vol.Schema):
            data_schema = data_schema.schema

        suggested_values = {}
        for key, value in data_schema.items():
            if isinstance(key, vol.Marker) and not isinstance(
                key.default, vol.Undefined
            ):
                suggested_values[str(key)] = key.default
            if isinstance(value, (vol.Schema, dict)):
                value = self.suggested_values_from_default(value)
                if value:
                    suggested_values[str(key)] = value
        return suggested_values

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return PowerLLMOptionsFlow(config_entry)
