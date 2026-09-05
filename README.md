# Power LLM
[![CI](https://github.com/Shulyaka/powerllm/actions/workflows/powerllm.yml/badge.svg?branch=master)](https://github.com/Shulyaka/powerllm/actions/workflows/powerllm.yml)
[![Coverage Status](https://coveralls.io/repos/github/Shulyaka/powerllm/badge.svg?branch=master)](https://coveralls.io/github/Shulyaka/powerllm?branch=master)

Home Assistant custom component for LLM empowerment.

This integration provides:

1. HTTP API for available LLM tools to integrate HA LLM Tools with an externally running LLM
2. Framework to easily add new LLM tools from other custom integrations, making Home Assistant a platform for LLM tools experimentation.
3. Detailed entity queries with `HassGetState`, including attributes and time since the last state change
4. Selectively enable or disable PowerLLM tools
5. Extra LLM tools:
   * Web and news search with Duck Duck Go
   * Web scrapping to access the Internet
   * Permanent memory tool
   * Python code execution

Please feel free to raise an issue if you have an idea of another useful tool!

## Installation

Requires Home Assistant 2026.8 or later.

1. Copy `custom_components/powerllm` directory from this repository into `custom_components/` directory in your config directory. Optionally use HACS for this step.
2. Restart Home Assistant
3. Add a config entry by going to Settings -> Device and Services -> Add integration or by pressing here: [![Add integration to My HA](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powerllm). If you only need the HTTP API but not the extra tools, then you can just add `powerllm:` into your `configuration.yaml` instead.
4. Configure your LLM integrations, such as [OpenAI Conversation](https://www.home-assistant.io/integrations/openai_conversation/) [![Show integration on My HA](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=openai_conversation) or [Google Generative AI](https://www.home-assistant.io/integrations/google_generative_ai_conversation/) [![Show integration on My HA](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=google_generative_ai_conversation) to select **both Assist and your Power LLM API**. Assist provides home control, timers, exposed scripts, calendars, to-do lists, live context, and date/time. PowerLLM provides the additional tools.

When upgrading a pre-HA2026.8 installation, add Assist to every conversation agent that previously selected only PowerLLM. PowerLLM no longer duplicates Assist tools or automatically exposes registered intents. Integrations should contribute those tools through Home Assistant's `llm` platform. PowerLLM's custom-tool registration framework remains available.

## Configuration

There are following configuration options available:

* ### Tool selection
  Select which PowerLLM tools the model may call. `HassGetState` is a normal selectable tool that always returns detailed states for matching entities, including entity IDs, attributes, aliases, area/floor, and time since the last state change. It can query both entities matching a requested state and those that do not match.

  Assist controls its own tools and entity overview. The former options to include exposed entities in the prompt and attach entity states to every intent response have been removed. An upgrade preserves a previously disabled `HassGetState` in tool selection. Detailed state queries remain available as a separate tool call; Assist's control responses are unchanged.

* ### DuckDuckGo Region
  The server location used for web and news search. You can safely leave it as `No Region`.

* ### Only allow referencing exposed entities in scripts
  Power LLM includes a tool that allows LLM to write scripts in Home Assistant format and instantly execute them to handle more complex tasks than covered by standard intents. If this option is enabled, Power LLM will make an effort to verify that all entities referenced in this script are exposed. This process however has certain limitations (for example if the entity id is evaluated from template at runtime), so the script might fail this check more often than wanted.

  When the script tool is enabled, its prompt includes a mapping of exposed entity IDs to names, with no states or other attributes. Disabling the tool removes this mapping. The mapping always includes only exposed entities, even when the script exposure restriction is disabled.

* ### Facts that the model remembers for each user
  These field contain the facts that the LLM chose to remember about the user for each `user_id`. You can also ask LLM to remember something about you. This option is presented here in case you want to delete something.

## HTTP API

HTTP clients that previously fetched all tools from `/api/powerllm/powerllm` must also fetch `/api/powerllm/assist` and send each tool call to its owning API. These endpoints expose one API at a time. Conversation integrations selecting both APIs use Home Assistant's merged API, which prefixes tool names with their API namespace.

This is an extension of [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/) providing LLM-specific endpoints, such as:

* GET `/api/powerllm`

  Returns the list available LLM API, such as 'Assist', 'Power LLM', etc

* GET `/api/powerllm/<api>`

  Returns the prompt and the list of tools for a specific api.

* POST `/api/powerllm/<api>`

  Same as above, but accepts optional parameters: `user_input`, `language`, `device_id`

* POST `/api/powerllm/<api>/<tool_name>`

  Calls the tool and returns the result. Optional parameters: `user_input`, `language`, `device_id`, `tool_args`

## Tools extension by other custom integrations

Other custom integrations can use `Power LLM` to add more tools to extend the functionality. Instruct your users to also install the Power LLM integration and add "powerllm" to dependencies in your `manifest.json`.

There are two options:

* Extend the `custom_components.powerllm.PowerLLMTool` class to implement the functionality, then call `custom_components.powerllm.async_register_tool` to register the object of the class. See the [memory tool](https://github.com/Shulyaka/powerllm/blob/master/custom_components/powerllm/tools/memory.py) for an example. The class must support deepcopy.

* Use the `custom_components.powerllm.llm_tool` decorator for any python function. The function is recommended to have type annotations for all parameters. If a parameter name is "hass", "llm_context", or any of the `homeassistant.helpers.llm.LLMContext` attributes, then the value for that parameter will be provided by the conversation agent ("pytest-style"). All other arguments will be provided by the LLM. Refer to the [python code tool](https://github.com/Shulyaka/powerllm/blob/master/custom_components/powerllm/tools/python_code.py) as an example. A synchronous function should be declared as `@callback`, or it will be executed in a separate thread than the main hass loop, while an async function will be run concurrently in the main event loop and therefore is not allowed to use any blocking operations. If using both `@llm_tool` and `@callback`, `@llm_tool` should be the outer decorator.

The tools in this repository use various techniques for demonstration.

## TODO

* Weather forecast intent
* Ability to talk to other conversation agents (i.e. "Ask expert" for a reasoning model, or NLP conversation (Assist) for device control fallback)
* Your suggestions!
