"""Tests for LLM Tools HTTP API."""

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


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
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    client = await hass_client()
    response = await client.request(method, "/api/powerllm/powerllm")
    assert response.status == 200
    data = await response.json()
    tools = {tool["name"]: tool for tool in data["tools"]}
    assert "HassGetState" in tools
    assert "HassTurnOn" not in tools
    assert "domain" in tools["HassGetState"]["parameters"]["properties"]
    assert "light.kitchen: Kitchen" in data["prompt"]

    response = await client.request(method, "/api/powerllm/assist")
    assert response.status == 200
    tools = {tool["name"] for tool in (await response.json())["tools"]}
    assert "HassTurnOn" in tools
    assert "GetDateTime" in tools
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

    response = await client.post("/api/powerllm/assist/GetDateTime")
    assert response.status == 200
    assert (await response.json())["success"] is True

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
