"""Tests for LLM Tools HTTP API."""

from unittest.mock import patch

import probatio as vol
import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError, Unauthorized, UnknownUser
from homeassistant.helpers import llm, selector
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.powerllm.http import async_llm_tools_json
from custom_components.powerllm.llm_tools import (
    PowerLLMTool,
    async_register_tool,
    llm_tool,
)


@pytest.mark.usefixtures("mock_init_component")
async def test_http_api_list(
    hass_client: ClientSessionGenerator, assist_api: llm.API
) -> None:
    """Both API owners remain available through HTTP."""
    client = await hass_client()
    response = await client.get("/api/powerllm")
    assert response.status == 200
    assert await response.json() == [
        {"name": assist_api.name, "id": "assist"},
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
    tool.title = "Select an entity"
    tool.integration = "external_provider"
    tool.annotations = llm.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
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
        "title": "Select an entity",
        "integration": "external_provider",
        "annotations": {
            "read_only": True,
            "destructive": False,
            "idempotent": True,
            "open_world": False,
        },
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
@pytest.mark.parametrize("method", ["get", "post"])
async def test_http_tool_default_metadata(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, method: str
) -> None:
    """Keep untitled custom tools and export all conservative annotation defaults."""
    tool = PowerLLMTool()
    tool.name = "untitled_tool"
    async_register_tool(hass, tool)
    client = await hass_client()

    response = await client.request(method, "/api/powerllm/powerllm")

    assert response.status == 200
    tools = {tool["name"]: tool for tool in (await response.json())["tools"]}
    assert tools["untitled_tool"] == {
        "name": "untitled_tool",
        "integration": "powerllm",
        "annotations": {
            "read_only": False,
            "destructive": True,
            "idempotent": False,
            "open_world": True,
        },
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    }


@pytest.mark.usefixtures("mock_init_component")
async def test_merged_tool_metadata(
    hass: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Serialize the original provider metadata after HA namespaces merged tools."""
    tool = PowerLLMTool()
    tool.name = "external_tool"
    tool.title = "External query"
    tool.integration = "external_provider"
    tool.annotations = llm.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=True
    )
    async_register_tool(hass, tool)
    api = await llm.async_get_api(hass, ["assist", "powerllm"], llm_context)

    tools = {tool["name"]: tool for tool in async_llm_tools_json(api)}

    assert tools["powerllm__external_tool"] == {
        "name": "powerllm__external_tool",
        "title": "External query",
        "integration": "external_provider",
        "annotations": {
            "read_only": True,
            "destructive": False,
            "idempotent": True,
            "open_world": True,
        },
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    }


@pytest.mark.usefixtures("mock_init_component")
async def test_http_tool(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, freezer
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
    ("payload", "expected"),
    [
        (
            {"data": {"value": 42}, "error": False},
            {"data": {"value": 42}, "error": False},
        ),
        (
            {"data": {"value": 42}, "error": "Tool-provided error"},
            {"data": {"value": 42}, "error": "Tool-provided error"},
        ),
        (
            [{"title": "Example", "href": "https://example.com"}],
            {"result": [{"title": "Example", "href": "https://example.com"}]},
        ),
        (42, {"result": 42}),
        (False, {"result": False}),
        (None, {"result": None}),
    ],
)
async def test_http_tool_preserves_payload(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, payload, expected: dict
) -> None:
    """Keep dictionary data intact and expose normalized non-object results."""

    @llm_tool(hass)
    @callback
    def payload_tool():
        """Return the tool's original JSON payload."""
        return payload

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/payload_tool")

    assert response.status == 200
    assert await response.json() == expected


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize(
    ("error", "error_type", "error_text"),
    [
        (
            ValueError("Invalid operation"),
            "HomeAssistantError",
            "Error calling failing_tool (ValueError): Invalid operation",
        ),
        (
            ServiceValidationError("Service rejected"),
            "ServiceValidationError",
            "Service rejected",
        ),
    ],
)
async def test_http_function_tool_error(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    error: Exception,
    error_type: str,
    error_text: str,
) -> None:
    """Report raised function errors with a failed HTTP response."""

    @llm_tool(hass)
    @callback
    def failing_tool():
        raise error

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/failing_tool")

    assert response.status == 500
    assert await response.json() == {"error": error_type, "error_text": error_text}


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("error", [False, True])
@pytest.mark.parametrize(
    "payload", [{"data": {"value": 42}}, {"results": [{"value": 42}]}]
)
async def test_http_native_tool_result(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    llm_context: llm.LLMContext,
    payload,
    error: bool,
) -> None:
    """Keep native result flags for HA callers and the existing HTTP data format."""

    native_result = llm.ToolResult(data=payload, error=error)

    @llm_tool(hass)
    @callback
    def native_result_tool():
        """Return a native Home Assistant result container."""
        return native_result

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="native_result_tool", tool_args={})
    )
    assert result is native_result
    assert result.data == payload
    assert result.error is error

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/native_result_tool")

    assert response.status == 200
    assert await response.json() == payload


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/powerllm/powerllm"),
        ("post", "/api/powerllm/powerllm"),
        ("post", "/api/powerllm/powerllm/private_tool"),
    ],
)
@pytest.mark.parametrize("error_type", [Unauthorized, UnknownUser])
async def test_http_api_permission_error(
    hass_client: ClientSessionGenerator, method: str, path: str, error_type
) -> None:
    """Return forbidden when API access fails, preserving each response format."""
    error = error_type()
    client = await hass_client()
    with patch("custom_components.powerllm.http.llm.async_get_api", side_effect=error):
        response = await client.request(method, path)

    assert response.status == 403
    if path.endswith("/private_tool"):
        assert await response.json() == {
            "error": error_type.__name__,
            "error_text": str(error),
        }
    else:
        assert await response.json() == {"message": str(error)}


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("error_type", [Unauthorized, UnknownUser])
async def test_http_function_permission_error(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, error_type
) -> None:
    """Keep permission exceptions raised by registered functions as forbidden."""

    @llm_tool(hass)
    @callback
    def private_tool():
        raise error_type()

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/private_tool")

    assert response.status == 403
    assert await response.json() == {
        "error": error_type.__name__,
        "error_text": error_type.__name__,
    }


@pytest.mark.usefixtures("mock_init_component")
async def test_http_permission_error_before_not_found(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Use exception type before interpreting the text of a permission failure."""

    class MissingPrivateResource(Unauthorized):
        """Permission failure whose message resembles a missing API."""

        def __str__(self) -> str:
            return "Private resource not found"

    @llm_tool(hass)
    @callback
    def private_tool():
        raise MissingPrivateResource()

    client = await hass_client()
    response = await client.post("/api/powerllm/powerllm/private_tool")

    assert response.status == 403
    assert (await response.json())["error_text"] == "Private resource not found"
