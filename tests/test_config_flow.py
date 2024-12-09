"""Test powerllm config flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_DEFAULT
from homeassistant.core import HomeAssistant

from custom_components.powerllm.const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_INTENT_ENTITIES,
    CONF_PROMPT_ENTITIES,
    CONF_SCRIPT_EXPOSED_ONLY,
    CONF_TOOL_SELECTION,
    DOMAIN,
)

from .const import MOCK_CONFIG, MOCK_OPTIONS_CONFIG


@pytest.fixture(autouse=True)
def bypass_setup_fixture():
    """Prevent setup."""
    with patch(
        "custom_components.powerllm.async_setup_entry",
        return_value=True,
    ):
        yield


def test_test(hass):
    """Workaround for https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/discussions/160."""


async def test_config_flow(hass: HomeAssistant):
    """Test a successful config flow."""
    # Init first step
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"

    # Advance to step 2
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "init"

    # Advance to step 3
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            k: v
            for k, v in MOCK_OPTIONS_CONFIG.items()
            if k not in {"memory_prompts", "tool_selection"}
        },
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "memory_prompts"

    # Advance to step 4
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_OPTIONS_CONFIG.get(result["step_id"], {})
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "tool_selection"

    # Final result
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_OPTIONS_CONFIG.get(result["step_id"], {})
    )

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "PowerLLM"
    assert result["data"] == MOCK_CONFIG
    assert result["options"] == MOCK_OPTIONS_CONFIG
    assert result["result"]


async def test_options_flow(
    hass: HomeAssistant, mock_config_entry, mock_init_component
) -> None:
    """Test a successful options flow."""
    options = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert options["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert options["step_id"] == "init"

    options = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            CONF_PROMPT_ENTITIES: False,
            CONF_INTENT_ENTITIES: False,
            CONF_DUCKDUCKGO_REGION: "us-en",
            CONF_SCRIPT_EXPOSED_ONLY: False,
        },
    )
    assert options["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert options["step_id"] == "memory_prompts"

    options = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {},
    )
    assert options["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert options["step_id"] == "tool_selection"

    options = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {"default": True},
    )
    assert options["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert options["data"][CONF_PROMPT_ENTITIES] is False
    assert options["data"][CONF_INTENT_ENTITIES] is False
    assert options["data"][CONF_DUCKDUCKGO_REGION] == "us-en"
    assert options["data"][CONF_SCRIPT_EXPOSED_ONLY] is False
    assert options["data"][CONF_TOOL_SELECTION][CONF_DEFAULT] is True
