"""Constants for powerllm tests."""

from homeassistant.const import CONF_NAME

from custom_components.powerllm.const import CONF_PROMPT_ENTITIES

# Mock config data to be used across multiple tests
MOCK_CONFIG = {
    CONF_NAME: "PowerLLM",
}

MOCK_OPTIONS_CONFIG = {
    CONF_PROMPT_ENTITIES: True,
}
