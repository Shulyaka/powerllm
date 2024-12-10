"""Dynamic script execution tool."""

import datetime
import logging
import operator
import time
from numbers import Number
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from RestrictedPython import (
    compile_restricted_exec,
    limited_builtins,
    safe_builtins,
    utility_builtins,
)
from RestrictedPython.Eval import default_guarded_getitem
from RestrictedPython.Guards import (
    full_write_guard,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safer_getattr,
)

from ..llm_tools import llm_tool

_LOGGER = logging.getLogger(__name__)


class MyHandler(logging.Handler):
    """Log handler that saves the logs in memory."""

    logs: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord):
        """Save the record."""
        self.logs.append(record)


@llm_tool
def python_code_execute(hass: HomeAssistant, source: str, data: dict | None = None):
    """Execute python code in a restricted environment.

    Use this tool for math calculations among other things.
    Use `output` dictionary for output and `logger` object for logging.
    """
    log_handler = MyHandler()
    logger = logging.getLogger(f"{__name__}.script")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_handler)
    try:
        output = execute(hass, source, data)
    except HomeAssistantError as e:
        output = {"error": type(e).__name__}
        if str(e):
            output["error_text"] = str(e)
    logger.removeHandler(log_handler)

    result = {"output": output}
    logs = [
        {"level": record.levelno, "msg": record.getMessage()}
        for record in log_handler.logs
    ]
    if logs:
        result["logs"] = logs
    return result


ALLOWED_HASS = {"bus", "services", "states"}
ALLOWED_EVENTBUS = {"fire"}
ALLOWED_STATEMACHINE = {
    "entity_ids",
    "all",
    "get",
    "is_state",
    "is_state_attr",
    "remove",
    "set",
}
ALLOWED_SERVICEREGISTRY = {"services", "has_service", "call"}
ALLOWED_TIME = {
    "sleep",
    "strftime",
    "strptime",
    "gmtime",
    "localtime",
    "ctime",
    "time",
    "mktime",
}
ALLOWED_DATETIME = {"date", "time", "datetime", "timedelta", "tzinfo"}
ALLOWED_DT_UTIL = {
    "utcnow",
    "now",
    "as_utc",
    "as_timestamp",
    "as_local",
    "utc_from_timestamp",
    "start_of_local_day",
    "parse_datetime",
    "parse_date",
    "get_age",
}
ALLOWED_IMPORT = {
    "math",
    "random",
    "itertools",
    "functools",
    "collections",
    "json",
    "csv",
    "re",
    "string",
    "operator",
    "enum",
    "types",
}


class ScriptError(HomeAssistantError):
    """When a script error occurs."""


IOPERATOR_TO_OPERATOR = {
    "%=": operator.mod,
    "&=": operator.and_,
    "**=": operator.pow,
    "*=": operator.mul,
    "+=": operator.add,
    "-=": operator.sub,
    "//=": operator.floordiv,
    "/=": operator.truediv,
    "<<=": operator.lshift,
    ">>=": operator.rshift,
    "@=": operator.matmul,
    "^=": operator.xor,
    "|=": operator.or_,
}


def guarded_inplacevar(op: str, target: Any, operand: Any) -> Any:
    """Implement augmented-assign (+=, -=, etc.) operators for restricted code.

    See RestrictedPython's `visit_AugAssign` for details.
    """
    if not isinstance(target, (list, Number, str)):
        raise ScriptError(f"The {op!r} operation is not allowed on a {type(target)}")
    op_fun = IOPERATOR_TO_OPERATOR.get(op)
    if not op_fun:
        raise ScriptError(f"The {op!r} operation is not allowed")
    return op_fun(target, operand)


def execute(hass, source, data=None):
    """Execute Python source."""

    compiled = compile_restricted_exec(source)

    if compiled.errors:
        raise ScriptError("Compile error: %s", ", ".join(compiled.errors))

    logger = logging.getLogger(f"{__name__}.script")

    if compiled.warnings:
        logger.warning("Warning loading script: %s", ", ".join(compiled.warnings))

    class ProtectedLogger:
        """Replacement logger for compatibility."""

        def getLogger(self, *args, **kwargs):
            """Return a specific logger every time."""
            return logger

    def protected_import(name: str, *args, **kwargs):
        if name.split(".")[0] in ALLOWED_IMPORT:
            return __import__(name, *args, **kwargs)
        if name == "datetime":
            return datetime
        if name == "time":
            return TimeWrapper()
        if name == "dt_util":
            return dt_util
        if name == "logging":
            return ProtectedLogger()
        raise ImportError(f"Module {name} not found")

    def protected_getattr(obj, name, default=None):
        """Restricted method to get attributes."""
        if name.startswith("async_"):
            raise ScriptError("Not allowed to access async methods")
        if (
            obj is hass
            and name not in ALLOWED_HASS
            or obj is hass.bus
            and name not in ALLOWED_EVENTBUS
            or obj is hass.states
            and name not in ALLOWED_STATEMACHINE
            or obj is hass.services
            and name not in ALLOWED_SERVICEREGISTRY
            or obj is dt_util
            and name not in ALLOWED_DT_UTIL
            or obj is datetime
            and name not in ALLOWED_DATETIME
            or isinstance(obj, TimeWrapper)
            and name not in ALLOWED_TIME
        ):
            raise ScriptError(f"Not allowed to access {obj.__class__.__name__}.{name}")

        return safer_getattr(obj, name, default)

    extra_builtins = {
        "__import__": protected_import,
        "datetime": datetime,
        "sorted": sorted,
        "time": TimeWrapper(),
        "dt_util": dt_util,
        "min": min,
        "max": max,
        "sum": sum,
        "any": any,
        "all": all,
        "enumerate": enumerate,
        "type": type,
        "map": map,
        "filter": filter,
        "reversed": reversed,
        "getattr": getattr,
        "hasattr": hasattr,
    }
    builtins = safe_builtins.copy()
    builtins.update(utility_builtins)
    builtins.update(limited_builtins)
    builtins.update(extra_builtins)
    restricted_globals = {
        "__builtins__": builtins,
        "_print_": StubPrinter,
        "_getattr_": protected_getattr,
        "_write_": full_write_guard,
        "_getiter_": iter,
        "_getitem_": default_guarded_getitem,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_unpack_sequence_": guarded_unpack_sequence,
        "_inplacevar_": guarded_inplacevar,
        "hass": hass,
        "data": data or {},
        "logger": logger,
        "output": {},
    }

    try:
        _LOGGER.info("Executing script: %s", data)
        # pylint: disable-next=exec-used
        exec(compiled.code, restricted_globals)  # noqa: S102
        _LOGGER.debug(
            "Output of python_script:\n%s",
            restricted_globals["output"],
        )
        # Ensure that we're always returning a dictionary
        if not isinstance(restricted_globals["output"], dict):
            output_type = type(restricted_globals["output"])
            restricted_globals["output"] = {}
            raise ScriptError(  # noqa: TRY301
                f"Expected `output` to be a dictionary, was {output_type}"
            )
    except ScriptError as err:
        raise ServiceValidationError(f"Error executing script: {err}") from err
    except Exception as err:
        raise HomeAssistantError(
            f"Error executing script ({type(err).__name__}): {err}"
        ) from err

    return restricted_globals["output"]


class StubPrinter:
    """Class to handle printing inside scripts."""

    def __init__(self, _getattr_):
        """Initialize our printer."""

    def _call_print(self, *objects, **kwargs):
        """Print text."""
        _LOGGER.warning("Don't use print() inside scripts. Use logger.info() instead")


class TimeWrapper:
    """Wrap the time module."""

    # Class variable, only going to warn once per Home Assistant run
    warned = False

    def sleep(self, *args, **kwargs):
        """Sleep method that warns once."""
        if not TimeWrapper.warned:
            TimeWrapper.warned = True
            _LOGGER.warning(
                "Using time.sleep can reduce the performance of Home Assistant"
            )

        time.sleep(*args, **kwargs)

    def __getattr__(self, attr):
        """Fetch an attribute from Time module."""
        attribute = getattr(time, attr)
        if callable(attribute):

            def wrapper(*args, **kw):
                """Wrap to return callable method if callable."""
                return attribute(*args, **kw)

            return wrapper
        return attribute
