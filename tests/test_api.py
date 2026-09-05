"""Tests for PowerLLM as an API that complements Assist."""

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent, llm
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powerllm import llm_tool
from custom_components.powerllm.const import CONF_MEMORY_PROMPTS, CONF_TOOL_SELECTION


@pytest.mark.usefixtures("mock_init_component")
async def test_powerllm_tools(hass: HomeAssistant, llm_context: llm.LLMContext) -> None:
    """Expose extras without discovering arbitrary intents or duplicating Assist."""

    class CustomIntent(intent.IntentHandler):
        intent_type = "CustomIntent"

    intent.async_register(hass, CustomIntent())
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert {tool.name for tool in api.tools} == {
        "HassGetState",
        "homeassistant_script",
        "websearch",
        "news",
        "memory",
        "python_code_execute",
        "web_scrape",
    }


@pytest.mark.usefixtures("mock_init_component")
async def test_merged_api(hass: HomeAssistant, llm_context: llm.LLMContext) -> None:
    """Selecting both APIs merges prompts and dispatches tools to their owner."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)

    @llm_tool(hass)
    @callback
    def echo(value: str) -> dict[str, str]:
        """Echo a value."""
        return {"value": value}

    api = await llm.async_get_api(hass, ["assist", "powerllm"], llm_context)
    tools = {tool.name for tool in api.tools}
    assert "assist__HassTurnOn" in tools
    assert "assist__GetDateTime" in tools
    assert "powerllm__HassGetState" in tools
    assert "powerllm__HassTurnOn" not in tools
    assert "Static Context:" in api.api_prompt
    assert "Entity IDs for scripts" in api.api_prompt
    assert await api.async_call_tool(
        llm.ToolInput(tool_name="powerllm__echo", tool_args={"value": "works"})
    ) == {"value": "works"}
    assert (
        await api.async_call_tool(
            llm.ToolInput(tool_name="assist__GetDateTime", tool_args={})
        )
    )["success"] is True
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="powerllm__HassGetState", tool_args={"name": "Kitchen"})
    )
    assert result["data"]["matched_states"][0]["entity_id"] == "light.kitchen"


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("enabled", [True, False])
async def test_script_prompt_selection(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    enabled: bool,
) -> None:
    """Only the enabled script tool contributes the entity ID mapping."""
    hass.states.async_set(
        "light.kitchen", "on", {"friendly_name": "Kitchen", "brightness": 100}
    )
    hass.states.async_set("light.hidden", "off", {"friendly_name": "Hidden"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    async_expose_entity(hass, "conversation", "light.hidden", False)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_TOOL_SELECTION: {"default": False, "homeassistant_script": enabled},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (
        "Entity IDs for scripts (entity_id: name):\nlight.kitchen: Kitchen\n"
        if enabled
        else ""
    )
    assert [tool.name for tool in api.tools] == (
        ["homeassistant_script"] if enabled else []
    )


@pytest.mark.usefixtures("mock_init_component")
async def test_memory_prompt_without_entities(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Memory prompts remain available even when there are no exposed entities."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_MEMORY_PROMPTS: {"User": {"12345": "Likes tea"}},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert "Likes tea" in api.api_prompt
    assert "expose entities" not in api.api_prompt
    assert "Entity IDs for scripts" not in api.api_prompt


@pytest.mark.usefixtures("mock_init_component")
async def test_get_state_selection(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
) -> None:
    """State queries use the normal tool selector independently of retired options."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            "intent_entities": False,
            CONF_TOOL_SELECTION: {"default": False, "HassGetState": True},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert [tool.name for tool in api.tools] == ["HassGetState"]
