"""Tests for PowerLLM config entry lifecycle."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import llm
from pytest_homeassistant.common import MockConfigEntry

from custom_components.powerllm.const import CONF_REQUIRE_ADMIN, DOMAIN


@pytest.mark.usefixtures("mock_init_component")
async def test_unload_and_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    llm_context: llm.LLMContext,
) -> None:
    """Unload only the entry's API and allow it to be set up again."""
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Other API",
        data={CONF_NAME: "Other API"},
        options=dict(mock_config_entry.options),
    )
    other_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other_entry.entry_id)
    other_api = (await llm.async_get_api(hass, "other_api", llm_context)).api
    assist_api = (await llm.async_get_api(hass, "assist", llm_context)).api

    for _ in range(2):
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
        with pytest.raises(HomeAssistantError, match="API powerllm not found"):
            await llm.async_get_api(hass, "powerllm", llm_context)
        assert (
            await llm.async_get_api(hass, "other_api", llm_context)
        ).api is other_api
        assert (await llm.async_get_api(hass, "assist", llm_context)).api is assist_api

        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        assert mock_config_entry.state is ConfigEntryState.LOADED
        assert (await llm.async_get_api(hass, "powerllm", llm_context)).tools


@pytest.mark.usefixtures("mock_init_component")
async def test_reload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    llm_context: llm.LLMContext,
) -> None:
    """Reload replaces the API registration without a duplicate-ID error."""
    original_api = (await llm.async_get_api(hass, "powerllm", llm_context)).api

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api is not original_api
    assert api.tools
    assert sum(api.id == "powerllm" for api in llm.async_get_apis(hass)) == 1


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("require_admin", [None, False, True])
async def test_reload_preserves_admin_option(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    llm_context: llm.LLMContext,
    require_admin: bool | None,
) -> None:
    """Restore saved permissions on setup and preserve access for legacy entries."""
    options = dict(mock_config_entry.options)
    if require_admin is None:
        options.pop(CONF_REQUIRE_ADMIN)
    else:
        options[CONF_REQUIRE_ADMIN] = require_admin
    hass.config_entries.async_update_entry(mock_config_entry, options=options)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)

    api = next(api for api in llm.async_get_apis(hass) if api.id == "powerllm")
    assert api.requires_admin is bool(require_admin)
    if require_admin:
        with pytest.raises(Unauthorized):
            await llm.async_get_api(hass, "powerllm", llm_context)
    else:
        assert (await llm.async_get_api(hass, "powerllm", llm_context)).api is api


@pytest.mark.usefixtures("mock_init_component")
async def test_remove_and_readd_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    llm_context: llm.LLMContext,
) -> None:
    """Removing an entry releases its API name without requiring a restart."""
    result = await hass.config_entries.async_remove(mock_config_entry.entry_id)

    assert result == {"require_restart": False}
    with pytest.raises(HomeAssistantError, match="API powerllm not found"):
        await llm.async_get_api(hass, "powerllm", llm_context)

    replacement = MockConfigEntry(
        domain=DOMAIN,
        title=mock_config_entry.title,
        data=dict(mock_config_entry.data),
        options=dict(mock_config_entry.options),
    )
    replacement.add_to_hass(hass)
    assert await hass.config_entries.async_setup(replacement.entry_id)
    assert replacement.state is ConfigEntryState.LOADED
    assert (await llm.async_get_api(hass, "powerllm", llm_context)).tools
