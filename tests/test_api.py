"""Tests for PowerLLM as an API that complements Assist."""

from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.components.conversation.chat_log import ChatLog
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import intent, llm
from primp import BuilderError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.powerllm import llm_tool
from custom_components.powerllm.api import PowerLLMAPI
from custom_components.powerllm.const import (
    CONF_MEMORY_PROMPTS,
    CONF_REQUIRE_ADMIN,
    CONF_TOOL_SELECTION,
    DOMAIN,
)

from . import tool_result_data


@pytest.mark.usefixtures("mock_init_component")
async def test_powerllm_tools(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Expose extras without discovering arbitrary intents or duplicating Assist."""

    class CustomIntent(intent.IntentHandler):
        intent_type = "CustomIntent"

    intent.async_register(hass, CustomIntent())
    tools = PowerLLMAPI(hass, mock_config_entry)._async_get_tools(llm_context)
    assert all(tool.integration == DOMAIN for tool in tools)
    expected_metadata = {
        "HassGetState": (
            "Get entity states",
            llm.ToolAnnotations(
                read_only=True, destructive=False, idempotent=True, open_world=False
            ),
        ),
        "websearch": (
            "Search the web",
            llm.ToolAnnotations(
                read_only=True, destructive=False, idempotent=True, open_world=True
            ),
        ),
        "news": (
            "Search news",
            llm.ToolAnnotations(
                read_only=True, destructive=False, idempotent=True, open_world=True
            ),
        ),
        "memory": (
            "Remember a fact",
            llm.ToolAnnotations(
                read_only=False, destructive=False, idempotent=False, open_world=False
            ),
        ),
        "homeassistant_script": (
            "Run a Home Assistant script",
            llm.ToolAnnotations(
                read_only=False, destructive=True, idempotent=False, open_world=True
            ),
        ),
        "python_code_execute": ("Execute Python code", llm.ToolAnnotations()),
        "web_scrape": (
            "Read a web page",
            llm.ToolAnnotations(
                read_only=True, destructive=False, idempotent=True, open_world=True
            ),
        ),
    }
    assert {
        tool.name: (tool.title, tool.annotations)
        for tool in tools
        if tool.name in expected_metadata
    } == expected_metadata

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert {tool.name for tool in api.tools} == {
        "HassGetState",
        "homeassistant_script",
        "websearch",
        "news",
        "memory",
        "python_code_execute",
        "web_scrape",
    }
    assert not any(
        "without an integration" in record.message for record in caplog.records
    )


@pytest.mark.usefixtures("mock_init_component")
async def test_merged_api(hass: HomeAssistant, llm_context: llm.LLMContext) -> None:
    """Selecting both APIs merges prompts and dispatches tools to their owner."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)

    @llm_tool(hass)
    @callback
    def echo(value: str) -> dict[str, str]:
        """Echo a value."""
        return {"value": value}

    api = await llm.async_get_api(hass, ["assist", "powerllm"], llm_context)
    tools = {tool.name for tool in api.tools}
    assert "intent__HassTurnOn" in tools
    assert "llm__GetDateTime" in tools
    assert "HassGetState" in tools
    assert not any(tool.startswith("powerllm__") for tool in tools)
    powerllm_api = await llm.async_get_api(hass, "powerllm", llm_context)
    merged_tools = {tool.name: tool for tool in api.tools}
    for tool in powerllm_api.tools:
        merged_tool = merged_tools[tool.name]
        assert merged_tool.title == tool.title
        assert merged_tool.annotations == tool.annotations
        assert merged_tool.integration == tool.integration
    assert "Static Context:" in api.api_prompt
    assert "Entity IDs for scripts" in api.api_prompt
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="echo", tool_args={"value": "works"})
    )
    assert tool_result_data(result) == {"value": "works"}
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="llm__GetDateTime", tool_args={})
    )
    date_time = tool_result_data(result)
    assert set(date_time) == {"date", "time", "timezone", "weekday"}
    assert all(date_time.values())
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="HassGetState", tool_args={"name": "Kitchen"})
    )
    result = tool_result_data(result)
    assert result["data"]["matched_states"][0]["entity_id"] == "light.kitchen"


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("merged", [False, True])
@pytest.mark.parametrize("user", ["admin", "member", "missing", "anonymous", "unknown"])
async def test_administrator_api_access(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    hass_admin_user,
    user: str,
    merged: bool,
) -> None:
    """Enforce the configured permission through native single and merged APIs."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={**mock_config_entry.options, CONF_REQUIRE_ADMIN: True},
    )
    await hass.async_block_till_done()
    assert next(
        api for api in llm.async_get_apis(hass) if api.id == "powerllm"
    ).requires_admin

    context = None
    if user == "admin":
        context = Context(user_id=hass_admin_user.id)
    elif user == "member":
        account = await hass.auth.async_create_user("Member", group_ids=[GROUP_ID_USER])
        assert not account.is_admin
        context = Context(user_id=account.id)
    elif user == "anonymous":
        context = Context()
    elif user == "unknown":
        context = Context(user_id="missing-user")
    request_context = replace(llm_context, context=context)
    selection = ["assist", "powerllm"] if merged else "powerllm"

    if user == "admin":
        api = await llm.async_get_api(hass, selection, request_context)
        assert api.api.requires_admin
        assert "HassGetState" in {tool.name for tool in api.tools}
    else:
        with pytest.raises(Unauthorized):
            await llm.async_get_api(hass, selection, request_context)


@pytest.mark.usefixtures("mock_init_component")
async def test_merged_tool_collision(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    assist_api: llm.API,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conflicting names use stable API IDs and retain the correct dispatcher."""
    monkeypatch.setattr(assist_api, "name", "Renamed device API")

    @llm_tool(hass, title="Custom date tool")
    @callback
    def llm__GetDateTime(value: str) -> dict[str, str]:
        """Return the supplied value."""
        return {"value": value}

    api = await llm.async_get_api(hass, ["assist", "powerllm"], llm_context)
    tools = {tool.name: tool for tool in api.tools}
    assert "llm__GetDateTime" not in tools
    assert tools["powerllm__llm__GetDateTime"].title == "Custom date tool"
    assert tools["powerllm__llm__GetDateTime"].integration == DOMAIN
    assert "HassGetState" in tools

    result = await api.async_call_tool(
        llm.ToolInput(
            tool_name="powerllm__llm__GetDateTime", tool_args={"value": "custom"}
        )
    )
    assert tool_result_data(result) == {"value": "custom"}
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="assist__llm__GetDateTime", tool_args={})
    )
    assert set(tool_result_data(result)) == {"date", "time", "timezone", "weekday"}


@pytest.mark.usefixtures("mock_init_component")
async def test_merged_native_tool_deduplication(
    hass: HomeAssistant, llm_context: llm.LLMContext, hass_admin_user
) -> None:
    """Combine both native APIs and custom tools without duplicate shared tools."""
    context = replace(llm_context, context=Context(user_id=hass_admin_user.id))
    api = await llm.async_get_api(
        hass, ["assist", "homeassistant", "powerllm"], context
    )
    assert [tool.name for tool in api.tools].count("llm__GetDateTime") == 1
    assert not any(tool.name.endswith("__llm__GetDateTime") for tool in api.tools)
    assert "HassGetState" in {tool.name for tool in api.tools}
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="llm__GetDateTime", tool_args={})
    )
    assert set(tool_result_data(result)) == {"date", "time", "timezone", "weekday"}


@pytest.mark.usefixtures("mock_init_component")
async def test_conversation_reuses_tools_with_current_context(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Keep native prompt caching while using live context and entity exposure."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    hass.states.async_set("light.office", "off", {"friendly_name": "Office"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    async_expose_entity(hass, "conversation", "light.office", False)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_MEMORY_PROMPTS: {"User": {"12345": "Likes tea"}},
        },
    )

    @llm_tool(hass)
    @callback
    def request_context(context: Context, agent_id: str) -> dict[str, str]:
        """Return the context of the current turn."""
        return {"context_id": context.id, "agent_id": agent_id}

    first_context = replace(llm_context, agent_id="conversation.test")
    chat_log = ChatLog(hass, "powerllm-test")
    await chat_log.async_provide_llm_data(first_context, user_llm_hass_api="powerllm")
    api = chat_log.llm_api
    assert api is not None
    system_prompt = chat_log.content[0]
    assert "Likes tea" in system_prompt.content
    assert "light.kitchen" in system_prompt.content
    assert "light.office" not in system_prompt.content
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="request_context", tool_args={})
    )
    assert tool_result_data(result) == {
        "context_id": first_context.context.id,
        "agent_id": "conversation.test",
    }
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="memory", tool_args={"text": "Likes coffee"})
    )
    assert tool_result_data(result) == {"success": True}
    assert mock_config_entry.options[CONF_MEMORY_PROMPTS]["User"]["12345"] == (
        "Likes tea\nLikes coffee"
    )

    async_expose_entity(hass, "conversation", "light.kitchen", False)
    async_expose_entity(hass, "conversation", "light.office", True)
    second_context = replace(first_context, context=Context(user_id="12345"))
    await chat_log.async_provide_llm_data(second_context, user_llm_hass_api="powerllm")
    assert chat_log.llm_api is api
    assert chat_log.content[0] is system_prompt
    assert api.llm_context is second_context
    result = await api.async_call_tool(
        llm.ToolInput(tool_name="request_context", tool_args={})
    )
    assert tool_result_data(result) == {
        "context_id": second_context.context.id,
        "agent_id": "conversation.test",
    }
    with pytest.raises(ServiceValidationError, match="unexposed entity light.kitchen"):
        await api.async_call_tool(
            llm.ToolInput(
                tool_name="homeassistant_script",
                tool_args={
                    "script": "action: light.turn_on\ntarget:\n  entity_id: light.kitchen"
                },
            )
        )

    new_chat_log = ChatLog(hass, "powerllm-new-conversation")
    await new_chat_log.async_provide_llm_data(
        second_context, user_llm_hass_api="powerllm"
    )
    assert "Likes coffee" in new_chat_log.content[0].content
    assert "light.office" in new_chat_log.content[0].content
    assert "light.kitchen" not in new_chat_log.content[0].content


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("homeassistant_script", {"script": "event: powerllm_test"}),
        ("memory", {"text": "New fact"}),
    ],
)
async def test_write_tools_return_native_results(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    tool_name: str,
    args: dict,
) -> None:
    """Return native success data after script execution or a memory update."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_MEMORY_PROMPTS: {"User": {"12345": "Existing fact"}},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    tool = next(tool for tool in api.tools if tool.name == tool_name)

    result = await tool.async_call(
        hass, llm.ToolInput(tool_name=tool_name, tool_args=args), llm_context
    )

    assert tool_result_data(result) == {"success": True}
    if tool_name == "memory":
        assert mock_config_entry.options[CONF_MEMORY_PROMPTS] == {
            "User": {"12345": "Existing fact\nNew fact"}
        }


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("enabled", [True, False])
async def test_script_prompt_selection(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    enabled: bool,
) -> None:
    """Only the enabled script tool contributes the entity ID mapping."""
    hass.states.async_set(
        "light.kitchen", "on", {"friendly_name": "Kitchen", "brightness": 100}
    )
    hass.states.async_set("light.hidden", "off", {"friendly_name": "Hidden"})
    async_expose_entity(hass, "conversation", "light.kitchen", True)
    async_expose_entity(hass, "conversation", "light.hidden", False)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_TOOL_SELECTION: {"default": False, "homeassistant_script": enabled},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert api.api_prompt == (
        "Entity IDs for scripts (entity_id: name):\nlight.kitchen: Kitchen\n"
        if enabled
        else ""
    )
    assert [tool.name for tool in api.tools] == (
        ["homeassistant_script"] if enabled else []
    )


@pytest.mark.usefixtures("mock_init_component")
async def test_memory_prompt_without_entities(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Memory prompts remain available even when there are no exposed entities."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_MEMORY_PROMPTS: {"User": {"12345": "Likes tea"}},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert "Likes tea" in api.api_prompt
    assert "expose entities" not in api.api_prompt
    assert "Entity IDs for scripts" not in api.api_prompt


@pytest.mark.usefixtures("mock_init_component")
async def test_get_state_selection(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
) -> None:
    """State queries use the normal tool selector independently of retired options."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            "intent_entities": False,
            CONF_TOOL_SELECTION: {"default": False, "HassGetState": True},
        },
    )
    api = await llm.async_get_api(hass, "powerllm", llm_context)
    assert [tool.name for tool in api.tools] == ["HassGetState"]


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize("search_enabled", [True, False])
async def test_api_without_search_client(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    mock_config_entry: MockConfigEntry,
    search_enabled: bool,
) -> None:
    """Discover enabled tools independently of search-client initialization."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **mock_config_entry.options,
            CONF_TOOL_SELECTION: {
                "default": False,
                "HassGetState": True,
                "websearch": search_enabled,
                "news": search_enabled,
            },
        },
    )
    with patch(
        "custom_components.powerllm.tools.duckduckgo.DDGS",
        side_effect=BuilderError('Invalid impersonate: "chrome_109"'),
    ) as mock_ddgs:
        api = await llm.async_get_api(hass, "powerllm", llm_context)

    assert {tool.name for tool in api.tools} == (
        {"HassGetState", "websearch", "news"} if search_enabled else {"HassGetState"}
    )
    mock_ddgs.assert_not_called()
