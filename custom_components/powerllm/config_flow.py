"""Config flow for Power LLM custom integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEFAULT, CONF_NAME
from homeassistant.core import Context
from homeassistant.helpers import config_validation as cv, llm, selector

from .api import PowerLLMAPI
from .const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_INTENT_ENTITIES,
    CONF_MEMORY_PROMPTS,
    CONF_PROMPT_ENTITIES,
    CONF_SCRIPT_EXPOSED_ONLY,
    CONF_TOOL_SELECTION,
    DOMAIN,
)
from .recursive_data_flow import RecursiveConfigFlow

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


class PowerLLMFlow(RecursiveConfigFlow, domain=DOMAIN):
    """Handle config and options flow for Power LLM."""

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
        """Get options schema."""
        tmp_entry = ConfigEntry(
            discovery_keys={},
            domain=DOMAIN,
            minor_version=0,
            source="",
            title="Temp",
            unique_id=None,
            version=0,
            subentries_data=None,
            data={CONF_NAME: "Temp"},
            options={
                CONF_PROMPT_ENTITIES: False,
                CONF_INTENT_ENTITIES: True,
                CONF_DUCKDUCKGO_REGION: "wt-wt",
                CONF_SCRIPT_EXPOSED_ONLY: False,
            },
        )
        tmp_context = llm.LLMContext(
            platform=DOMAIN,
            context=Context(user_id="Temp"),
            user_prompt=None,
            language=None,
            assistant=None,
            device_id=None,
        )
        tmp_api = await PowerLLMAPI(self.hass, tmp_entry).async_get_api_instance(
            tmp_context
        )
        tools = [tool.name for tool in tmp_api.tools]
        tools.append(CONF_DEFAULT)

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
                vol.Optional(CONF_MEMORY_PROMPTS): vol.Schema(
                    {
                        vol.Optional(user.id): selector.TextSelector(
                            selector.TextSelectorConfig(
                                multiline=True,
                                type=selector.TextSelectorType.TEXT,
                            ),
                        )
                        for user in await self.hass.auth.async_get_users()
                        if not user.system_generated
                    }
                ),
                vol.Optional(CONF_TOOL_SELECTION): vol.Schema(
                    {vol.Required(tool, default=True): bool for tool in tools}
                ),
            }
        )
