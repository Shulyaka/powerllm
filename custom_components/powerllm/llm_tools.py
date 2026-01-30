"""Power LLM Tools."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from types import NoneType, UnionType
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

import voluptuous as vol
from homeassistant.core import HomeAssistant, State, callback, is_callback
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    intent,
    llm,
    template,
)
from homeassistant.helpers.template.helpers import resolve_area_id
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType, JsonValueType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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


EXPORTED_ATTRIBUTES = [
    "device_class",
    "message",
    "all_day",
    "start_time",
    "end_time",
    "location",
    "description",
    "hvac_modes",
    "min_temp",
    "max_temp",
    "fan_modes",
    "preset_modes",
    "swing_modes",
    "current_temperature",
    "temperature",
    "target_temp_high",
    "target_temp_low",
    "fan_mode",
    "preset_mode",
    "swing_mode",
    "hvac_action",
    "aux_heat",
    "current_position",
    "current_tilt_position",
    "latitude",
    "longitude",
    "percentage",
    "direction",
    "oscillating",
    "available_modes",
    "max_humidity",
    "min_humidity",
    "action",
    "current_humidity",
    "humidity",
    "mode",
    "faces",
    "total_faces",
    "min",
    "max",
    "step",
    "min_color_temp_kelvin",
    "max_color_temp_kelvin",
    "min_mireds",
    "max_mireds",
    "effect_list",
    "supported_color_modes",
    "color_mode",
    "brightness",
    "color_temp_kelvin",
    "color_temp",
    "hs_color",
    "rgb_color",
    "xy_color",
    "rgbw_color",
    "rgbww_color",
    "effect",
    "sound_mode_list",
    "volume_level",
    "is_volume_muted",
    "media_content_type",
    "media_duration",
    "media_position",
    "media_title",
    "media_artist",
    "media_album_name",
    "media_track",
    "media_series_title",
    "media_season",
    "media_episode",
    "app_name",
    "sound_mode",
    "shuffle",
    "repeat",
    "source",
    "options",
    "battery_level",
    "available_tones",
    "elevation",
    "rising",
    "fan_speed_list",
    "fan_speed",
    "status",
    "cleaned_area",
    "operation_list",
    "operation_mode",
    "away_mode",
    "temperature_unit",
    "pressure",
    "pressure_unit",
    "wind_speed",
    "wind_speed_unit",
    "dew_point",
    "cloud_coverage",
    "persons",
]


def _area_name(hass: HomeAssistant, lookup_value: str) -> str | None:
    """Get the area name from an area id, device id, or entity id."""
    area_reg = ar.async_get(hass)
    if area := area_reg.async_get_area(lookup_value):
        return area.name

    def _get_area_name(area_reg: ar.AreaRegistry, valid_area_id: str) -> str:
        """Get area name from valid area ID."""
        area = area_reg.async_get_area(valid_area_id)
        assert area
        return area.name

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    try:
        cv.entity_id(lookup_value)
    except vol.Invalid:
        pass
    else:
        if entity := ent_reg.async_get(lookup_value):
            # If entity has an area ID, get the area name for that
            if entity.area_id:
                return _get_area_name(area_reg, entity.area_id)
            # If entity has a device ID and the device exists with an area ID, get the
            # area name for that
            if (
                entity.device_id
                and (device := dev_reg.async_get(entity.device_id))
                and device.area_id
            ):
                return _get_area_name(area_reg, device.area_id)

    if (device := dev_reg.async_get(lookup_value)) and device.area_id:
        return _get_area_name(area_reg, device.area_id)

    return None


def _floor_name(hass: HomeAssistant, lookup_value: str) -> str | None:
    """Get the floor name from a floor id."""
    floor_registry = fr.async_get(hass)

    # Check if it's a floor ID
    if floor := floor_registry.async_get_floor(lookup_value):
        return floor.name

    # Resolve to area ID and get floor name from area's floor
    if aid := resolve_area_id(hass, lookup_value):
        area_reg = ar.async_get(hass)
        if (
            (area := area_reg.async_get_area(aid))
            and area.floor_id
            and (floor := floor_registry.async_get_floor(area.floor_id))
        ):
            return floor.name

    return None


def _format_state(hass: HomeAssistant, entity_state: State) -> dict[str, Any]:
    """Format state for better understanding by a LLM."""
    entity_registry = er.async_get(hass)
    entity_state = template.TemplateState(hass, entity_state, collect=False)

    result: dict[str, Any] = {
        "name": entity_state.name,
        "entity_id": entity_state.entity_id,
        "state": entity_state.state_with_unit,
        "last_changed": dt_util.get_age(entity_state.last_changed) + " ago",
    }

    if registry_entry := entity_registry.async_get(entity_state.entity_id):
        if area_name := _area_name(hass, entity_state.entity_id):
            result["area"] = area_name
        if floor_name := _floor_name(hass, entity_state.entity_id):
            result["floor"] = floor_name
        if len(registry_entry.aliases):
            result["aliases"] = list(registry_entry.aliases)

    attributes: dict[str, Any] = {
        attribute: value
        for attribute, value in entity_state.attributes.items()
        if attribute in EXPORTED_ATTRIBUTES
    }
    if attributes:
        result["attributes"] = attributes

    return result


ADDITIONAL_DESCRIPTIONS = {
    intent.INTENT_GET_STATE: ". Use it to get a list of devices matching certain "
    "criteria or get additional details and attributes on them. ",
}


class PowerIntentTool(PowerLLMTool):
    """Power LLM Tool representing an Intent."""

    def __init__(
        self,
        name: str,
        intent_handler: intent.IntentHandler,
        response_entities: bool = False,
    ) -> None:
        """Init the class."""
        self.name = name
        self.intent_handler = intent_handler
        self._response_entities = response_entities
        self.description = (
            intent_handler.description or f"Execute Home Assistant {self.name} intent"
        )
        if name in ADDITIONAL_DESCRIPTIONS:
            self.description += ADDITIONAL_DESCRIPTIONS[name]
        self.extra_slots = None
        if not (slot_schema := intent_handler.slot_schema):
            return

        slot_schema = {**slot_schema}
        extra_slots = set()

        for field in ("preferred_area_id", "preferred_floor_id"):
            if field in slot_schema:
                extra_slots.add(field)
                del slot_schema[field]

        self.parameters = vol.Schema(slot_schema)
        if extra_slots:
            self.extra_slots = extra_slots

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Handle the intent."""
        slots = {key: {"value": val} for key, val in tool_input.tool_args.items()}

        if self.extra_slots and llm_context.device_id:
            device_reg = dr.async_get(hass)
            device = device_reg.async_get(llm_context.device_id)

            area: ar.AreaEntry | None = None
            floor: fr.FloorEntry | None = None
            if device:
                area_reg = ar.async_get(hass)
                if device.area_id and (area := area_reg.async_get_area(device.area_id)):
                    if area.floor_id:
                        floor_reg = fr.async_get(hass)
                        floor = floor_reg.async_get_floor(area.floor_id)

            for slot_name, slot_value in (
                ("preferred_area_id", area.id if area else None),
                ("preferred_floor_id", floor.floor_id if floor else None),
            ):
                if slot_value and slot_name in self.extra_slots:
                    slots[slot_name] = {"value": slot_value}

        intent_response = await intent.async_handle(
            hass=hass,
            platform=llm_context.platform,
            intent_type=self.intent_handler.intent_type,
            slots=slots,
            text_input=None,
            context=llm_context.context,
            language=llm_context.language,
            assistant=llm_context.assistant,
            device_id=llm_context.device_id,
        )
        return PowerIntentResponseDict(intent_response, self._response_entities, hass)


class PowerIntentResponseDict(dict):
    """Dictionary to represent an intent response resulting from a tool call."""

    def __init__(
        self,
        intent_response: Any,
        response_entities: bool = False,
        hass: HomeAssistant | None = None,
    ) -> None:
        """Initialize the dictionary."""
        if not isinstance(intent_response, intent.IntentResponse):
            super().__init__(intent_response)
            return

        result = intent_response.as_dict()
        if response_entities and intent_response.matched_states and hass is not None:
            result["data"]["matched_states"] = [
                _format_state(hass, state) for state in intent_response.matched_states
            ]
        if response_entities and intent_response.unmatched_states and hass is not None:
            result["data"]["unmatched_states"] = [
                _format_state(hass, state) for state in intent_response.unmatched_states
            ]
        del result["language"]

        def remove_empty(value: JsonValueType):
            if isinstance(value, list):
                for v in value:
                    remove_empty(v)
            if not isinstance(value, dict):
                return
            for key in list(value.keys()):
                remove_empty(value[key])
                if not value[key] and value[key] is not False:
                    del value[key]

        remove_empty(result)

        super().__init__(result)
        self.original = intent_response


class PowerScriptTool(PowerLLMTool, llm.ScriptTool):
    """Power LLM Tool representing a Script."""


class PowerCalendarGetEventsTool(PowerLLMTool, llm.CalendarGetEventsTool):
    """Power LLM Tool allowing querying a calendar."""


class PowerTodoGetItemsTool(PowerLLMTool, llm.TodoGetItemsTool):
    """Power LLM Tool allowing querying a to-do list."""


class PowerGetLiveContextTool(PowerLLMTool, llm.GetLiveContextTool):
    """Power LLM Tool for getting the current state of exposed entities."""


class PowerGetDateTimeTool(PowerLLMTool, llm.GetDateTimeTool):
    """Power LLM Tool for getting the current date and time."""


class PowerFunctionTool(PowerLLMTool):
    """LLM Tool representing an Python function.

    The function is recommended to have annotations for all parameters.
    If a parameter name is "hass", "llm_context", or any of the LLMContext
    attributes, then the value for that parameter will be provided by the
    conversation agent 'pytest-style'.
    All other arguments will be provided by the LLM.
    Async functions are not allowed to use any blocking code, while a synchronous
    function will be executed in a separate thread.
    """

    function: Callable

    def __init__(
        self,
        function: Callable,
    ) -> None:
        """Init the class."""

        self.function = function

        self.name = function.__name__
        self.name = self.name.removeprefix("async_")

        self.description = inspect.getdoc(function)

        def hint_to_schema(hint: Any) -> Any:
            if isinstance(hint, UnionType) or get_origin(hint) is Union:
                hints = get_args(hint)
                if len(hints) == 2 and hints[0] is NoneType:
                    return vol.Maybe(hint_to_schema(hints[1]))
                if len(hints) == 2 and hints[1] is NoneType:
                    return vol.Maybe(hint_to_schema(hints[0]))
                return vol.Any(*tuple(hint_to_schema(x) for x in hints))

            if get_origin(hint) is list or get_origin(hint) is set:
                schema = get_args(hint)[0]
                if schema is Any or isinstance(schema, TypeVar):
                    return get_origin(hint)
                return [hint_to_schema(schema)]

            if get_origin(hint) is dict:
                schema = get_args(hint)
                if (
                    schema[0] is Any
                    or schema[1] is Any
                    or isinstance(schema[0], TypeVar)
                    or isinstance(schema[1], TypeVar)
                ):
                    return dict
                return {schema[0]: schema[1]}

            return hint

        schema = {}
        annotations = get_type_hints(function)
        for param in inspect.signature(function).parameters.values():
            if param.name in ("hass", "llm_context"):
                continue
            if hasattr(llm.LLMContext, param.name):
                continue

            hint = annotations.get(param.name, Any)

            schema[
                (
                    vol.Required(param.name)
                    if param.default is inspect.Parameter.empty
                    else vol.Optional(param.name, default=param.default)
                )
            ] = hint_to_schema(hint)

        self.parameters = vol.Schema(schema)

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> Any:
        """Call the function."""
        kwargs = tool_input.tool_args
        for parameter in inspect.signature(self.function).parameters.values():
            if parameter.name == "hass":
                kwargs["hass"] = hass
            elif parameter.name == "llm_context":
                kwargs["llm_context"] = llm_context
            elif hasattr(llm.LLMContext, parameter.name):
                kwargs[parameter.name] = getattr(llm_context, parameter.name)

        if inspect.iscoroutinefunction(self.function):
            return await self.function(**kwargs)

        if is_callback(self.function) or hass.loop != asyncio.get_running_loop():
            return self.function(**kwargs)

        return await hass.loop.run_in_executor(None, lambda: self.function(**kwargs))


@callback
def async_register_tool(hass: HomeAssistant, tool: PowerLLMTool | Callable) -> None:
    """Register an LLM tool with PowerLLM integration."""
    tools = hass.data.setdefault(DOMAIN, {})

    if not isinstance(tool, PowerLLMTool):
        if isinstance(tool, llm.Tool):
            raise TypeError("Please base your tool class on powerllm.PowerLLMTool")
        tool = PowerFunctionTool(tool)

    if tool.name in tools:
        _LOGGER.warning("Overwriting an already registered tool %s", tool.name)

    tools[tool.name] = tool


HASS_LIST = []
LLM_TOOL_LIST = []


def llm_tool(arg: HomeAssistant | Callable) -> Callable:
    """Register a function as an LLM Tool with decorator."""

    if isinstance(arg, HomeAssistant):
        hass = arg

        def _llm_tool(func: Callable) -> Callable:
            async_register_tool(hass, func)
            return func

        return _llm_tool

    func = arg
    LLM_TOOL_LIST.append(func)
    for hass in HASS_LIST:
        async_register_tool(hass, func)
    return func


def deferred_register_tools(hass: HomeAssistant) -> None:
    """Register tools declared with the decorator."""
    if hass in HASS_LIST:
        return

    HASS_LIST.append(hass)
    for func in LLM_TOOL_LIST:
        async_register_tool(hass, func)
