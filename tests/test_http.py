"""Tests for LLM Tools HTTP API."""

import probatio as vol
import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm, selector
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.powerllm.llm_tools import (
    PowerLLMTool,
    async_register_tool,
    llm_tool,
)


@pytest.mark.usefixtures("mock_init_component")
async def test_http_api_list(hass_client: ClientSessionGenerator) -> None:
    """Both API owners remain available through HTTP."""
    client = await hass_client()
    response = await client.get("/api/powerllm")
    assert response.status == 200
    assert await response.json() == [
        {"name": "Assist", "id": "assist"},
        {"name": "PowerLLM", "id": "powerllm"},
    ]


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("method", ["get", "post"])
async def test_http_tool_list(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, method: str
) -> None:
    """Clients can fetch each API separately, with no duplicate control tools."""
    tool = PowerLLMTool()
    tool.name = "selector_tool"
    tool.description = "A tool with a Home Assistant selector."
    tool.parameters = vol.Schema(
        {
            vol.Required("entity_id"): selector.EntitySelector(),
            vol.Optional("count", default=5): vol.Coerce(int),
            vol.Optional("label"): vol.Maybe(str),
        }
    )
    async_register_tool(hass, tool)
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    client = await hass_client()
    response = await client.request(method, "/api/powerllm/powerllm")
    assert response.status == 200
    data = await response.json()
    tools = {tool["name"]: tool for tool in data["tools"]}
    assert "HassGetState" in tools
    assert "HassTurnOn" not in tools
    assert tools["HassGetState"]["parameters"]["properties"]["domain"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert tools["selector_tool"] == {
        "name": "selector_tool",
        "description": "A tool with a Home Assistant selector.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "format": "entity_id"},
                "count": {"type": "integer", "default": 5},
                "label": {"anyOf": [{"type": "null"}, {"type": "string"}]},
            },
            "required": ["entity_id"],
            "additionalProperties": False,
        },
    }
    assert "light.kitchen: Kitchen" in data["prompt"]

    response = await client.request(method, "/api/powerllm/assist")
    assert response.status == 200
    tools = {tool["name"] for tool in (await response.json())["tools"]}
    assert "intent__HassTurnOn" in tools
    assert "llm__GetDateTime" in tools
    assert "HassGetState" not in tools

    response = await client.request(method, "/api/powerllm/non-existent")
    assert response.status == 404


@pytest.mark.usefixtures("mock_init_component")
async def test_http_tool(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """HTTP state queries retain details and report invalid tools and arguments."""
    hass.states.async_set(
        "light.kitchen", "on", {"friendly_name": "Kitchen", "brightness": 100}
    )
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    client = await hass_client()
    response = await client.post(
        "/api/powerllm/powerllm/HassGetState",
        json={
            "language": "en",
            "tool_args": {"name": "Kitchen"},
        },
    )
    assert response.status == 200
    data = await response.json()
    assert data["data"]["matched_states"] == [
        {
            "entity_id": "light.kitchen",
            "name": "Kitchen",
            "state": "on",
            "last_changed": "0 seconds ago",
            "attributes": {"brightness": 100},
        }
    ]

    response = await client.post("/api/powerllm/assist/llm__GetDateTime")
    assert response.status == 200
    date_time = await response.json()
    if not hasattr(llm, "ToolResult"):
        assert date_time["success"] is True
        date_time = date_time["result"]
    assert set(date_time) == {"date", "time", "timezone", "weekday"}
    assert all(date_time.values())

    response = await client.post("/api/powerllm/non-existent/non-existent")
    assert response.status == 404
    response = await client.post("/api/powerllm/powerllm/HassTurnOn")
    assert response.status == 404
    response = await client.post(
        "/api/powerllm/powerllm/HassGetState",
        json={
            "tool_args": {"unexpected": "value"},
        },
    )
    assert response.status == 500
    assert (await response.json())["error"] == "MultipleInvalid"


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"value": 42}, "error": False},
        {"data": {"value": 42}, "error": "Tool-provided error"},
        [{"title": "Example", "href": "https://example.com"}],
    ],
)
async def test_http_tool_preserves_payload(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, payload
) -> None:
    """Preserve lists and dictionaries with keys also used by result containers."""

    @llm_tool(hass)
    @callback
    def payload_tool():
        """Return the tool's original JSON payload."""
        return payload

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/payload_tool")

    assert response.status == 200
    assert await response.json() == payload


@pytest.mark.skipif(not hasattr(llm, "ToolResult"), reason="Requires HA 2026.10")
@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("error", [False, True])
@pytest.mark.parametrize("payload", [{"data": {"value": 42}}, [{"value": 42}]])
async def test_http_native_tool_result(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    llm_context: llm.LLMContext,
    payload,
    error: bool,
) -> None:
    """Keep native result flags for HA callers and the existing HTTP data format."""

    @llm_tool(hass)
    @callback
    def native_result_tool():
        """Return a native Home Assistant result container."""
        return llm.ToolResult(data=payload, error=error)

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="native_result_tool", tool_args={})
    )
    assert isinstance(result, llm.ToolResult)
    assert result.data == payload
    assert result.error is error

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/native_result_tool")

    assert response.status == 200
    assert await response.json() == payload
