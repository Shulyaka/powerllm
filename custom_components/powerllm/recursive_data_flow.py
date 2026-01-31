"""Recursive config flow and options flow."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section


class RecursiveBaseFlow:
    """Overwrite methods in this class with integration-specific config."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_validate_input(
        self, step_id: str, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate step data."""
        return {}

    def step_enabled(self, step_id: str) -> bool:
        """Check if the current data flow step is enabled."""
        return True

    @property
    def title(self) -> str:
        """Return config flow title."""
        raise self.domain

    async def get_data_schema(self) -> vol.Schema:
        """Get data schema."""
        raise NotImplementedError

    async def get_options_schema(self) -> vol.Schema:
        """Get options schema."""
        raise NotImplementedError


class RecursiveDataFlow(RecursiveBaseFlow):
    """Handle both config and option flow."""

    data_schema: vol.Schema | None = None
    options_schema: vol.Schema | None = None
    domain: str | None = None

    def __init_subclass__(
        cls,
        *,
        data_schema: vol.Schema | None = None,
        options_schema: vol.Schema | None = None,
        **kwargs: Any,
    ) -> None:
        """Set config and options schema if provided."""
        super().__init_subclass__(**kwargs)
        cls.data_schema = data_schema
        cls.options_schema = options_schema
        cls.domain = kwargs.get("domain")

    def __init__(self) -> None:
        """Initialize the flow."""
        self.data: Mapping[str, Any] | None = None
        self.options: Mapping[str, Any] | None = None
        self.config_step = None
        self.current_step_schema = None
        self.current_step_id = None
        self.current_step_data = None

    def config_step_generator(
        self,
    ) -> Generator[tuple[str, vol.Schema, dict, bool]]:
        """Return a generator of the next step config."""

        def traverse_config(
            name: str, schema: vol.Schema, data: dict, last_config: bool = False
        ) -> tuple[str, vol.Schema, dict, bool]:
            current_schema = {}
            recursive_schema = {}
            for var, val in schema.schema.items():
                if isinstance(val, vol.Schema):
                    recursive_schema[var] = val
                elif isinstance(val, dict):
                    recursive_schema[var] = vol.Schema(val)
                else:
                    current_schema[var] = val

            yield (
                name,
                vol.Schema(current_schema),
                data,
                last_config and not recursive_schema,
            )
            for index, (var, val) in enumerate(recursive_schema.items(), start=1):
                if self.step_enabled(str(var)):
                    yield from traverse_config(
                        str(var),
                        val,
                        data.setdefault(var, {}),
                        last_config and index == len(recursive_schema),
                    )

        if not isinstance(self, OptionsFlow):
            yield from traverse_config("user", self.data_schema, self.data, False)
        yield from traverse_config("init", self.options_schema, self.options, True)

    async def async_step(
        self, step_id: str, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the step."""
        if self.config_step is None:
            self.config_step = self.config_step_generator()
            (
                self.current_step_id,
                self.current_step_schema,
                self.current_step_data,
                self.last_step,
            ) = next(self.config_step)
        if self.current_step_id != step_id:
            raise RuntimeError("Unexpected step id")

        errors = {}
        if user_input is not None:
            for name, var in user_input.items():
                self.current_step_data[name] = var
            errors = await self.async_validate_input(
                step_id=step_id,
                user_input=user_input,
            )
            if not errors:
                try:
                    (
                        self.current_step_id,
                        self.current_step_schema,
                        self.current_step_data,
                        self.last_step,
                    ) = next(self.config_step)
                    return await self.async_step(self.current_step_id)
                except StopIteration:
                    return self.async_create_entry(
                        title=self.title, data=self.data, options=self.options
                    )

        schema = self.add_suggested_values_to_schema(
            self.current_step_schema, self.current_step_data
        )

        return self.async_show_form(
            step_id=self.current_step_id,
            data_schema=schema,
            errors=errors,
            last_step=self.last_step,
        )

    def __getattr__(self, attr: str) -> Any:
        """Get step method."""
        if attr.startswith("async_step_"):
            return partial(self.async_step, attr[11:])
        if hasattr(super(), "__getattr__"):
            return super().__getattr__(attr)
        raise AttributeError


class RecursiveOptionsFlow(RecursiveDataFlow, OptionsFlow):
    """Handle an options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self.data = config_entry.data
        self.options = config_entry.options.copy()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options flow entry point."""
        if self.options_schema is None:
            self.options_schema = await self.get_options_schema()
        return await self.async_step("init", user_input)

    @callback
    def async_create_entry(
        self,
        *,
        data: Mapping[str, Any],
        options: Mapping[str, Any] | None = None,
        **kwargs,
    ) -> ConfigFlowResult:
        """Return result entry for option flow."""
        return super().async_create_entry(data=options, **kwargs)


class RecursiveConfigFlow(RecursiveDataFlow, ConfigFlow):
    """Handle a config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Config flow entry point."""
        if self.data_schema is None:
            self.data_schema = await self.get_data_schema()
        if self.options_schema is None:
            self.options_schema = await self.get_options_schema()
        if self.data is None:
            self.data = self.suggested_values_from_default(self.data_schema)
        if self.options is None:
            self.options = self.suggested_values_from_default(self.options_schema)
        return await self.async_step("user", user_input)

    def suggested_values_from_default(
        self, data_schema: vol.Schema | Mapping[str, Any] | section
    ) -> Mapping[str, Any]:
        """Generate suggested values from schema markers."""
        if isinstance(data_schema, section):
            data_schema = data_schema.schema
        if isinstance(data_schema, vol.Schema):
            data_schema = data_schema.schema

        suggested_values = {}
        for key, value in data_schema.items():
            if isinstance(key, vol.Marker) and not isinstance(
                key.default, vol.Undefined
            ):
                suggested_values[str(key)] = key.default()
            if isinstance(value, (vol.Schema, dict, section)):
                value = self.suggested_values_from_default(value)
                if value:
                    suggested_values[str(key)] = value
        return suggested_values

    @classmethod
    @callback
    def async_get_options_flow(cls, config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""

        class MyOptionsFlow(
            RecursiveOptionsFlow,
            cls,
            data_schema=cls.data_schema,
            options_schema=cls.options_schema,
        ):
            pass

        return MyOptionsFlow(config_entry)

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        """Return options flow support for this handler."""
        return cls.get_options_schema is not RecursiveBaseFlow.get_options_schema or (
            cls.options_schema is not None and cls.options_schema.schema
        )
