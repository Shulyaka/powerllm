"""Validate model arguments on real tool execution paths."""

from unittest.mock import Mock, patch

import probatio as vol
import pytest
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.powerllm.llm_tools import PowerFunctionTool, async_register_tool

from . import tool_result_data


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("merged", [False, True])
@pytest.mark.parametrize("execution", ["executor", "callback", "async"])
@pytest.mark.parametrize(
    "args",
    [
        {},
        {"value": "bad"},
        {"value": 1, "unexpected": True},
        {"value": 1, "hass": "fake"},
    ],
)
async def test_function_rejects_invalid_arguments(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    merged: bool,
    execution: str,
    args: dict,
) -> None:
    """Reject invalid inputs before every function dispatch, including merged APIs."""
    calls = Mock()

    def checked(value: int, hass: HomeAssistant):
        calls(value, hass)
        return {}

    async def async_checked(value: int, hass: HomeAssistant):
        return checked(value, hass)

    if execution == "async":
        function = async_checked
    elif execution == "callback":
        function = callback(checked)
    else:
        function = checked
    tool = PowerFunctionTool(function)
    async_register_tool(hass, tool)
    api = await llm.async_get_api(
        hass, ["assist", "powerllm"] if merged else "powerllm", llm_context
    )
    tool_input = llm.ToolInput(
        tool_name=f"powerllm__{tool.name}" if merged else tool.name,
        tool_args=args.copy(),
    )

    with pytest.raises(vol.Invalid):
        await api.async_call_tool(tool_input)

    calls.assert_not_called()
    assert tool_input.tool_args == args


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("merged", [False, True])
async def test_function_uses_validated_arguments(
    hass: HomeAssistant, llm_context: llm.LLMContext, merged: bool
) -> None:
    """Pass converted values, defaults and trusted context without changing input."""
    calls = Mock()

    @callback
    def checked(
        value: int, hass: HomeAssistant, llm_context: llm.LLMContext, count: int = 2
    ):
        calls(value, hass, llm_context, count)
        return {"value": value, "count": count}

    tool = PowerFunctionTool(checked)
    tool.parameters = vol.Schema(
        {vol.Required("value"): vol.Coerce(int), vol.Optional("count", default=2): int}
    )
    async_register_tool(hass, tool)
    api = await llm.async_get_api(
        hass, ["assist", "powerllm"] if merged else "powerllm", llm_context
    )
    tool_input = llm.ToolInput(
        tool_name="powerllm__checked" if merged else "checked",
        tool_args={"value": "3"},
    )

    result = await api.async_call_tool(tool_input)

    assert tool_result_data(result) == {"value": 3, "count": 2}
    calls.assert_called_once_with(3, hass, llm_context, 2)
    assert tool_input.tool_args == {"value": "3"}


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("merged", [False, True])
@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("websearch", {"query": []}),
        ("news", {}),
        ("homeassistant_script", {"script": {}}),
        ("memory", {"text": []}),
        ("python_code_execute", {"source": []}),
        ("web_scrape", {"url": []}),
        ("HassGetState", {"unexpected": True}),
    ],
)
async def test_builtin_rejects_invalid_arguments(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry,
    merged: bool,
    tool_name: str,
    args: dict,
) -> None:
    """Validate built-ins before network requests, scripts or memory updates."""
    api = await llm.async_get_api(
        hass, ["assist", "powerllm"] if merged else "powerllm", llm_context
    )
    options = mock_config_entry.options
    with (
        patch("custom_components.powerllm.tools.duckduckgo.DDGS") as search,
        patch("custom_components.powerllm.tools.script.Script") as script,
        patch(
            "custom_components.powerllm.tools.web_scrape.trafilatura.fetch_response"
        ) as fetch,
        pytest.raises(vol.Invalid),
    ):
        await api.async_call_tool(
            llm.ToolInput(
                tool_name=f"powerllm__{tool_name}" if merged else tool_name,
                tool_args=args,
            )
        )

    search.assert_not_called()
    script.assert_not_called()
    fetch.assert_not_called()
    assert mock_config_entry.options == options


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("merged", [False, True])
@pytest.mark.parametrize(
    ("tool_name", "method", "query_arg"),
    [("websearch", "text", "query"), ("news", "news", "keywords")],
)
@pytest.mark.parametrize(
    ("extra_args", "expected_count"), [({}, 5), ({"max_results": "3"}, 3)]
)
async def test_search_uses_schema_defaults_and_conversions(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    merged: bool,
    tool_name: str,
    method: str,
    query_arg: str,
    extra_args: dict,
    expected_count: int,
) -> None:
    """Honor advertised result limits on direct and merged search calls."""
    api = await llm.async_get_api(
        hass, ["assist", "powerllm"] if merged else "powerllm", llm_context
    )
    tool_input = llm.ToolInput(
        tool_name=f"powerllm__{tool_name}" if merged else tool_name,
        tool_args={query_arg: "Home Assistant", **extra_args},
    )
    with patch("custom_components.powerllm.tools.duckduckgo.DDGS") as search:
        getattr(search.return_value, method).return_value = [{"title": "Example"}]
        result = await api.async_call_tool(tool_input)

    getattr(search.return_value, method).assert_called_once_with(
        "Home Assistant",
        region="wt-wt",
        max_results=expected_count,
        backend="duckduckgo",
    )
    assert tool_result_data(result) == {"results": [{"title": "Example"}]}
    assert tool_input.tool_args == {query_arg: "Home Assistant", **extra_args}


@pytest.mark.usefixtures("mock_init_component")
async def test_http_rejects_invalid_function_arguments(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """Surface schema failures through the existing HTTP error path."""
    calls = Mock()

    @callback
    def checked(value: int):
        calls(value)
        return {}

    async_register_tool(hass, checked)
    client = await hass_client()
    response = await client.post(
        "/api/powerllm/powerllm/checked", json={"tool_args": {"value": "bad"}}
    )

    assert response.status == 500
    assert (await response.json())["error"] == "MultipleInvalid"
    calls.assert_not_called()
