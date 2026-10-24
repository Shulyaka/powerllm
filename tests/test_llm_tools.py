"""Test powerllm config flow."""

from functools import wraps

import probatio as vol
import pytest
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import Context, HomeAssistant, State, callback
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers import (
    area_registry as ar,
    entity_registry as er,
    floor_registry as fr,
    llm,
)

from custom_components.powerllm import llm_tools
from custom_components.powerllm.const import DOMAIN
from custom_components.powerllm.tools import get_state

from . import tool_result_data


def test_format_state(hass: HomeAssistant) -> None:
    """Test foratting of an entity state."""
    state1 = State(
        "light.kitchen", "on", attributes={ATTR_FRIENDLY_NAME: "kitchen light"}
    )

    assert get_state._format_state(hass, state1) == {
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

    assert get_state._format_state(hass, state1) == {
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

    assert get_state._format_state(hass, state1) == {
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

    assert get_state._format_state(hass, state1) == {
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

    assert get_state._format_state(hass, state1) == {
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

    assert hass.data[DOMAIN]["test_function"].integration == DOMAIN
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    tool = list(api.tools)[-1]
    assert tool.name == "test_function"
    assert tool.description == "Test tool description."

    assert tool.parameters({"required_arg": 4}) == {
        "required_arg": 4,
        "optional_arg": 9.6,
    }
    for value in (2.5, "text"):
        args = {"required_arg": 4, "optional_arg": value}
        assert tool.parameters(args) == args
    for args in ({}, {"required_arg": "bad"}, {"required_arg": 4, "optional_arg": []}):
        with pytest.raises(vol.Invalid):
            tool.parameters(args)

    tool_input = llm.ToolInput(
        tool_name="test_function",
        tool_args={"required_arg": 4},
    )

    response = tool_result_data(await api.async_call_tool(tool_input))

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

    assert hass.data[DOMAIN]["test_async_function"].integration == DOMAIN
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    tool = list(api.tools)[-1]
    assert tool.name == "test_async_function"
    assert tool.description == "Test tool description."

    assert tool.parameters({"required_arg": 4}) == {
        "required_arg": 4,
        "optional_arg": None,
    }
    for value in (None, 2.5):
        args = {"required_arg": {"count": 4}, "optional_arg": value}
        assert tool.parameters(args) == args
    for args in (
        {},
        {"required_arg": {"count": "bad"}},
        {"required_arg": 4, "optional_arg": "bad"},
    ):
        with pytest.raises(vol.Invalid):
            tool.parameters(args)

    tool_input = llm.ToolInput(
        tool_name="test_async_function",
        tool_args={"required_arg": 4},
    )

    response = tool_result_data(await api.async_call_tool(tool_input))

    assert response == {"result": "test_response"}
    assert call == {
        "context": llm_context.context,
        "hass": hass,
        "llm_context": llm_context,
        "optional_arg": None,
        "platform": "test_platform",
        "required_arg": 4,
    }


@pytest.mark.parametrize("execution", ["async", "callback", "executor"])
@pytest.mark.parametrize(
    "error",
    [
        ValueError("Invalid operation"),
        HomeAssistantError("Tool failed"),
        ServiceValidationError("Service rejected"),
        Unauthorized(),
        vol.Invalid("Invalid value"),
    ],
)
async def test_function_tool_errors(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_init_component,
    execution: str,
    error: Exception,
) -> None:
    """Report failures through HA's exception handling on every execution path."""

    def sync_failing_tool():
        raise error

    async def async_failing_tool():
        raise error

    if execution == "async":
        failing_tool = async_failing_tool
    else:
        failing_tool = sync_failing_tool
        if execution == "callback":
            failing_tool = callback(failing_tool)

    failing_tool.__name__ = "failing_tool"
    llm_tools.llm_tool(hass)(failing_tool)
    api = await llm.async_get_api(hass, "powerllm", llm_context)

    if isinstance(error, (HomeAssistantError, vol.Invalid)):
        with pytest.raises(type(error)) as raised:
            await api.async_call_tool(
                llm.ToolInput(tool_name="failing_tool", tool_args={})
            )
        assert raised.value is error
    else:
        with pytest.raises(
            HomeAssistantError,
            match="Error calling failing_tool \\(ValueError\\): Invalid operation",
        ) as raised:
            await api.async_call_tool(
                llm.ToolInput(tool_name="failing_tool", tool_args={})
            )
        assert raised.value.__cause__ is error


@pytest.mark.parametrize(
    ("module", "integration"),
    [
        ("custom_components.external_provider", "external_provider"),
        ("custom_components.external_provider.tools", "external_provider"),
        ("homeassistant.components.core_provider", "core_provider"),
        ("homeassistant.components.core_provider.tools", "core_provider"),
        ("custom_components.powerllm.tools.python_code", DOMAIN),
        ("tests.test_llm_tools", DOMAIN),
        ("some_package.tools", DOMAIN),
        ("custom_components_extra.provider", DOMAIN),
        ("homeassistant.components_extra.provider", DOMAIN),
        ("custom_components.", DOMAIN),
        ("homeassistant.components.", DOMAIN),
        (None, DOMAIN),
    ],
)
def test_function_tool_integration_module(module: str | None, integration: str) -> None:
    """Infer an integration domain only from recognized integration modules."""

    def module_tool():
        """Return data from an integration tool."""
        return {}

    module_tool.__module__ = module
    tool = llm_tools.PowerFunctionTool(module_tool)

    assert tool.integration == integration


@pytest.mark.parametrize("registration", ["direct", "immediate", "deferred"])
async def test_function_tool_integration_registration(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_init_component,
    monkeypatch: pytest.MonkeyPatch,
    registration: str,
) -> None:
    """Preserve inferred attribution through each function registration path."""
    monkeypatch.setattr(llm_tools, "HASS_LIST", [])
    monkeypatch.setattr(llm_tools, "LLM_TOOL_LIST", [])

    def external_function_tool():
        """Return data from another integration."""
        return {}

    external_function_tool.__module__ = "custom_components.external_provider.tools"
    if registration == "direct":
        llm_tools.async_register_tool(hass, external_function_tool)
    elif registration == "immediate":
        assert (
            llm_tools.llm_tool(hass)(external_function_tool) is external_function_tool
        )
    else:
        assert llm_tools.llm_tool(external_function_tool) is external_function_tool
        assert "external_function_tool" not in hass.data[DOMAIN]
        llm_tools.deferred_register_tools(hass)

    tool = hass.data[DOMAIN]["external_function_tool"]
    assert tool.function is external_function_tool
    assert tool.integration == "external_provider"

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    registered = next(
        tool for tool in api.tools if tool.name == "external_function_tool"
    )
    assert registered is tool
    assert registered.integration == "external_provider"


def test_function_tool_integration_wrapped_function() -> None:
    """Attribute decorated functions to the original integration implementation."""

    def original_tool():
        """Return data from the original integration."""
        return {}

    original_tool.__module__ = "custom_components.original_provider.tools"

    @wraps(original_tool)
    def wrapped_tool():
        return original_tool()

    wrapped_tool.__module__ = "custom_components.wrapper_provider.helpers"
    tool = llm_tools.PowerFunctionTool(wrapped_tool)

    assert tool.function is wrapped_tool
    assert tool.integration == "original_provider"


def test_function_tool_integration_override(hass: HomeAssistant) -> None:
    """Preserve an explicit function-wrapper provider during registration."""

    class ExplicitFunctionTool(llm_tools.PowerFunctionTool):
        """Function wrapper supplied by an explicitly identified provider."""

        integration = "explicit_provider"

    def overridden_function_tool():
        """Return data from a function with a different inferred provider."""
        return {}

    overridden_function_tool.__module__ = "custom_components.detected_provider.tools"
    tool = ExplicitFunctionTool(overridden_function_tool)
    assert tool.integration == "explicit_provider"

    llm_tools.async_register_tool(hass, tool)
    assert hass.data[DOMAIN]["overridden_function_tool"] is tool
    assert tool.integration == "explicit_provider"


@pytest.mark.parametrize("instance_integration", [None, "instance_provider"])
async def test_tool_integration_override(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_init_component,
    instance_integration: str | None,
) -> None:
    """Preserve provider metadata from external tool classes and instances."""

    class ExternalTool(llm_tools.PowerLLMTool):
        """Tool supplied by a separate integration."""

        name = "external_tool"
        integration = "external_provider"

    tool = ExternalTool()
    expected_integration = "external_provider"
    if instance_integration is not None:
        tool.integration = instance_integration
        expected_integration = instance_integration

    llm_tools.async_register_tool(hass, tool)
    assert tool.integration == expected_integration

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    registered = next(tool for tool in api.tools if tool.name == "external_tool")
    assert registered is tool
    assert registered.integration == expected_integration


def test_format_state_with_computed_alias(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Resolve Core's computed-name marker into a readable alias."""
    entry = entity_registry.async_get_or_create(
        "light",
        "demo",
        "computed",
        suggested_object_id="kitchen",
        original_name="Kitchen light",
    )
    entity_registry.async_update_entity(
        entry.entity_id, aliases=[er.COMPUTED_NAME, "Kitchen lamp"]
    )
    state = State(entry.entity_id, "on", {ATTR_FRIENDLY_NAME: "Kitchen light"})
    assert get_state._format_state(hass, state)["aliases"] == [
        "Kitchen light",
        "Kitchen lamp",
    ]
