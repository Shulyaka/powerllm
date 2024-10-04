# Power LLM
[![CI](https://github.com/Shulyaka/powerllm/actions/workflows/powerllm.yml/badge.svg?branch=master)](https://github.com/Shulyaka/powerllm/actions/workflows/powerllm.yml)
[![Coverage Status](https://coveralls.io/repos/github/Shulyaka/powerllm/badge.svg?branch=master)](https://coveralls.io/github/Shulyaka/powerllm?branch=master)

Home Assistant custom component for LLM empowerment.

This integration provides:

1. HTTP API for available LLM tools to integrate HA LLM Tools with an externally running LLM
2. Framework to easily add new LLM tools from other custom integrations, making Home Assistant a platform for LLM tools experimentation.
3. Enhanced and experimental versions of core 'Assist' LLM tools
4. Extra LLM tools:
   * Web, maps, and news search with Duck Duck Go
   * Permanent memory tool
   * Python code execution

Please feel free to raise an issue if you have an idea of another useful tool!

## Installation

1. Copy `custom_components/powerllm` directory from this repository into `custom_components/` directory in your config directory. Optionally use HACS for this step.
2. Restart Home Assistant
3. Add a config entry by going to Settings -> Device and Services -> Add integration or by pressing here: [![Add integration to My HA](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powerllm). If you only need the HTTP API but not the extra tools, then you can just add `powerllm:` into your `configuration.yaml` instead.
4. Configure your LLM integrations, such as [OpenAI Conversation](https://www.home-assistant.io/integrations/openai_conversation/) [![Show integration on My HA](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=openai_conversation) or [Google Generative AI](https://www.home-assistant.io/integrations/google_generative_ai_conversation/) [![Show integration on My HA](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=google_generative_ai_conversation) to use Power LLM API instead of Assist API.

## Configuration

There are following configuration options available:

* ### Include exposed entities into api prompt
  For each interaction with LLM, a system prompt is generated. If this option is enabled, the system prompt will contain the list of all exposed devices. It would allow the LLM to find the devices you refer to more fast and reliable, but also consume input tokens. If your list of exposed entities is really big, you may want to disable this option and rely on other methods, such as explicit querying (see next option) or just guessing by its name from the user prompt (make sure to set up your aliases).

* ### Include relevant entities into intent tool response
  Some intents will return the states of affected entities in its response. If this option is enabled, they are also forwarded to the LLM. Usually they are not so important, and a simple response will also do the job. With one exception: the `HassGetState`, this is the intent specifically used to find entities matching certain criteria and return their states in the response. In fact, if this option is disabled, the `HassGetState` would not be exposed to the LLM at all.

  Please keep in mind that the state returned returned using this option contains more information and attributes, than the list in the prompt. So if you want your LLM to be able to answer questions like `how long have the lights been on?`, keep it enabled.

* ### DuckDuckGo Region
  The server location used for web and news search. You can safely leave it as `No Region`.

* ### Only allow referencing exposed entities in scripts
  Power LLM includes a tool that allows LLM to write scripts in Home Assistant format and instantly execute them to handle more complex tasks than covered by standard intents. If this option is enabled, Power LLM will make an effort to verify that all entities referenced in this script are exposed. This process however has certain limitations (for example if the entity id is evaluated from template at runtime), so the script might fail this check more often than wanted.

* ### Facts that the model remembers for each user
  This field should be in a yaml map format, with user_id as the key and string as the value. The string contains the facts that the LLM chose to remember about the user. The best way to add things here is to ask LLM to remember something about you. This option is presented here in case you want to delete something.

## HTTP API

This is an extension of [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/) providing LLM-specific endpoints, such as:

* GET `/api/powerllm`

  Returns the list available LLM API, such as 'Assist', 'Power LLM', etc

* GET `/api/powerllm/<api>`

  Returns the prompt and the list of tools for a specific api. Optional parameters: `user_input`, `language`, `device_id`

* POST `/api/powerllm/<api>/<tool_name>`

  Calls the tool and returns the result. Optional parameters: `user_input`, `language`, `device_id`, `tool_args`

## Tools extension by other custom integrations

Other custom integrations can use `Power LLM` to add more tools to extend the functionality. Instruct your users to also install the Power LLM integration and add "powerllm" to dependencies in your `manifest.json`.

There are two options:

* Extend the `custom_components.powerllm.PowerLLMTool` class to implement the functionality, then call `custom_components.powerllm.async_register_tool` to register the object of the class. See the [memory tool](https://github.com/Shulyaka/powerllm/blob/master/custom_components/powerllm/tools/memory.py) for an example

* Use the `custom_components.powerllm.llm_tool` decorator for any python function. The function is recommended to have annotations for all parameters. If a parameter name is "hass", "llm_context", or any of the `homeassistant.helpers.llm.LLMContext` attributes, then the value for that parameter will be provided by the conversation agent 'pytest-style'. All other arguments will be provided by the LLM. Refer to the [python code tool](https://github.com/Shulyaka/powerllm/blob/master/custom_components/powerllm/tools/python_code.py) as an example.

## TODO

* Selectively Enable/Disable any tool
* Weather forecast intent
* Ability to talk to other conversation agents (i.e. "Ask expert" for a reasoning model, or NLP conversation (Assist) for device control fallback)
* Your suggestions!
