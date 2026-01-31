"""Test powerllm config flow."""

from decimal import Decimal
from unittest.mock import patch

import voluptuous as vol
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.components.intent import async_register_timer_handler
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    intent,
    llm,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powerllm.const import CONF_PROMPT_ENTITIES

INTENT_TOOLS = [
    "HassTurnOn",
    "HassTurnOff",
    "HassGetState",
    "HassSetPosition",
    "HassStopMoving",
]

TIMER_TOOLS = [
    "HassStartTimer",
    "HassCancelTimer",
    "HassCancelAllTimers",
    "HassIncreaseTimer",
    "HassDecreaseTimer",
    "HassPauseTimer",
    "HassUnpauseTimer",
    "HassTimerStatus",
]

ASSIST_TOOLS = [
    "GetDateTime",
]

POWERLLM_TOOLS = [
    "homeassistant_script",
    "websearch",
    "news",
    "memory",
    "python_code_execute",
    "web_scrape",
]


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


async def test_powerllm_api(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
    floor_registry: fr.FloorRegistry,
    mock_init_component,
) -> None:
    """Test Assist API."""
    entity_registry.async_get_or_create(
        "light",
        "kitchen",
        "mock-id-kitchen",
        original_name="Kitchen",
        suggested_object_id="kitchen",
    ).write_unavailable_state(hass)

    test_context = Context(user_id="12345")
    llm_context = llm.LLMContext(
        platform="test_platform",
        context=test_context,
        language="*",
        assistant="conversation",
        device_id=None,
    )
    schema = {
        vol.Optional("area"): cv.string,
        vol.Optional("floor"): cv.string,
        vol.Optional("preferred_area_id"): cv.string,
        vol.Optional("preferred_floor_id"): cv.string,
    }

    class MyIntentHandler(intent.IntentHandler):
        intent_type = "test_intent"
        slot_schema = schema
        platforms = set()  # Match none

    intent_handler = MyIntentHandler()

    intent.async_register(hass, intent_handler)

    assert len(llm.async_get_apis(hass)) == 2
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert len(api.tools) == len(INTENT_TOOLS) + len(POWERLLM_TOOLS) + 1

    # Match all
    intent_handler.platforms = None

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert len(api.tools) == len(INTENT_TOOLS) + len(POWERLLM_TOOLS) + 2

    # Match specific domain
    intent_handler.platforms = {"light"}

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert len(api.tools) == len(INTENT_TOOLS) + len(POWERLLM_TOOLS) + 2
    tool = api.tools[4]
    assert tool.name == "test_intent"
    assert tool.description == "Execute Home Assistant test_intent intent"
    assert tool.parameters == vol.Schema(
        {
            vol.Optional("area"): cv.string,
            vol.Optional("floor"): cv.string,
            # No preferred_area_id, preferred_floor_id
        }
    )
    assert str(tool) == "<PowerIntentTool - test_intent>"

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
        tool_name="test_intent",
        tool_args={"area": "kitchen", "floor": "ground_floor"},
    )

    with patch(
        "homeassistant.helpers.intent.async_handle", return_value=intent_response
    ) as mock_intent_handle:
        response = await api.async_call_tool(tool_input)

    mock_intent_handle.assert_awaited_once_with(
        hass=hass,
        platform="test_platform",
        intent_type="test_intent",
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
        response = await api.async_call_tool(tool_input)

    mock_intent_handle.assert_awaited_once_with(
        hass=hass,
        platform="test_platform",
        intent_type="test_intent",
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


async def test_powerllm_api_get_timer_tools(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test getting timer tools with Assist API."""
    api = await llm.async_get_api(hass, "powerllm", llm_context)

    assert "HassStartTimer" not in [tool.name for tool in api.tools]

    llm_context.device_id = "test_device"

    async_register_timer_handler(hass, "test_device", lambda *args: None)

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert "HassStartTimer" in [tool.name for tool in api.tools]


async def test_powerllm_api_tools(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test getting timer tools with Assist API."""
    llm_context.device_id = "test_device"

    async_register_timer_handler(hass, "test_device", lambda *args: None)

    class MyIntentHandler(intent.IntentHandler):
        intent_type = "Super crazy intent with unique nåme"
        description = "my intent handler"

    intent.async_register(hass, MyIntentHandler())

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert [tool.name for tool in api.tools] == [
        *INTENT_TOOLS,
        *TIMER_TOOLS,
        "Super_crazy_intent_with_unique_name",
        *ASSIST_TOOLS,
        *POWERLLM_TOOLS,
    ]


async def test_powerllm_api_description(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
) -> None:
    """Test intent description with Assist API."""

    class MyIntentHandler(intent.IntentHandler):
        intent_type = "test_intent"
        description = "my intent handler"

    intent.async_register(hass, MyIntentHandler())

    assert len(llm.async_get_apis(hass)) == 2
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert (
        len(api.tools)
        == len(INTENT_TOOLS) + len(ASSIST_TOOLS) + len(POWERLLM_TOOLS) + 2
    )
    tool = api.tools[len(INTENT_TOOLS) + 1]
    assert tool.name == "test_intent"
    assert tool.description == "my intent handler"


async def test_powerllm_api_prompt(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    area_registry: ar.AreaRegistry,
    floor_registry: fr.FloorRegistry,
    mock_init_component,
    mock_config_entry,
) -> None:
    """Test prompt for the assist API."""
    context = Context()
    llm_context = llm.LLMContext(
        platform="test_platform",
        context=context,
        language="*",
        assistant="conversation",
        device_id=None,
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (
        "Only if the user wants to control a device, tell them to expose entities to "
        "their voice assistant in Home Assistant."
    )

    # Expose entities

    # Create a script with a unique ID
    assert await async_setup_component(
        hass,
        "script",
        {
            "script": {
                "test_script": {
                    "description": "This is a test script",
                    "sequence": [],
                    "fields": {
                        "beer": {"description": "Number of beers"},
                        "wine": {},
                    },
                }
            }
        },
    )
    async_expose_entity(hass, "conversation", "script.test_script", True)

    entry = MockConfigEntry(title=None)
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "1234")},
        suggested_area="Test Area",
    )
    area = area_registry.async_get_area_by_name("Test Area")
    area_registry.async_update(area.id, aliases=["Alternative name"])
    entry1 = entity_registry.async_get_or_create(
        "light",
        "kitchen",
        "mock-id-kitchen",
        original_name="Kitchen",
        suggested_object_id="kitchen",
    )
    entry2 = entity_registry.async_get_or_create(
        "light",
        "living_room",
        "mock-id-living-room",
        original_name="Living Room",
        suggested_object_id="living_room",
        device_id=device.id,
    )
    hass.states.async_set(
        entry1.entity_id,
        "on",
        {"friendly_name": "Kitchen", "temperature": Decimal("0.9"), "humidity": 65},
    )
    hass.states.async_set(entry2.entity_id, "on", {"friendly_name": "Living Room"})

    def create_entity(
        device: dr.DeviceEntry, write_state=True, aliases: set[str] | None = None
    ) -> None:
        """Create an entity for a device and track entity_id."""
        entity = entity_registry.async_get_or_create(
            "light",
            "test",
            device.id,
            device_id=device.id,
            original_name=str(device.name or "Unnamed Device"),
            suggested_object_id=str(device.name or "unnamed_device"),
        )
        if aliases:
            entity_registry.async_update_entity(entity.entity_id, aliases=aliases)
        if write_state:
            entity.write_unavailable_state(hass)

    create_entity(
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", "1234")},
            name="Test Device",
            manufacturer="Test Manufacturer",
            model="Test Model",
            suggested_area="Test Area",
        ),
        aliases={"my test light"},
    )
    for i in range(3):
        create_entity(
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                connections={("test", f"{i}abcd")},
                name="Test Service",
                manufacturer="Test Manufacturer",
                model="Test Model",
                suggested_area="Test Area",
                entry_type=dr.DeviceEntryType.SERVICE,
            )
        )
    create_entity(
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", "5678")},
            name="Test Device 2",
            manufacturer="Test Manufacturer 2",
            model="Device 2",
            suggested_area="Test Area 2",
        )
    )
    create_entity(
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", "9876")},
            name="Test Device 3",
            manufacturer="Test Manufacturer 3",
            model="Test Model 3A",
            suggested_area="Test Area 2",
        )
    )
    create_entity(
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", "qwer")},
            name="Test Device 4",
            suggested_area="Test Area 2",
        )
    )
    device2 = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test", "9876-disabled")},
        name="Test Device 3 - disabled",
        manufacturer="Test Manufacturer 3",
        model="Test Model 3A",
        suggested_area="Test Area 2",
    )
    device_registry.async_update_device(
        device2.id, disabled_by=dr.DeviceEntryDisabler.USER
    )
    create_entity(device2, False)
    create_entity(
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", "9876-no-name")},
            manufacturer="Test Manufacturer NoName",
            model="Test Model NoName",
            suggested_area="Test Area 2",
        )
    )
    create_entity(
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={("test", "9876-integer-values")},
            name=1,
            manufacturer=2,
            model=3,
            suggested_area="Test Area 2",
        )
    )

    lock_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={("test2", "12345")},
        name="Test Lock",
        manufacturer="Test Manufacturer",
        model="Test Model",
        suggested_area="Test Area",
    )

    lock_entity = entity_registry.async_get_or_create(
        "lock",
        "test",
        lock_device.id,
        device_id=lock_device.id,
        original_name=str(device.name or "Unnamed Device"),
        suggested_object_id=str(device.name or "unnamed_device"),
    )
    lock_entity.write_unavailable_state(hass)

    exposed_entities_prompt = (
        "Live Context: An overview of the areas and the devices in this smart home:" """
- names: '1'
  domain: light
  state: unavailable
  areas: Test Area 2
- names: Kitchen
  domain: light
  state: 'on'
  attributes:
    temperature: '0.9'
    humidity: '65'
- names: Living Room
  domain: light
  state: 'on'
  areas: Test Area, Alternative name
- names: Test Device, my test light
  domain: light
  state: unavailable
  areas: Test Area, Alternative name
- names: Test Device 2
  domain: light
  state: unavailable
  areas: Test Area 2
- names: Test Device 3
  domain: light
  state: unavailable
  areas: Test Area 2
- names: Test Device 4
  domain: light
  state: unavailable
  areas: Test Area 2
- names: Test Service
  domain: light
  state: unavailable
  areas: Test Area, Alternative name
- names: Test Service
  domain: light
  state: unavailable
  areas: Test Area, Alternative name
- names: Test Service
  domain: light
  state: unavailable
  areas: Test Area, Alternative name
- names: Unnamed Device
  domain: light
  state: unavailable
  areas: Test Area 2
"""
    )
    stateless_exposed_entities_prompt = (
        "Static Context: An overview of the areas and the devices in this smart home:"
        """
light.1:
  names: '1'
  domain: light
  areas: Test Area 2
light.kitchen:
  names: Kitchen
  domain: light
light.living_room:
  names: Living Room
  domain: light
  areas: Test Area, Alternative name
light.test_device:
  names: Test Device, my test light
  domain: light
  areas: Test Area, Alternative name
light.test_device_2:
  names: Test Device 2
  domain: light
  areas: Test Area 2
light.test_device_3:
  names: Test Device 3
  domain: light
  areas: Test Area 2
light.test_device_4:
  names: Test Device 4
  domain: light
  areas: Test Area 2
light.test_service:
  names: Test Service
  domain: light
  areas: Test Area, Alternative name
light.test_service_2:
  names: Test Service
  domain: light
  areas: Test Area, Alternative name
light.test_service_3:
  names: Test Service
  domain: light
  areas: Test Area, Alternative name
light.unnamed_device:
  names: Unnamed Device
  domain: light
  areas: Test Area 2
"""
    )
    first_part_prompt = (
        "When controlling Home Assistant always call the intent tools. "
        "When controlling a device, prefer passing just name and domain. "
        "When controlling an area, prefer passing just area name and domain."
    )
    lock_prompt = "Use HassTurnOn to lock and HassTurnOff to unlock a lock."
    no_timer_prompt = "This device is not able to start timers."

    area_prompt = (
        "When a user asks to turn on all devices of a specific type, "
        "ask user to specify an area, unless there is only one device of that type."
    )
    dynamic_context_prompt = (
        "You ARE equipped to answer questions about the current state of"
        """
the home using the `GetLiveContext` tool. This is a primary function. Do not state """
        """you lack the
functionality if the question requires live data.
If the user asks about device existence/type (e.g., "Do I have lights in the """
        """bedroom?"): Answer
from the static context below.
If the user asks about the CURRENT state, value, or mode (e.g., "Is the lock locked?",
"Is the fan on?", "What mode is the thermostat in?", "What is the temperature """
        """outside?"):
    1.  Recognize this requires live data.
    2.  You MUST call `GetLiveContext`. This tool will provide the needed real-time """
        """information (like temperature from the local weather, lock status, etc.).
    3.  Use the tool's response** to answer the user accurately (e.g., "The """
        """temperature outside is [value from tool].").
For general knowledge questions not about the home: Answer truthfully from internal """
        """knowledge.
"""
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (f"""{first_part_prompt}
{area_prompt}
{no_timer_prompt}
{dynamic_context_prompt}
{stateless_exposed_entities_prompt}""")

    # Verify that the GetLiveContext tool returns the same results
    # as the exposed_entities_prompt
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="GetLiveContext", tool_args={})
    )
    assert result == {
        "success": True,
        "result": exposed_entities_prompt,
    }

    # Fake that request is made from a specific device ID with an area
    llm_context.device_id = device.id
    area_prompt = (
        "You are in area Test Area and all generic commands like 'turn on the lights' "
        "should target this area."
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (f"""{first_part_prompt}
{area_prompt}
{no_timer_prompt}
{dynamic_context_prompt}
{stateless_exposed_entities_prompt}""")

    # Add floor
    floor = floor_registry.async_create("2")
    area_registry.async_update(area.id, floor_id=floor.floor_id)
    area_prompt = (
        "You are in area Test Area (floor 2) and all generic commands like "
        "'turn on the lights' should target this area."
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (f"""{first_part_prompt}
{area_prompt}
{no_timer_prompt}
{dynamic_context_prompt}
{stateless_exposed_entities_prompt}""")

    # Register device for timers
    async_register_timer_handler(hass, device.id, lambda *args: None)

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    # The no_timer_prompt is gone
    assert api.api_prompt == (f"""{first_part_prompt}
{area_prompt}
{dynamic_context_prompt}
{stateless_exposed_entities_prompt}""")

    # Expose lock
    async_expose_entity(hass, "conversation", lock_entity.entity_id, True)
    stateless_exposed_entities_prompt += """lock.unnamed_device:
  names: Unnamed Device
  domain: lock
  areas: Test Area, Alternative name
"""

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (f"""{first_part_prompt}
{area_prompt}
{dynamic_context_prompt}
{lock_prompt}
{stateless_exposed_entities_prompt}""")

    options = mock_config_entry.options.copy()
    options[CONF_PROMPT_ENTITIES] = False
    hass.config_entries.async_update_entry(mock_config_entry, options=options)

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (f"""{first_part_prompt}
{area_prompt}""")
