"""Rest API for Home Assistant."""

import logging
from http import HTTPStatus
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, llm
from voluptuous_openapi import convert

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class LLMToolsApiView(HomeAssistantView):
    """View to get LLM APIs."""

    url = f"/api/{DOMAIN}"
    name = f"api:{DOMAIN}"

    @callback
    def get(self, request: web.Request) -> web.Response:
        """Get LLM Tools list."""
        hass = request.app[KEY_HASS]
        return self.json(
            [{"name": api.name, "id": api.id} for api in llm.async_get_apis(hass)]
        )


class LLMToolsListView(HomeAssistantView):
    """View to get LLM Tools list."""

    url = f"/api/{DOMAIN}/" + "{api}"
    name = f"api:{DOMAIN}:api"

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Optional("user_input"): cv.string,
                vol.Optional("language"): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
        allow_empty=True,
    )
    async def get(
        self, request: web.Request, data: dict[str, Any], api: str
    ) -> web.Response:
        """Get LLM Tools list."""
        hass = request.app[KEY_HASS]

        llm_context = llm.LLMContext(
            platform=DOMAIN,
            context=self.context(request),
            user_prompt=data.get("user_input"),
            language=data.get("language", hass.config.language),
            assistant=CONVERSATION_DOMAIN,
            device_id=data.get("device_id"),
        )

        try:
            llm_api = await llm.async_get_api(hass, api, llm_context)
            return self.json(
                {"prompt": llm_api.api_prompt, "tools": async_llm_tools_json(llm_api)}
            )
        except HomeAssistantError as e:
            return self.json_message(
                str(e),
                HTTPStatus.NOT_FOUND
                if str(e).endswith(" not found")
                else HTTPStatus.INTERNAL_SERVER_ERROR,
            )


class LLMToolView(HomeAssistantView):
    """View to get LLM Tool."""

    url = f"/api/{DOMAIN}/" + "{api}/{tool_name}"
    name = f"api:{DOMAIN}:api:tool"

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Optional("tool_args", default={}): {cv.string: object},
                vol.Optional("user_input"): cv.string,
                vol.Optional("language"): cv.string,
                vol.Optional("device_id"): cv.string,
            }
        ),
        allow_empty=True,
    )
    async def post(
        self,
        request: web.Request,
        data: dict[str, Any] | None,
        api: str,
        tool_name: str,
    ) -> web.Response:
        """Call an the LLM Tool."""
        hass = request.app[KEY_HASS]

        llm_context = llm.LLMContext(
            platform=DOMAIN,
            context=self.context(request),
            user_prompt=data.get("user_input"),
            language=data.get("language", hass.config.language),
            assistant=CONVERSATION_DOMAIN,
            device_id=data.get("device_id"),
        )

        tool_input = llm.ToolInput(
            tool_name=tool_name,
            tool_args=data["tool_args"],
        )

        try:
            llm_api = await llm.async_get_api(hass, api, llm_context)
            _LOGGER.info(
                "Tool call: %s::%s(%s)",
                api,
                tool_input.tool_name,
                tool_input.tool_args,
            )
            tool_response = await llm_api.async_call_tool(tool_input)
        except (HomeAssistantError, vol.Invalid) as e:
            tool_response = {"error": type(e).__name__}
            if str(e):
                tool_response["error_text"] = str(e)
            _LOGGER.info("Tool response: %s", tool_response)
            return self.json(
                tool_response,
                HTTPStatus.NOT_FOUND
                if str(e).endswith(" not found")
                else HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        _LOGGER.info("Tool response: %s", tool_response)

        return self.json(tool_response)


@callback
def async_llm_tools_json(api: llm.APIInstance) -> list[dict[str, Any]]:
    """Generate LLM Tools data to JSONify."""

    def format_tool(tool: llm.Tool) -> dict[str, Any]:
        """Format tool specification."""
        tool_spec = {"name": tool.name}
        if tool.description:
            tool_spec["description"] = tool.description
        tool_spec["parameters"] = convert(tool.parameters)
        return tool_spec

    return [format_tool(tool) for tool in api.tools]
