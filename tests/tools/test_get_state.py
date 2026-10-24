"""Tests for detailed state queries."""

from unittest.mock import patch

import probatio as vol
import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    intent,
    llm,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powerllm.tools.get_state import (
    GetStateTool,
    _area_name,
    _floor_name,
)

from tests import tool_result_data


@pytest.fixture
def child_device(
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
    floor_registry: fr.FloorRegistry,
    mock_config_entry: MockConfigEntry,
) -> dr.ChildDeviceEntry:
    """Create a child device that inherits its parent's area and floor."""
    floor = floor_registry.async_create("Parent floor")
    area = area_registry.async_create("Parent area", floor_id=floor.floor_id)
    parent = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={("test", "parent")},
        suggested_area=area.name,
    )
    return device_registry.async_get_or_create_child(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={("test", "child")},
        parent_device_id=parent.id,
    )


@pytest.mark.parametrize("area_source", ["parent", "child", "entity"])
async def test_get_state_child_device_area(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    area_registry: ar.AreaRegistry,
    floor_registry: fr.FloorRegistry,
    child_device: dr.ChildDeviceEntry,
    mock_init_component,
    area_source: str,
) -> None:
    """Format inherited areas and floors while preserving explicit overrides."""
    area = area_registry.async_get_area_by_name("Parent area")
    if area_source != "parent":
        floor = floor_registry.async_create("Child floor")
        area = area_registry.async_create("Child area", floor_id=floor.floor_id)
        device_registry.async_update_child_device(child_device.id, area_id=area.id)
    device_area = area
    entity = entity_registry.async_get_or_create(
        "light",
        "test",
        "child_light",
        device_id=child_device.id,
        original_name="Child light",
    )
    if area_source == "entity":
        floor = floor_registry.async_create("Entity floor")
        area = area_registry.async_create("Entity area", floor_id=floor.floor_id)
        entity_registry.async_update_entity(entity.entity_id, area_id=area.id)
    hass.states.async_set(entity.entity_id, "on", {"friendly_name": "Child light"})
    async_expose_entity(hass, "conversation", entity.entity_id, True)
    api = await llm.async_get_api(hass, "powerllm", llm_context)

    response = tool_result_data(
        await api.async_call_tool(
            llm.ToolInput(tool_name="HassGetState", tool_args={"domain": "light"})
        )
    )

    matched_states = response["data"]["matched_states"]
    assert len(matched_states) == 1
    assert matched_states[0]["entity_id"] == entity.entity_id
    assert matched_states[0]["area"] == area.name
    assert (
        matched_states[0]["floor"] == floor_registry.async_get_floor(area.floor_id).name
    )
    assert _area_name(hass, child_device.id) == device_area.name
    assert (
        _floor_name(hass, child_device.id)
        == floor_registry.async_get_floor(device_area.floor_id).name
    )


@pytest.mark.parametrize("area_source", ["parent", "child", "none"])
async def test_get_state_child_device_context(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
    floor_registry: fr.FloorRegistry,
    child_device: dr.ChildDeviceEntry,
    mock_init_component,
    area_source: str,
) -> None:
    """Use the calling child device's effective area and floor as preferences."""
    area = area_registry.async_get_area_by_name("Parent area")
    if area_source == "child":
        floor = floor_registry.async_create("Child floor")
        area = area_registry.async_create("Child area", floor_id=floor.floor_id)
        device_registry.async_update_child_device(child_device.id, area_id=area.id)
    elif area_source == "none":
        device_registry.async_update_device(child_device.parent_device_id, area_id=None)
    llm_context.device_id = child_device.id
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    intent_response = intent.IntentResponse("en")

    with patch(
        "homeassistant.helpers.intent.async_handle", return_value=intent_response
    ) as mock_intent_handle:
        await api.async_call_tool(llm.ToolInput(tool_name="HassGetState", tool_args={}))

    slots = mock_intent_handle.call_args.kwargs["slots"]
    if area_source == "none":
        assert slots == {}
        assert _area_name(hass, child_device.id) is None
        assert _floor_name(hass, child_device.id) is None
    else:
        assert slots == {
            "preferred_area_id": {"value": area.id},
            "preferred_floor_id": {"value": area.floor_id},
        }


async def test_get_state_context(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
    floor_registry: fr.FloorRegistry,
    mock_init_component,
) -> None:
    """Keep detailed responses and pass the request's device context to the intent."""
    test_context = Context(user_id="12345")
    llm_context = llm.LLMContext(
        platform="test_platform",
        context=test_context,
        language="*",
        assistant="conversation",
        device_id=None,
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert test_context.json_fragment  # To reproduce an error case in tracing
    intent_response = intent.IntentResponse("*")
    intent_response.async_set_states(
        [State("light.matched", "on")], [State("light.unmatched", "on")]
    )
    intent_response.async_set_speech("Some speech")
    intent_response.async_set_card("Card title", "card content")
    intent_response.async_set_speech_slots({"hello": 1})
    intent_response.async_set_reprompt("Do it again")
    tool_input = llm.ToolInput(
        tool_name="HassGetState",
        tool_args={"area": "kitchen", "floor": "ground_floor"},
    )

    with patch(
        "homeassistant.helpers.intent.async_handle", return_value=intent_response
    ) as mock_intent_handle:
        response = tool_result_data(await api.async_call_tool(tool_input))

    mock_intent_handle.assert_awaited_once_with(
        hass=hass,
        platform="test_platform",
        intent_type="HassGetState",
        slots={
            "area": {"value": "kitchen"},
            "floor": {"value": "ground_floor"},
        },
        text_input=None,
        context=test_context,
        language="*",
        assistant="conversation",
        device_id=None,
    )
    assert response == {
        "card": {
            "simple": {
                "content": "card content",
                "title": "Card title",
            },
        },
        "data": {
            "matched_states": [
                {
                    "entity_id": "light.matched",
                    "last_changed": "0 seconds ago",
                    "name": "matched",
                    "state": "on",
                },
            ],
            "unmatched_states": [
                {
                    "entity_id": "light.unmatched",
                    "last_changed": "0 seconds ago",
                    "name": "unmatched",
                    "state": "on",
                },
            ],
        },
        "reprompt": {
            "plain": {
                "reprompt": "Do it again",
            },
        },
        "response_type": "action_done",
        "speech": {
            "plain": {
                "speech": "Some speech",
            },
        },
        "speech_slots": {
            "hello": 1,
        },
    }

    # Call with a device/area/floor
    entry = MockConfigEntry(title=None)
    entry.add_to_hass(hass)

    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "1234")},
        suggested_area="Test Area",
    )
    area = area_registry.async_get_area_by_name("Test Area")
    floor = floor_registry.async_create("2")
    area_registry.async_update(area.id, floor_id=floor.floor_id)
    llm_context.device_id = device.id

    with patch(
        "homeassistant.helpers.intent.async_handle", return_value=intent_response
    ) as mock_intent_handle:
        response = tool_result_data(await api.async_call_tool(tool_input))

    mock_intent_handle.assert_awaited_once_with(
        hass=hass,
        platform="test_platform",
        intent_type="HassGetState",
        slots={
            "area": {"value": "kitchen"},
            "floor": {"value": "ground_floor"},
            "preferred_area_id": {"value": area.id},
            "preferred_floor_id": {"value": floor.floor_id},
        },
        text_input=None,
        context=test_context,
        language="*",
        assistant="conversation",
        device_id=device.id,
    )
    assert response == {
        "card": {
            "simple": {
                "content": "card content",
                "title": "Card title",
            },
        },
        "data": {
            "matched_states": [
                {
                    "entity_id": "light.matched",
                    "last_changed": "0 seconds ago",
                    "name": "matched",
                    "state": "on",
                },
            ],
            "unmatched_states": [
                {
                    "entity_id": "light.unmatched",
                    "last_changed": "0 seconds ago",
                    "name": "unmatched",
                    "state": "on",
                },
            ],
        },
        "response_type": "action_done",
        "reprompt": {
            "plain": {
                "reprompt": "Do it again",
            },
        },
        "speech": {
            "plain": {
                "speech": "Some speech",
            },
        },
        "speech_slots": {
            "hello": 1,
        },
    }


async def test_get_state_filters(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Query actual exposed states and retain both matching and nonmatching details."""
    hass.states.async_set(
        "light.on", "on", {"friendly_name": "On light", "brightness": 100}
    )
    hass.states.async_set("light.off", "off", {"friendly_name": "Off light"})
    hass.states.async_set("light.hidden", "on", {"friendly_name": "Hidden light"})
    async_expose_entity(hass, "conversation", "light.on", True)
    async_expose_entity(hass, "conversation", "light.off", True)
    async_expose_entity(hass, "conversation", "light.hidden", False)
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    result = await api.async_call_tool(
        llm.ToolInput(
            tool_name="HassGetState", tool_args={"domain": "light", "state": "on"}
        )
    )
    result = tool_result_data(result)
    assert result["response_type"] == "query_answer"
    assert result["data"]["matched_states"] == [
        {
            "name": "On light",
            "entity_id": "light.on",
            "state": "on",
            "last_changed": "0 seconds ago",
            "attributes": {"brightness": 100},
        }
    ]
    assert result["data"]["unmatched_states"] == [
        {
            "name": "Off light",
            "entity_id": "light.off",
            "state": "off",
            "last_changed": "0 seconds ago",
        }
    ]
    assert "light.hidden" not in str(result)


async def test_get_state_invalid_args(
    hass: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Reject unsupported arguments before calling the intent."""
    with pytest.raises(vol.Invalid):
        await GetStateTool().async_call(
            hass,
            llm.ToolInput(
                tool_name="HassGetState", tool_args={"preferred_area_id": "injected"}
            ),
            llm_context,
        )
