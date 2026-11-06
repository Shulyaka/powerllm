"""PowerLLM tools served through Home Assistant's native MCP API."""

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.components.mcp_server.server import async_get_api_instance
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from pytest_homeassistant.common import MockConfigEntry

from custom_components.powerllm.const import CONF_TOOL_SELECTION


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("read_only", [False, True])
async def test_mcp_tool_selection(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    read_only: bool,
) -> None:
    """Native MCP filtering respects annotations and PowerLLM tool selection."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_TOOL_SELECTION: {
                **mock_config_entry.options[CONF_TOOL_SELECTION],
                "news": False,
            },
        },
    )

    api = await async_get_api_instance(hass, "powerllm", llm_context, read_only)

    read_tools = {"HassGetState", "websearch", "web_scrape"}
    write_tools = {"memory", "homeassistant_script", "python_code_execute"}
    assert {tool.name for tool in api.tools} == (
        read_tools if read_only else read_tools | write_tools
    )
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="HassGetState", tool_args={"name": "Kitchen"})
    )
    assert result.data["data"]["matched_states"][0]["entity_id"] == "light.kitchen"

    if read_only:
        for tool_name in write_tools:
            with pytest.raises(HomeAssistantError, match="not found"):
                await api.async_call_tool(
                    llm.ToolInput(tool_name=tool_name, tool_args={})
                )
