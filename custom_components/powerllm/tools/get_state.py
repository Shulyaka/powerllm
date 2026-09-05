"""Query detailed entity states without duplicating Assist's control tools."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, State
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

from ..llm_tools import PowerLLMTool

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
        if aliases := [
            alias
            for alias in er.async_get_entity_aliases(hass, registry_entry)
            if alias
        ]:
            result["aliases"] = aliases

    attributes: dict[str, Any] = {
        attribute: value
        for attribute, value in entity_state.attributes.items()
        if attribute in EXPORTED_ATTRIBUTES
    }
    if attributes:
        result["attributes"] = attributes

    return result


class GetStateTool(PowerLLMTool):
    """Query matching entities and return their detailed states."""

    name = intent.INTENT_GET_STATE
    description = (
        "Gets or checks the state of a device or entity. Use it to get a list of "
        "devices matching criteria or additional details and attributes, including "
        "entity IDs and how long ago their state changed."
    )
    parameters = vol.Schema(
        {
            vol.Optional("name"): cv.string,
            vol.Optional("area"): cv.string,
            vol.Optional("floor"): cv.string,
            vol.Optional("domain"): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional("device_class"): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional("state"): vol.All(cv.ensure_list, [cv.string]),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Handle the intent."""
        args = self.parameters(tool_input.tool_args)
        slots = {key: {"value": val} for key, val in args.items()}

        if llm_context.device_id:
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
                if slot_value:
                    slots[slot_name] = {"value": slot_value}

        intent_response = await intent.async_handle(
            hass=hass,
            platform=llm_context.platform,
            intent_type=self.name,
            slots=slots,
            text_input=None,
            context=llm_context.context,
            language=llm_context.language,
            assistant=llm_context.assistant,
            device_id=llm_context.device_id,
        )
        return GetStateResponseDict(intent_response, hass)


class GetStateResponseDict(dict):
    """Dictionary to represent an intent response resulting from a tool call."""

    def __init__(
        self,
        intent_response: intent.IntentResponse,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the dictionary."""
        result = intent_response.as_dict()
        if intent_response.matched_states:
            result["data"]["matched_states"] = [
                _format_state(hass, state) for state in intent_response.matched_states
            ]
        if intent_response.unmatched_states:
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
