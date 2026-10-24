"""Tests for the entity ID mapping contributed by the script tool."""

from unittest.mock import patch

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.llm import LLMContext
from homeassistant.util.yaml import parse_yaml

from custom_components.powerllm.tools.script import DynamicScriptTool


@pytest.mark.parametrize("exposed_only", [True, False])
async def test_entity_mapping(
    hass: HomeAssistant, llm_context: LLMContext, exposed_only: bool
) -> None:
    """Preserve duplicate names and only disclose exposed identities, without states."""
    hass.states.async_set(
        "light.first", "on", {"friendly_name": "Lamp", "brightness": 100}
    )
    hass.states.async_set("light.second", "off", {"friendly_name": "Lamp"})
    hass.states.async_set("calendar.events", "off", {"friendly_name": "Calendar"})
    hass.states.async_set("script.evening", "off", {"friendly_name": "Evening"})
    hass.states.async_set("light.hidden", "on", {"friendly_name": "Hidden"})
    for entity_id in (
        "light.first",
        "light.second",
        "calendar.events",
        "script.evening",
    ):
        async_expose_entity(hass, "conversation", entity_id, True)
    async_expose_entity(hass, "conversation", "light.hidden", False)
    prompt = DynamicScriptTool(exposed_only).prompt(hass, llm_context)
    assert parse_yaml(prompt.split("\n", 1)[1]) == {
        "light.first": "Lamp",
        "light.second": "Lamp",
        "calendar.events": "Calendar",
        "script.evening": "Evening",
    }


@pytest.mark.parametrize(
    ("script", "message"),
    [
        ("delay: '00:00:01'\nsequence: []", 'action should be inside the "sequence"'),
        ("trigger: []", "Please rewrite without triggers"),
        (
            "action: light.turn_on\ntarget:\n  entity_id: light.hidden",
            "Referencing unknown or unexposed entity light.hidden",
        ),
    ],
)
async def test_script_validation_error(
    hass: HomeAssistant, async_call_tool, script: str, message: str
) -> None:
    """Expose intentional script validation failures as Home Assistant errors."""
    hass.states.async_set("light.hidden", "off")
    async_expose_entity(hass, "conversation", "light.hidden", False)

    with pytest.raises(ServiceValidationError, match=message):
        await async_call_tool("homeassistant_script", script=script)


@pytest.fixture
def script_events(hass: HomeAssistant) -> list[Event]:
    """Record real script events and their execution context."""
    events = []

    @callback
    def record(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen("powerllm_test_result", record)
    return events


@pytest.mark.parametrize(
    "source",
    [
        "event: powerllm_test_result\nevent_data:\n  message: hello",
        "sequence:\n  - event: powerllm_test_result\n    event_data:\n      message: hello",
        "- event: powerllm_test_result\n  event_data:\n    message: hello",
        ["event: powerllm_test_result\nevent_data:\n  message: hello"],
        ["- event: powerllm_test_result\n  event_data:\n    message: hello"],
    ],
)
async def test_script_input_formats(
    hass: HomeAssistant,
    llm_context: LLMContext,
    async_call_tool,
    script_events: list[Event],
    source,
) -> None:
    """Execute single actions, sequence wrappers, lists, and YAML string lists."""
    result = await async_call_tool("homeassistant_script", script=source)
    await hass.async_block_till_done()

    assert result == {"success": True}
    assert [event.data for event in script_events] == [{"message": "hello"}]
    assert script_events[0].context is llm_context.context


async def test_script_variables_and_nested_templates(
    hass: HomeAssistant, async_call_tool, script_events: list[Event]
) -> None:
    """Normalize variables, templates, conditions, and nested action sequences."""
    source = """
sequence:
  - variables:
      greeting: hello
  - if:
      - condition: template
        value_template: "{{ greeting == 'hello' }}"
    then:
      - repeat:
          count: 2
          sequence:
            - event: powerllm_test_result
              event_data:
                message: "{{ greeting }}"
"""

    result = await async_call_tool("homeassistant_script", script=source)
    await hass.async_block_till_done()

    assert result == {"success": True}
    assert [event.data for event in script_events] == [
        {"message": "hello"},
        {"message": "hello"},
    ]


async def test_script_response(async_call_tool) -> None:
    """Keep native response variables when validating a sequence wrapper."""
    source = """
sequence:
  - variables:
      answer:
        value: 42
  - stop: finished
    response_variable: answer
"""

    result = await async_call_tool("homeassistant_script", script=source)

    assert result == {"service_response": {"value": 42}}


@pytest.mark.parametrize("source", ["[]", "sequence: []", []])
async def test_empty_script(async_call_tool, source) -> None:
    """A valid empty action sequence succeeds without a script result object."""
    assert await async_call_tool("homeassistant_script", script=source) == {
        "success": True
    }


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "Script must be an action or a list of actions"),
        ("null", "Script must be an action or a list of actions"),
        ("42", "Script must be an action or a list of actions"),
        ("plain text", "Script must be an action or a list of actions"),
        ("{}", "Invalid script"),
        ("sequence: 42", "Invalid script"),
        ("sequence: [{}]", "Invalid script"),
        ("- event: powerllm_test_result\n- unknown: action", "Invalid script"),
        (["event: powerllm_test_result", "unknown: action"], "Invalid script"),
        ("triggers: []\nsequence: []", "Please rewrite without triggers"),
        ("[", "Invalid script YAML"),
        ("variables:\n  value: '{{ invalid'", "Invalid script"),
    ],
)
async def test_invalid_script_before_execution(
    hass: HomeAssistant,
    async_call_tool,
    script_events: list[Event],
    source,
    message: str,
) -> None:
    """Reject malformed YAML and actions before any part of the script executes."""
    with pytest.raises(ServiceValidationError, match=message):
        await async_call_tool("homeassistant_script", script=source)
    await hass.async_block_till_done()

    assert script_events == []


async def test_script_setup_error(async_call_tool) -> None:
    """Preserve HA errors raised during action setup instead of reclassifying them."""
    error = HomeAssistantError("Action setup failed")
    with patch(
        "custom_components.powerllm.tools.script.async_validate_actions_config",
        side_effect=error,
    ), pytest.raises(HomeAssistantError) as raised:
        await async_call_tool("homeassistant_script", script="event: powerllm_test")

    assert raised.value is error


async def test_script_background_execution(
    hass: HomeAssistant,
    llm_context: LLMContext,
    async_call_tool,
    script_events: list[Event],
) -> None:
    """Keep a timed-out validated script running with the original call context."""
    with patch("custom_components.powerllm.tools.script.SCRIPT_TIMEOUT", 0):
        result = await async_call_tool(
            "homeassistant_script", script="event: powerllm_test_result"
        )
    await hass.async_block_till_done()

    assert result == {
        "success": True,
        "message": "The script is scheduled to execute in background",
    }
    assert len(script_events) == 1
    assert script_events[0].context is llm_context.context
