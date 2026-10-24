"""Tests for DuckDuckGo search tools."""

from copy import deepcopy
from threading import get_ident
from unittest.mock import MagicMock, patch

import pytest
from ddgs.exceptions import DDGSException
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.llm import LLMContext, ToolAnnotations, ToolInput, ToolResult
from primp import BuilderError

from custom_components.powerllm.llm_tools import async_register_tool
from custom_components.powerllm.tools.duckduckgo import DDGNewsTool, DDGTextSearchTool

SEARCH_TOOLS = [
    (DDGTextSearchTool, "text", "query"),
    (DDGNewsTool, "news", "keywords"),
]


@pytest.mark.parametrize("tool_type", [DDGTextSearchTool, DDGNewsTool])
async def test_tool_metadata_without_client(hass: HomeAssistant, tool_type) -> None:
    """Preserve registered metadata when copying tools without an HTTP client."""
    annotations = ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
    with patch(
        "custom_components.powerllm.tools.duckduckgo.DDGS",
        side_effect=BuilderError('Invalid impersonate: "chrome_109"'),
    ) as mock_ddgs:
        tool = tool_type("us-en")
        async_register_tool(hass, tool, title="Custom search", annotations=annotations)
        tool.integration = "custom_provider"
        copied = deepcopy(tool)

    mock_ddgs.assert_not_called()
    assert copied is not tool
    assert copied.name == tool.name
    assert copied.title == "Custom search"
    assert copied.annotations == annotations
    assert copied.integration == "custom_provider"
    assert copied._region == "us-en"


@pytest.mark.parametrize(("tool_type", "method", "query_arg"), SEARCH_TOOLS)
@pytest.mark.parametrize("results", [[{"title": "Example"}], []])
async def test_search(
    hass: HomeAssistant,
    llm_context: LLMContext,
    tool_type,
    method: str,
    query_arg: str,
    results: list[dict[str, str]],
) -> None:
    """Create clients and search in the executor, preserving arguments and results."""
    event_loop_thread = get_ident()
    client = MagicMock()

    def search(*args, **kwargs):
        assert get_ident() != event_loop_thread
        return results

    getattr(client, method).side_effect = search

    def create_client():
        assert get_ident() != event_loop_thread
        return client

    tool = tool_type("us-en")
    with patch(
        "custom_components.powerllm.tools.duckduckgo.DDGS", side_effect=create_client
    ) as mock_ddgs:
        response = await tool.async_call(
            hass,
            ToolInput(
                tool_name=tool.name,
                tool_args={query_arg: "Home Assistant", "max_results": 3},
            ),
            llm_context,
        )

    mock_ddgs.assert_called_once_with()
    getattr(client, method).assert_called_once_with(
        "Home Assistant", region="us-en", max_results=3, backend="duckduckgo"
    )
    assert isinstance(response, ToolResult)
    assert response.error is False
    assert response.data == {"results": results}


@pytest.mark.parametrize(("tool_type", "method", "query_arg"), SEARCH_TOOLS)
@pytest.mark.parametrize("during_init", [True, False])
@pytest.mark.parametrize("error_type", [DDGSException, BuilderError])
async def test_search_error(
    hass: HomeAssistant,
    llm_context: LLMContext,
    tool_type,
    method: str,
    query_arg: str,
    during_init: bool,
    error_type,
) -> None:
    """Translate client initialization and search failures into tool errors."""
    error = error_type("Search client failed")
    tool = tool_type()
    with patch("custom_components.powerllm.tools.duckduckgo.DDGS") as mock_ddgs:
        if during_init:
            mock_ddgs.side_effect = error
        else:
            getattr(mock_ddgs.return_value, method).side_effect = error

        with pytest.raises(HomeAssistantError, match="Search client failed") as raised:
            await tool.async_call(
                hass,
                ToolInput(tool_name=tool.name, tool_args={query_arg: "Home Assistant"}),
                llm_context,
            )

    assert raised.value.__cause__ is error
