"""Tests helpers."""

from unittest.mock import patch

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powerllm import DOMAIN

from .const import MOCK_CONFIG, MOCK_OPTIONS_CONFIG


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss
# persistent notifications. These calls would fail without this fixture since the
# persistent_notification integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield


@pytest.fixture
def mock_config_entry(hass):
    """Mock a config entry."""
    entry = MockConfigEntry(
        title="PowerLLM",
        domain=DOMAIN,
        data=MOCK_CONFIG,
        options=MOCK_OPTIONS_CONFIG,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def mock_init_component(hass, mock_config_entry):
    """Initialize integration."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
async def setup_ha(hass: HomeAssistant) -> None:
    """Set up Home Assistant."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "assist_pipeline", {})
    assert await async_setup_component(hass, "intent", {})
    assert await async_setup_component(hass, "script", {})


@pytest.fixture
def llm_context() -> llm.LLMContext:
    """Return tool input context."""
    return llm.LLMContext(
        platform="test_platform",
        context=Context(user_id="12345"),
        user_prompt=None,
        language=None,
        assistant=None,
        device_id=None,
    )


@pytest.fixture
async def async_call_tool(
    hass: HomeAssistant, llm_context: llm.LLMContext, mock_init_component
):
    """Get the tool call function."""

    api = await llm.async_get_api(hass, "powerllm", llm_context)

    async def _call_tool(name: str, **kwargs):
        tool_input = llm.ToolInput(
            tool_name=name,
            tool_args=kwargs,
        )

        return await api.async_call_tool(tool_input)

    return _call_tool
