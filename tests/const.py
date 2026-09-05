"""Constants for powerllm tests."""

from homeassistant.const import CONF_DEFAULT, CONF_NAME

from custom_components.powerllm.const import (
    CONF_DUCKDUCKGO_REGION,
    CONF_MEMORY_PROMPTS,
    CONF_SCRIPT_EXPOSED_ONLY,
    CONF_TOOL_SELECTION,
)

# Mock config data to be used across multiple tests
MOCK_CONFIG = {
    CONF_NAME: "PowerLLM",
}

MOCK_OPTIONS_CONFIG = {
    CONF_DUCKDUCKGO_REGION: "wt-wt",
    CONF_SCRIPT_EXPOSED_ONLY: True,
    CONF_MEMORY_PROMPTS: {},
    CONF_TOOL_SELECTION: {
        "HassGetState": True,
        "homeassistant_script": True,
        "memory": True,
        "news": True,
        "websearch": True,
        CONF_DEFAULT: True,
    },
}
