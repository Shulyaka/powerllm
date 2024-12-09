"""Config flow for Power LLM custom integration."""

from __future__ import annotations

import logging
from collections.abc import Generator, Mapping
from functools import partial
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

from .const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_INTENT_ENTITIES,
    CONF_MEMORY_PROMPTS,
    CONF_PROMPT_ENTITIES,
    CONF_SCRIPT_EXPOSED_ONLY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

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


class PowerLLMBaseFlow:
    """Handle both config and option flow for Power LLM."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_validate_input(
        self, step_id: str, step_schema: vol.Schema, step_data: dict[str, Any]
    ) -> dict[str, str]:
        """Validate step data."""
        if step_id == "user":
            await self.async_set_unique_id(self.title())
            self._abort_if_unique_id_configured()
        return {}

    def title(self) -> str:
        """Return config flow title."""
        return self.data[CONF_NAME]

    async def get_data_schema(self) -> vol.Schema:
        """Get data schema."""
        return vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
            }
        )

    async def get_options_schema(self) -> vol.Schema:
        """Get data schema."""
        return vol.Schema(
            {
                vol.Required(CONF_PROMPT_ENTITIES, default=True): bool,
                vol.Required(CONF_INTENT_ENTITIES, default=True): bool,
                vol.Required(
                    CONF_DUCKDUCKGO_REGION, default="wt-wt"
                ): selector.SelectSelector(
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


class RecursiveDataFlow(PowerLLMBaseFlow):
    """Handle both config and option flow."""

    def __init__(self) -> None:
        """Initialize the flow."""
        self.config_step = None
        self.current_step_schema = None
        self.current_step_id = None
        self.current_step_data = None

    def config_step_generator(
        self,
    ) -> Generator[tuple[str, vol.Schema, dict], None, None]:
        """Return a generator of the next step config."""

        def traverse_config(
            name: str, schema: vol.Schema, data: dict
        ) -> tuple[str, vol.Schema, dict]:
            current_schema = {}
            recursive_schema = {}
            for var, val in schema.schema.items():
                if isinstance(val, vol.Schema):
                    recursive_schema[var] = val
                elif isinstance(val, dict):
                    recursive_schema[var] = vol.Schema(val)
                else:
                    current_schema[var] = val

            yield name, vol.Schema(current_schema), data
            for var, val in recursive_schema.items():
                yield traverse_config(str(var), val, data.setdefault(var, {}))

        if not isinstance(self, OptionsFlow):
            yield from traverse_config("user", self.data_schema, self.data)
        yield from traverse_config("init", self.options_schema, self.options)

    async def async_step(
        self, step_id: str, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the step."""
        if self.config_step is None:
            self.config_step = self.config_step_generator()
            (
                self.current_step_id,
                self.current_step_schema,
                self.current_step_data,
            ) = next(self.config_step)
        if self.current_step_id != step_id:
            raise RuntimeError("Unexpected step id")

        errors = {}
        if user_input is not None:
            for name, var in user_input.items():
                self.current_step_data[name] = var
            errors = await self.async_validate_input(
                step_id=step_id,
                step_schema=self.current_step_schema,
                step_data=self.current_step_data,
            )
            if not errors:
                try:
                    (
                        self.current_step_id,
                        self.current_step_schema,
                        self.current_step_data,
                    ) = next(self.config_step)
                    return await self.async_step(self.current_step_id)
                except StopIteration:
                    return self.async_create_entry(
                        title=self.title(), data=self.data, options=self.options
                    )

        schema = self.add_suggested_values_to_schema(
            self.current_step_schema, self.current_step_data
        )

        return self.async_show_form(
            step_id=self.current_step_id, data_schema=schema, errors=errors
        )

    def __getattr__(self, attr: str) -> Any:
        """Get step method."""
        if attr.startswith("async_step_"):
            return partial(self.async_step, attr[11:])
        if hasattr(super(), "__getattr__"):
            return super().__getattr__(attr)
        raise AttributeError


class PowerLLMOptionsFlow(RecursiveDataFlow, OptionsFlow):
    """Handle an options flow for Power LLM."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.data: Mapping[str, Any] = config_entry.data
        self.options: Mapping[str, Any] = config_entry.options.copy()
        self.data_schema: vol.Schema | None = None
        self.options_schema: vol.Schema | None = None
        super().__init__()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options flow entry point."""
        if self.data_schema is None:
            self.data_schema = await self.get_data_schema()
            self.options_schema = await self.get_options_schema()
        return await self.async_step("init", user_input)

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


class PowerLLMConfigFlow(RecursiveDataFlow, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Power LLM."""

    def __init__(self) -> None:
        """Initialize config flow."""
        self.data_schema: vol.Schema | None = None
        self.options_schema: vol.Schema | None = None
        super().__init__()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Config flow entry point."""
        if self.data_schema is None:
            self.data_schema = await self.get_data_schema()
            self.options_schema = await self.get_options_schema()
            self.data: Mapping[str, Any] = self.suggested_values_from_default(
                self.data_schema
            )
            self.options: Mapping[str, Any] = self.suggested_values_from_default(
                self.options_schema
            )
        return await self.async_step("user", user_input)

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
                suggested_values[str(key)] = key.default()
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
