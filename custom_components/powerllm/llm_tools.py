"""Power LLM Tools."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from types import NoneType, UnionType
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

import probatio as vol
from homeassistant.core import HomeAssistant, callback, is_callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PowerLLMTool(llm.Tool):
    """Base class for Power LLM Tools."""

    integration = DOMAIN

    @callback
    def prompt(self, hass: HomeAssistant, llm_context: llm.LLMContext) -> str | None:
        """Additional system prompt for this tool."""

    @callback
    def async_is_applicable(
        self, hass: HomeAssistant, llm_context: llm.LLMContext
    ) -> bool:
        """Check the tool applicability."""
        return True


class PowerFunctionTool(PowerLLMTool):
    """LLM Tool representing an Python function.

    The function is recommended to have annotations for all parameters.
    If a parameter name is "hass", "llm_context", or any of the LLMContext
    attributes, then the value for that parameter will be provided by the
    conversation agent 'pytest-style'.
    All other arguments will be provided by the LLM.
    Async functions are not allowed to use any blocking code, while a synchronous
    function will be executed in a separate thread.
    """

    function: Callable

    def __init__(
        self,
        function: Callable,
    ) -> None:
        """Init the class."""

        self.function = function

        if self.integration == DOMAIN:
            module = getattr(inspect.unwrap(function), "__module__", None) or ""
            for prefix in ("custom_components.", "homeassistant.components."):
                if module.startswith(prefix):
                    domain = module.removeprefix(prefix).partition(".")[0]
                    self.integration = domain or DOMAIN
                    break

        self.name = function.__name__
        self.name = self.name.removeprefix("async_")

        self.description = inspect.getdoc(function)

        def hint_to_schema(hint: Any) -> Any:
            if isinstance(hint, UnionType) or get_origin(hint) is Union:
                hints = get_args(hint)
                if len(hints) == 2 and hints[0] is NoneType:
                    return vol.Maybe(hint_to_schema(hints[1]))
                if len(hints) == 2 and hints[1] is NoneType:
                    return vol.Maybe(hint_to_schema(hints[0]))
                return vol.Any(*tuple(hint_to_schema(x) for x in hints))

            if get_origin(hint) is list or get_origin(hint) is set:
                schema = get_args(hint)[0]
                if schema is Any or isinstance(schema, TypeVar):
                    return get_origin(hint)
                return [hint_to_schema(schema)]

            if get_origin(hint) is dict:
                schema = get_args(hint)
                if (
                    schema[0] is Any
                    or schema[1] is Any
                    or isinstance(schema[0], TypeVar)
                    or isinstance(schema[1], TypeVar)
                ):
                    return dict
                return {schema[0]: schema[1]}

            return hint

        schema = {}
        annotations = get_type_hints(function)
        for param in inspect.signature(function).parameters.values():
            if param.name in ("hass", "llm_context"):
                continue
            if hasattr(llm.LLMContext, param.name):
                continue

            hint = annotations.get(param.name, Any)

            schema[
                (
                    vol.Required(param.name)
                    if param.default is inspect.Parameter.empty
                    else vol.Optional(param.name, default=param.default)
                )
            ] = hint_to_schema(hint)

        self.parameters = vol.Schema(schema)

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        """Call the function."""
        kwargs = self.parameters(tool_input.tool_args)
        for parameter in inspect.signature(self.function).parameters.values():
            if parameter.name == "hass":
                kwargs["hass"] = hass
            elif parameter.name == "llm_context":
                kwargs["llm_context"] = llm_context
            elif hasattr(llm.LLMContext, parameter.name):
                kwargs[parameter.name] = getattr(llm_context, parameter.name)

        try:
            if inspect.iscoroutinefunction(self.function):
                result = await self.function(**kwargs)
            elif is_callback(self.function) or hass.loop != asyncio.get_running_loop():
                result = self.function(**kwargs)
            else:
                result = await hass.loop.run_in_executor(
                    None, lambda: self.function(**kwargs)
                )
        except (HomeAssistantError, vol.Invalid):
            raise
        except Exception as e:
            raise HomeAssistantError(
                f"Error calling {self.name} ({type(e).__name__}): {e}"
            ) from e

        if isinstance(result, llm.ToolResult):
            return result
        return llm.ToolResult(
            data=result if isinstance(result, dict) else {"result": result}
        )


@callback
def async_register_tool(hass: HomeAssistant, tool: PowerLLMTool | Callable) -> None:
    """Register an LLM tool with PowerLLM integration."""
    tools = hass.data.setdefault(DOMAIN, {})

    if not isinstance(tool, PowerLLMTool):
        if isinstance(tool, llm.Tool):
            raise TypeError("Please base your tool class on powerllm.PowerLLMTool")
        tool = PowerFunctionTool(tool)

    if tool.name in tools:
        _LOGGER.warning("Overwriting an already registered tool %s", tool.name)

    tools[tool.name] = tool


HASS_LIST = []
LLM_TOOL_LIST = []


def llm_tool(arg: HomeAssistant | Callable) -> Callable:
    """Register a function as an LLM Tool with decorator."""

    if isinstance(arg, HomeAssistant):
        hass = arg

        def _llm_tool(func: Callable) -> Callable:
            async_register_tool(hass, func)
            return func

        return _llm_tool

    func = arg
    LLM_TOOL_LIST.append(func)
    for hass in HASS_LIST:
        async_register_tool(hass, func)
    return func


def deferred_register_tools(hass: HomeAssistant) -> None:
    """Register tools declared with the decorator."""
    if hass in HASS_LIST:
        return

    HASS_LIST.append(hass)
    for func in LLM_TOOL_LIST:
        async_register_tool(hass, func)
