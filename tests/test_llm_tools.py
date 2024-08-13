"""Test powerllm config flow."""

import pytest
import voluptuous as vol
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    floor_registry as fr,
    llm,
)

from custom_components.powerllm import llm_tools


@pytest.fixture
def llm_context() -> llm.LLMContext:
    """Return tool input context."""
    return llm.LLMContext(
        platform="test_platform",
        context=Context(),
        user_prompt=None,
        language=None,
        assistant=None,
        device_id=None,
    )


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


def test_format_state(hass: HomeAssistant) -> None:
    """Test foratting of an entity state."""
    state1 = State(
        "light.kitchen", "on", attributes={ATTR_FRIENDLY_NAME: "kitchen light"}
    )

    assert llm_tools._format_state(hass, state1) == {
        "name": "kitchen light",
        "entity_id": "light.kitchen",
        "state": "on",
        "last_changed": "0 seconds ago",
    }


def test_format_state_with_attributes(hass: HomeAssistant) -> None:
    """Test foratting of an entity state with attributes."""
    state1 = State(
        "light.kitchen",
        "on",
        attributes={
            ATTR_FRIENDLY_NAME: "kitchen light",
            "extra_attr": "filtered out",
            "brightness": "100",
        },
    )

    assert llm_tools._format_state(hass, state1) == {
        "name": "kitchen light",
        "entity_id": "light.kitchen",
        "state": "on",
        "last_changed": "0 seconds ago",
        "attributes": {"brightness": "100"},
    }


def test_format_state_with_alias(
    hass: HomeAssistant,
    area_registry: ar.AreaRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test foratting of an entity state with an alias assigned in entity registry."""
    state1 = State(
        "light.kitchen", "on", attributes={ATTR_FRIENDLY_NAME: "kitchen light"}
    )
    entity_registry.async_get_or_create(
        "light", "demo", "1234", suggested_object_id="kitchen"
    )
    entity_registry.async_update_entity(state1.entity_id, aliases={"küchenlicht"})

    assert llm_tools._format_state(hass, state1) == {
        "name": "kitchen light",
        "entity_id": "light.kitchen",
        "state": "on",
        "last_changed": "0 seconds ago",
        "aliases": ["küchenlicht"],
    }


def test_format_state_with_area(
    hass: HomeAssistant,
    area_registry: ar.AreaRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test foratting of an entity state with area assigned in area registry."""
    state1 = State(
        "light.kitchen", "on", attributes={ATTR_FRIENDLY_NAME: "kitchen light"}
    )
    area_kitchen = area_registry.async_get_or_create("kitchen")
    entity_registry.async_get_or_create(
        "light", "demo", "1234", suggested_object_id="kitchen"
    )
    entity_registry.async_update_entity(state1.entity_id, area_id=area_kitchen.id)

    assert llm_tools._format_state(hass, state1) == {
        "name": "kitchen light",
        "entity_id": "light.kitchen",
        "state": "on",
        "last_changed": "0 seconds ago",
        "area": "kitchen",
    }


def test_format_state_with_floor(
    hass: HomeAssistant,
    area_registry: ar.AreaRegistry,
    entity_registry: er.EntityRegistry,
    floor_registry: fr.FloorRegistry,
) -> None:
    """Test foratting of an entity state with area and a floor."""
    state1 = State(
        "light.kitchen", "on", attributes={ATTR_FRIENDLY_NAME: "kitchen light"}
    )

    area_kitchen = area_registry.async_get_or_create("kitchen")
    floor_1 = floor_registry.async_create("first floor", aliases={"ground floor"})
    area_kitchen = area_registry.async_update(
        area_kitchen.id, floor_id=floor_1.floor_id
    )
    entity_registry.async_get_or_create(
        "light", "demo", "1234", suggested_object_id="kitchen"
    )
    entity_registry.async_update_entity(state1.entity_id, area_id=area_kitchen.id)

    assert llm_tools._format_state(hass, state1) == {
        "name": "kitchen light",
        "entity_id": "light.kitchen",
        "state": "on",
        "last_changed": "0 seconds ago",
        "area": "kitchen",
        "floor": "first floor",
    }


async def test_function_tool(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test function tools."""
    call = {}

    @llm_tools.llm_tool(hass)
    def test_function(
        hass: HomeAssistant,
        llm_context: llm.LLMContext,
        platform: str,
        context: Context,
        required_arg: int,
        optional_arg: float | str = 9.6,
    ):
        """Test tool description."""
        call["hass"] = hass
        call["llm_context"] = llm_context
        call["platform"] = platform
        call["context"] = context
        call["required_arg"] = required_arg
        call["optional_arg"] = optional_arg
        return {"result": "test_response"}

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    tool = list(api.tools)[5]
    assert tool.name == "test_function"
    assert tool.description == "Test tool description."

    schema = {
        vol.Required("required_arg"): int,
        vol.Optional("optional_arg", default=9.6): vol.Any(float, str),
    }
    tool_schema = tool.parameters.schema
    assert isinstance(tool_schema[vol.Optional("optional_arg", default=9.6)], vol.Any)
    assert tool_schema[vol.Optional("optional_arg", default=9.6)].validators == (
        float,
        str,
    )
    schema[vol.Optional("optional_arg", default=9.6)] = tool_schema[
        vol.Optional("optional_arg", default=9.6)
    ]
    assert tool_schema == schema

    tool_input = llm.ToolInput(
        tool_name="test_function",
        tool_args={"required_arg": 4},
    )

    response = await api.async_call_tool(tool_input)

    assert response == {"result": "test_response"}
    assert call == {
        "context": llm_context.context,
        "hass": hass,
        "llm_context": llm_context,
        "optional_arg": 9.6,
        "platform": "test_platform",
        "required_arg": 4,
    }


async def test_async_function_tool(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test function tools with async function."""
    call = {}

    @llm_tools.llm_tool(hass)
    async def async_test_async_function(
        hass: HomeAssistant,
        llm_context: llm.LLMContext,
        platform: str,
        context: Context,
        required_arg: int | dict[str, int],
        optional_arg: None | float = None,
    ):
        """Test tool description."""
        call["hass"] = hass
        call["llm_context"] = llm_context
        call["platform"] = platform
        call["context"] = context
        call["required_arg"] = required_arg
        call["optional_arg"] = optional_arg
        return {"result": "test_response"}

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    tool = list(api.tools)[5]
    assert tool.name == "test_async_function"
    assert tool.description == "Test tool description."

    schema = {
        vol.Required("required_arg"): vol.Any(int, {str: int}),
        vol.Optional("optional_arg"): vol.Maybe(float),
    }
    tool_schema = tool.parameters.schema

    assert isinstance(tool_schema[vol.Optional("optional_arg")], vol.Any)
    assert tool_schema[vol.Optional("optional_arg")].validators == (None, float)
    schema[vol.Optional("optional_arg")] = tool_schema[vol.Optional("optional_arg")]

    assert isinstance(tool_schema[vol.Required("required_arg")], vol.Any)
    assert tool_schema[vol.Required("required_arg")].validators == (int, {str: int})
    schema[vol.Required("required_arg")] = tool_schema[vol.Required("required_arg")]

    assert tool_schema == schema

    tool_input = llm.ToolInput(
        tool_name="test_async_function",
        tool_args={"required_arg": 4},
    )

    response = await api.async_call_tool(tool_input)

    assert response == {"result": "test_response"}
    assert call == {
        "context": llm_context.context,
        "hass": hass,
        "llm_context": llm_context,
        "optional_arg": None,
        "platform": "test_platform",
        "required_arg": 4,
    }
