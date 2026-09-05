"""Tests for the entity ID mapping contributed by the script tool."""

import pytest
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.llm import LLMContext
from homeassistant.util.yaml import parse_yaml

from custom_components.powerllm.tools.script import DynamicScriptTool


@pytest.mark.parametrize("exposed_only", [True, False])
async def test_entity_mapping(
    hass: HomeAssistant, llm_context: LLMContext, exposed_only: bool
) -> None:
    """Preserve duplicate names and only disclose exposed identities, without states."""
    hass.states.async_set(
        "light.first", "on", {"friendly_name": "Lamp", "brightness": 100}
    )
    hass.states.async_set("light.second", "off", {"friendly_name": "Lamp"})
    hass.states.async_set("calendar.events", "off", {"friendly_name": "Calendar"})
    hass.states.async_set("script.evening", "off", {"friendly_name": "Evening"})
    hass.states.async_set("light.hidden", "on", {"friendly_name": "Hidden"})
    for entity_id in (
        "light.first",
        "light.second",
        "calendar.events",
        "script.evening",
    ):
        async_expose_entity(hass, "conversation", entity_id, True)
    async_expose_entity(hass, "conversation", "light.hidden", False)
    prompt = DynamicScriptTool(exposed_only).prompt(hass, llm_context)
    assert parse_yaml(prompt.split("\n", 1)[1]) == {
        "light.first": "Lamp",
        "light.second": "Lamp",
        "calendar.events": "Calendar",
        "script.evening": "Evening",
    }
