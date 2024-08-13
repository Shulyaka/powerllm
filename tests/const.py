"""Constants for powerllm tests."""

from homeassistant.const import CONF_NAME

from custom_components.powerllm.const import (
    CONF_INTENT_ENTITIES,
    CONF_PROMPT_ENTITIES,
    CONF_SCRIPT_EXPOSED_ONLY,
)

# Mock config data to be used across multiple tests
MOCK_CONFIG = {
    CONF_NAME: "PowerLLM",
}

MOCK_OPTIONS_CONFIG = {
    CONF_PROMPT_ENTITIES: True,
    CONF_INTENT_ENTITIES: True,
    CONF_SCRIPT_EXPOSED_ONLY: True,
}
