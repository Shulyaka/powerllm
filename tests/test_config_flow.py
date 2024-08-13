"""Test powerllm config flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.powerllm.const import CONF_PROMPT_ENTITIES, DOMAIN

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

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_OPTIONS_CONFIG
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
    options_flow = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    options = await hass.config_entries.options.async_configure(
        options_flow["flow_id"],
        {
            CONF_PROMPT_ENTITIES: False,
        },
    )
    await hass.async_block_till_done()
    assert options["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert options["data"][CONF_PROMPT_ENTITIES] is False
