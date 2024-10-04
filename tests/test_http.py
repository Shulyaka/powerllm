"""Tests for LLM Tools HTTP API."""

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, intent
from pytest_homeassistant_custom_component.common import MockUser
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


async def test_http_api_list(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_init_component,
) -> None:
    """Test LLM API list via HTTP API."""
    client = await hass_client()
    resp = await client.get("/api/powerllm")

    assert resp.status == 200
    data = await resp.json()

    assert data == [
        {"name": "Assist", "id": "assist"},
        {"name": "PowerLLM", "id": "powerllm"},
    ]


async def test_http_tool_list(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    snapshot: SnapshotAssertion,
    mock_init_component,
) -> None:
    """Test LLM Tool list via HTTP API."""

    class TestIntentHandler(intent.IntentHandler):
        """Test Intent Handler."""

        intent_type = "OrderBeer"
        description = "Orders beer"

        @property
        def slot_schema(self) -> dict | None:
            """Return a slot schema."""
            return {vol.Required("type"): cv.string}

        async def async_handle(self, intent):
            """Handle the intent."""
            assert intent.context.user_id == hass_admin_user.id
            response = intent.create_response()
            response.async_set_speech(
                f"I've ordered a {intent.slots['type']['value']}!"
            )
            response.async_set_card(
                "Beer ordered", f"You chose a {intent.slots['type']['value']}."
            )
            return response

    intent.async_register(hass, TestIntentHandler())

    client = await hass_client()
    resp = await client.get("/api/powerllm/assist")

    assert resp.status == 200
    data = await resp.json()

    data["tools"][0]["parameters"]["properties"]["device_class"]["items"]["enum"].sort()
    data["tools"][1]["parameters"]["properties"]["device_class"]["items"]["enum"].sort()
    assert data == snapshot

    resp = await client.get("/api/powerllm/non-existent")
    assert resp.status == 404


async def test_http_tool(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_init_component,
) -> None:
    """Test LLM Tool via HTTP API."""

    class TestIntentHandler(intent.IntentHandler):
        """Test Intent Handler."""

        intent_type = "OrderBeer"
        description = "Orders beer"

        @property
        def slot_schema(self) -> dict | None:
            """Return a slot schema."""
            return {vol.Required("type"): cv.string}

        async def async_handle(self, intent):
            """Handle the intent."""
            assert intent.context.user_id == hass_admin_user.id
            response = intent.create_response()
            response.async_set_speech(
                f"I've ordered a {intent.slots['type']['value']}!"
            )
            response.async_set_card(
                "Beer ordered", f"You chose a {intent.slots['type']['value']}."
            )
            return response

    intent.async_register(hass, TestIntentHandler())

    client = await hass_client()
    resp = await client.post(
        "/api/powerllm/assist/OrderBeer",
        json={
            "user_input": "I wish beer",
            "language": "en",
            "device_id": "12345",
            "tool_args": {"type": "Lager"},
        },
    )

    assert resp.status == 200
    data = await resp.json()

    assert data == {
        "data": {
            "failed": [],
            "success": [],
            "targets": [],
        },
        "response_type": "action_done",
        "speech": {
            "plain": {
                "extra_data": None,
                "speech": "I've ordered a Lager!",
            },
        },
    }

    resp = await client.post("/api/powerllm/non-existent/non-existent")
    assert resp.status == 404

    resp = await client.post("/api/powerllm/assist/non-existent")
    assert resp.status == 404

    resp = await client.post("/api/powerllm/assist/OrderBeer")

    assert resp.status == 500
    data = await resp.json()

    assert data == {
        "error": "MultipleInvalid",
        "error_text": "required key not provided @ data['type']",
    }
