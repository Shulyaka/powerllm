"""Metadata registration for function and class tools."""

from unittest.mock import Mock

import pytest
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm

from custom_components.powerllm import llm_tools
from custom_components.powerllm.const import DOMAIN

from . import tool_result_data

READ_ANNOTATIONS = llm.ToolAnnotations(
    read_only=True, destructive=False, idempotent=True, open_world=False
)


@pytest.mark.usefixtures("mock_init_component")
@pytest.mark.parametrize(
    "registration", ["constructor", "direct", "immediate", "deferred", "late_deferred"]
)
async def test_function_metadata_registration(
    hass: HomeAssistant,
    llm_context: llm.LLMContext,
    monkeypatch: pytest.MonkeyPatch,
    registration: str,
) -> None:
    """Retain metadata, identity, schema and execution on every registration path."""
    monkeypatch.setattr(llm_tools, "HASS_LIST", [])
    monkeypatch.setattr(llm_tools, "LLM_TOOL_LIST", [])
    calls = Mock()

    @callback
    def metadata_tool(
        value: int, hass: HomeAssistant, llm_context: llm.LLMContext, count: int = 2
    ):
        """Multiply a value."""
        calls(value, hass, llm_context, count)
        return {"value": value * count}

    metadata_tool.__module__ = "custom_components.external_provider.tools"
    options = {"title": "Multiply a value", "annotations": READ_ANNOTATIONS}
    if registration == "constructor":
        tool = llm_tools.PowerFunctionTool(metadata_tool, **options)
        llm_tools.async_register_tool(hass, tool)
    elif registration == "direct":
        llm_tools.async_register_tool(hass, metadata_tool, **options)
    elif registration == "immediate":
        assert llm_tools.llm_tool(hass, **options)(metadata_tool) is metadata_tool
    else:
        if registration == "late_deferred":
            llm_tools.deferred_register_tools(hass)
        assert llm_tools.llm_tool(**options)(metadata_tool) is metadata_tool
        if registration == "deferred":
            assert "metadata_tool" not in hass.data[DOMAIN]
            llm_tools.deferred_register_tools(hass)

    api = await llm.async_get_api(hass, "powerllm", llm_context)
    tool = next(tool for tool in api.tools if tool.name == "metadata_tool")
    assert tool.function is metadata_tool
    assert tool.title == "Multiply a value"
    assert tool.annotations is READ_ANNOTATIONS
    assert tool.integration == "external_provider"
    assert tool.description == "Multiply a value."
    assert tool.parameters({"value": 3}) == {"value": 3, "count": 2}

    result = await api.async_call_tool(
        llm.ToolInput(tool_name="metadata_tool", tool_args={"value": 3})
    )

    assert tool_result_data(result) == {"value": 6}
    calls.assert_called_once_with(3, hass, llm_context, 2)


def test_function_metadata_defaults(hass: HomeAssistant) -> None:
    """Omitted metadata retains HA's conservative behavior defaults."""

    def unknown_tool():
        return {}

    tool = llm_tools.PowerFunctionTool(unknown_tool)
    llm_tools.async_register_tool(hass, tool, title=None, annotations=None)

    assert tool.title is None
    assert tool.annotations == llm.ToolAnnotations()


@pytest.mark.parametrize("override", [False, True])
def test_function_metadata_subclass_defaults(
    hass: HomeAssistant, override: bool
) -> None:
    """Respect subclass metadata unless constructor keywords override it."""

    class ProviderTool(llm_tools.PowerFunctionTool):
        """Wrapper with provider-specific metadata."""

        title = "Provider title"
        annotations = READ_ANNOTATIONS
        integration = "external_provider"

    def provider_tool():
        return {}

    annotations = llm.ToolAnnotations(open_world=False)
    tool = ProviderTool(
        provider_tool,
        title="Override title" if override else None,
        annotations=annotations if override else None,
    )
    llm_tools.async_register_tool(hass, tool, title=None, annotations=None)

    assert tool.title == ("Override title" if override else "Provider title")
    assert tool.annotations is (annotations if override else READ_ANNOTATIONS)
    assert tool.integration == "external_provider"
    assert ProviderTool.title == "Provider title"
    assert ProviderTool.annotations is READ_ANNOTATIONS


@pytest.mark.parametrize("override", [False, True])
def test_class_metadata_registration(hass: HomeAssistant, override: bool) -> None:
    """Preserve class defaults or apply explicit per-instance registration values."""

    class ProviderTool(llm_tools.PowerLLMTool):
        """Class tool with existing metadata."""

        name = "provider_tool"
        title = "Provider title"
        annotations = READ_ANNOTATIONS
        integration = "external_provider"

    annotations = llm.ToolAnnotations(open_world=False)
    tool = ProviderTool()
    llm_tools.async_register_tool(
        hass,
        tool,
        title="Override title" if override else None,
        annotations=annotations if override else None,
    )

    assert hass.data[DOMAIN][tool.name] is tool
    assert tool.title == ("Override title" if override else "Provider title")
    assert tool.annotations is (annotations if override else READ_ANNOTATIONS)
    assert tool.integration == "external_provider"
    assert ProviderTool.title == "Provider title"
    assert ProviderTool.annotations is READ_ANNOTATIONS


def test_deferred_metadata_isolation(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build independent wrappers for each HA instance from deferred metadata."""
    monkeypatch.setattr(llm_tools, "HASS_LIST", [])
    monkeypatch.setattr(llm_tools, "LLM_TOOL_LIST", [])
    other_hass = Mock(spec=HomeAssistant)
    other_hass.data = {}

    def shared_tool():
        return {}

    assert (
        llm_tools.llm_tool(title="Shared title", annotations=READ_ANNOTATIONS)(
            shared_tool
        )
        is shared_tool
    )
    llm_tools.deferred_register_tools(hass)
    llm_tools.deferred_register_tools(other_hass)
    first = hass.data[DOMAIN]["shared_tool"]
    second = other_hass.data[DOMAIN]["shared_tool"]

    assert first is not second
    assert first.function is second.function is shared_tool
    assert first.annotations is second.annotations is READ_ANNOTATIONS
    first.title = "Instance title"
    assert second.title == "Shared title"

    llm_tools.deferred_register_tools(other_hass)
    assert other_hass.data[DOMAIN]["shared_tool"] is second
