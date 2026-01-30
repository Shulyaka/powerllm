"""Power LLM Tools."""

from __future__ import annotations

import logging
from functools import cache, partial

import slugify as unicode_slug
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.cover.intent import INTENT_CLOSE_COVER, INTENT_OPEN_COVER
from homeassistant.components.intent import async_device_supports_timers
from homeassistant.components.lock import DOMAIN as LOCK_DOMAIN
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.components.weather import INTENT_GET_WEATHER
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEFAULT, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    floor_registry as fr,
    intent,
    llm,
)
from homeassistant.util import yaml

from .const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_INTENT_ENTITIES,
    CONF_PROMPT_ENTITIES,
    CONF_SCRIPT_EXPOSED_ONLY,
    CONF_TOOL_SELECTION,
    DOMAIN,
)
from .llm_tools import (
    PowerCalendarGetEventsTool,
    PowerGetDateTimeTool,
    PowerGetLiveContextTool,
    PowerIntentTool,
    PowerLLMTool,
    PowerScriptTool,
    PowerTodoGetItemsTool,
)
from .tools.duckduckgo import DDGNewsTool, DDGTextSearchTool
from .tools.memory import MemoryTool
from .tools.script import DynamicScriptTool

_LOGGER = logging.getLogger(__name__)


class PowerLLMAPI(llm.API):
    """API exposing PowerLLM tools to LLMs."""

    IGNORE_INTENTS = {
        INTENT_GET_WEATHER,
        INTENT_OPEN_COVER,  # deprecated
        INTENT_CLOSE_COVER,  # deprecated
        intent.INTENT_NEVERMIND,
        intent.INTENT_TOGGLE,
        intent.INTENT_GET_CURRENT_DATE,
        intent.INTENT_GET_CURRENT_TIME,
        intent.INTENT_GET_TEMPERATURE,
        intent.INTENT_RESPOND,
    }

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Init the class."""
        super().__init__(
            hass=hass,
            id=unicode_slug.slugify(config_entry.data[CONF_NAME], separator="_"),
            name=config_entry.data[CONF_NAME],
        )
        self.cached_slugify = cache(
            partial(unicode_slug.slugify, separator="_", lowercase=False)
        )
        self.config_entry = config_entry

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the instance of the API."""
        if llm_context.assistant:
            exposed_entities: dict | None = llm._get_exposed_entities(
                self.hass, llm_context.assistant, include_state=False
            )
        else:
            exposed_entities = None

        tools = self._async_get_tools(llm_context, exposed_entities)
        api_prompt = self._async_get_api_prompt(llm_context, exposed_entities, tools)

        return llm.APIInstance(
            api=self,
            api_prompt=api_prompt,
            llm_context=llm_context,
            tools=tools,
            custom_serializer=llm.selector_serializer,
        )

    @callback
    def _async_get_api_prompt(
        self,
        llm_context: llm.LLMContext,
        exposed_entities: dict | None,
        tools: list[PowerLLMTool],
    ) -> str:
        """Return the prompt for the API."""
        if not exposed_entities or not exposed_entities["entities"]:
            return llm.NO_ENTITIES_PROMPT
        return "\n".join(
            [
                *self._async_get_preable(llm_context),
                *self._async_get_exposed_entities_prompt(llm_context, exposed_entities),
                *self._async_get_tools_prompt(llm_context, tools),
            ]
        )

    @callback
    def _async_get_preable(self, llm_context: llm.LLMContext) -> list[str]:
        """Return the prompt for the API."""

        prompt = [
            (
                "When controlling Home Assistant always call the intent tools. "
                "When controlling a device, prefer passing just name and domain. "
                "When controlling an area, prefer passing just area name and domain."
            )
        ]
        area: ar.AreaEntry | None = None
        floor: fr.FloorEntry | None = None
        if llm_context.device_id:
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(llm_context.device_id)

            if device:
                area_reg = ar.async_get(self.hass)
                if device.area_id and (area := area_reg.async_get_area(device.area_id)):
                    floor_reg = fr.async_get(self.hass)
                    if area.floor_id:
                        floor = floor_reg.async_get_floor(area.floor_id)

            extra = (
                "and all generic commands like 'turn on the lights' "
                "should target this area."
            )

        if floor and area:
            prompt.append(f"You are in area {area.name} (floor {floor.name}) {extra}")
        elif area:
            prompt.append(f"You are in area {area.name} {extra}")
        else:
            prompt.append(
                "When a user asks to turn on all devices of a specific type, "
                "ask user to specify an area, unless there is only one device "
                "of that type."
            )

        if not llm_context.device_id or not async_device_supports_timers(
            self.hass, llm_context.device_id
        ):
            prompt.append("This device is not able to start timers.")

        if self.config_entry.options[CONF_PROMPT_ENTITIES]:
            prompt.append(llm.DYNAMIC_CONTEXT_PROMPT)

        return prompt

    @callback
    def _async_get_exposed_entities_prompt(
        self, llm_context: llm.LLMContext, exposed_entities: dict | None
    ) -> list[str]:
        """Return the prompt for the API for exposed entities."""
        prompt = []

        if (
            self.config_entry.options[CONF_PROMPT_ENTITIES]
            and exposed_entities
            and exposed_entities["entities"]
        ):
            if any(
                entity.get("domain") == LOCK_DOMAIN
                for entity in exposed_entities["entities"].values()
            ):
                prompt.append(
                    "Use HassTurnOn to lock and HassTurnOff to unlock a lock."
                )

            prompt.append(
                "Static Context: An overview of the areas and the devices in this "
                "smart home:"
            )
            prompt.append(yaml.dump(exposed_entities["entities"]))

        return prompt

    @callback
    def _async_get_tools_prompt(
        self, llm_context: llm.LLMContext, tools: list[PowerLLMTool]
    ) -> list[str]:
        """Return the prompt for the API for available tools."""
        prompt = []

        for tool in tools:
            if (tool_prompt := tool.prompt(self.hass, llm_context)) is not None:
                prompt.append(tool_prompt)

        return prompt

    @callback
    def _async_get_tools(
        self, llm_context: llm.LLMContext, exposed_entities: dict | None
    ) -> list[PowerLLMTool]:
        """Return a list of LLM tools."""
        ignore_intents = self.IGNORE_INTENTS
        if not llm_context.device_id or not async_device_supports_timers(
            self.hass, llm_context.device_id
        ):
            ignore_intents = ignore_intents | {
                intent.INTENT_START_TIMER,
                intent.INTENT_CANCEL_TIMER,
                intent.INTENT_INCREASE_TIMER,
                intent.INTENT_DECREASE_TIMER,
                intent.INTENT_PAUSE_TIMER,
                intent.INTENT_UNPAUSE_TIMER,
                intent.INTENT_TIMER_STATUS,
            }

        if not self.config_entry.options[CONF_INTENT_ENTITIES]:
            ignore_intents = ignore_intents | {intent.INTENT_GET_STATE}

        intent_handlers = [
            intent_handler
            for intent_handler in intent.async_get(self.hass)
            if intent_handler.intent_type not in ignore_intents
        ]

        exposed_domains: set[str] | None = None
        if exposed_entities is not None:
            exposed_domains = {
                info["domain"] for info in exposed_entities["entities"].values()
            }

            intent_handlers = [
                intent_handler
                for intent_handler in intent_handlers
                if intent_handler.platforms is None
                or intent_handler.platforms & exposed_domains
            ]

        tools: list[PowerLLMTool] = [
            PowerIntentTool(
                self.cached_slugify(intent_handler.intent_type),
                intent_handler,
                self.config_entry.options[CONF_INTENT_ENTITIES],
            )
            for intent_handler in intent_handlers
        ]

        tools.append(PowerGetDateTimeTool())

        if exposed_entities:
            if exposed_entities[CALENDAR_DOMAIN]:
                names = []
                for info in exposed_entities[CALENDAR_DOMAIN].values():
                    names.extend(info["names"].split(", "))
                tools.append(PowerCalendarGetEventsTool(names))

            if exposed_domains is not None and TODO_DOMAIN in exposed_domains:
                names = []
                for info in exposed_entities["entities"].values():
                    if info["domain"] != TODO_DOMAIN:
                        continue
                    names.extend(info["names"].split(", "))
                tools.append(PowerTodoGetItemsTool(names))

            tools.extend(
                PowerScriptTool(self.hass, script_entity_id)
                for script_entity_id in exposed_entities[SCRIPT_DOMAIN]
            )

        if exposed_domains:
            tools.append(PowerGetLiveContextTool())

        tools.append(
            DynamicScriptTool(self.config_entry.options[CONF_SCRIPT_EXPOSED_ONLY])
        )

        tools.append(
            DDGTextSearchTool(self.config_entry.options[CONF_DUCKDUCKGO_REGION])
        )
        tools.append(DDGNewsTool(self.config_entry.options[CONF_DUCKDUCKGO_REGION]))
        tools.append(MemoryTool(self.config_entry))

        tools.extend(self.hass.data.get(DOMAIN, {}).values())

        tool_selection = self.config_entry.options.get(CONF_TOOL_SELECTION, {})
        tool_selection_default = tool_selection.get(CONF_DEFAULT, True)
        return [
            tool
            for tool in tools
            if tool.async_is_applicable(self.hass, llm_context)
            and tool_selection.get(tool.name, tool_selection_default)
        ]
