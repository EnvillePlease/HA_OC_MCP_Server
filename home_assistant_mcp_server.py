# ========================================
# Home Assistant MCP Server
# ========================================
# File: home_assistant_mcp_server.py
# Function: Main MCP server script for Home Assistant integration
# Author: EnvillePlease
# Version: 1.0
# Created: 28 April 2026
# Modified: 28 April 2026
# ========================================

"""MCP server for Home Assistant integration using homeassistant_api client.
Produces a JSON description of the client's methods on stdout for MCP consumption.
"""

import os
import sys
import json
import inspect
from typing import get_type_hints, Any
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from homeassistant_api import Client

# Load environment variables from .env file
load_dotenv()

# Ensure unbuffered output and no encoding issues
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf8', buffering=1)

# Retrieve Home Assistant URL and token from environment variables
URL = os.getenv("HOME_ASSISTANT_URL")
TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

# Validate that required environment variables are set
if not URL or not TOKEN:
    raise ValueError("HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN must be set in the environment")

# Initialize the Home Assistant API client
client = Client(URL, TOKEN)

# Create the MCP server instance (not used directly here but kept for integration)
mcp = FastMCP("Home Assistant MCP Server")

# -----------------------------
# Introspection / serialization
# -----------------------------
def _param_to_dict(param: inspect.Parameter) -> dict:
    """Serialize a function parameter into a JSON-friendly dictionary.

    This helper captures the parameter name, kind, default value,
    and annotation for introspection output.
    """
    return {
        "name": param.name,
        "kind": param.kind.name,
        "default": None if param.default is inspect.Parameter.empty else param.default,
        "annotation": None if param.annotation is inspect.Parameter.empty else _safe_repr(param.annotation),
    }


def _safe_repr(obj: Any) -> str:
    """Return a safe string representation for an object.

    If repr() fails, fall back to the object's type name.
    """
    try:
        return repr(obj)
    except (TypeError, ValueError):
        return type(obj).__name__


def _func_to_dict(name: str, func: Any) -> dict:
    """Generate a metadata dictionary for a callable API member.

    The returned dictionary includes the signature, documented parameters,
    type hints, and the first line of the docstring.
    """
    sig = None
    params = []
    try:
        sig = inspect.signature(func)
        params = [_param_to_dict(p) for p in sig.parameters.values()]
    except (ValueError, TypeError):
        sig = None
    try:
        hints = get_type_hints(func)
        type_hints = {k: _safe_repr(v) for k, v in hints.items()}
    except (AttributeError, NameError, TypeError):
        type_hints = {}
    doc = inspect.getdoc(func) or ""
    short_doc = doc.splitlines()[0] if doc else ""
    return {
        "name": name,
        "signature": str(sig) if sig is not None else None,
        "params": params,
        "type_hints": type_hints,
        "doc": doc,
        "short_doc": short_doc,
    }


def _extract_client_api(obj) -> list[dict]:
    """Inspect a client object and return its public API description.

    Public members are any attributes and callables that do not begin with an underscore.
    """
    results = []
    for name, member in inspect.getmembers(obj):
        if name.startswith("_"):
            continue
        # Prefer callables/methods
        if inspect.isroutine(member) or inspect.ismethod(member) or inspect.isfunction(member) or callable(member):
            try:
                results.append(_func_to_dict(name, member))
            except (ValueError, TypeError, AttributeError):
                # fallback to minimal entry when introspection fails
                results.append({"name": name, "signature": None, "params": [], "doc": ""})
            continue
        # Non-callable attribute: include type and short repr
        try:
            value_repr = repr(member)
        except (TypeError, ValueError):
            value_repr = "<unrepresentable>"
        results.append({
            "name": name,
            "attr_type": type(member).__name__,
            "value_repr": value_repr[:200],
            "doc": (inspect.getdoc(member) or "").splitlines()[:3]
        })
    return results


def _add_example_values(api_list: list[dict]) -> list[dict]:
    """Populate function parameters with example values for generated documentation.

    This helper does not change the actual API, only attaches sample inputs
    to make the exported metadata easier to understand.
    """
    for item in api_list:
        examples = []
        for p in item.get("params", []):
            pname = p["name"].lower()
            ann = (p.get("annotation") or "").lower()
            example: Any = "example_value"
            if "token" in pname or "password" in pname:
                example = "<REDACTED>"
            elif "entity_id" in pname or "entity" in pname:
                example = "light.kitchen"
            elif "service" in pname:
                example = "light.turn_on"
            elif "data" in pname or "payload" in pname:
                example = {"entity_id": "light.kitchen", "brightness": 200}
            elif "area" in pname or "room" in pname:
                example = "living_room"
            elif "bool" in ann or pname.startswith("is_") or pname.startswith("has_"):
                example = True
            elif "int" in ann or "count" in pname or "number" in pname:
                example = 1
            # redact defaults that may contain tokens
            if isinstance(p.get("default"), str) and ("token" in pname or "password" in pname):
                p["default"] = "<REDACTED>"
            examples.append({p["name"]: example})
        item["examples"] = examples
    return api_list


# Ensure we do not leak sensitive environment values.
def _sanitize_export(data: Any) -> Any:
    """Redact configured secret values from JSON-serializable export data."""
    sensitive_keys = {"HOME_ASSISTANT_TOKEN", "TOKEN", "PASSWORD", "API_KEY"}
    j = json.dumps(data, default=str)
    for key in sensitive_keys:
        secret = os.getenv(key)
        if secret:
            j = j.replace(secret, "<REDACTED>")
    return json.loads(j)

@mcp.tool()
def get_client_api() -> str:
    """Return the Home Assistant client API description as a JSON string.

    This MCP tool exposes metadata about the Home Assistant client and
    its public callable members to MCP consumers.
    """
    api = _extract_client_api(client)
    api = _add_example_values(api)
    safe_api = _sanitize_export(api)
    return json.dumps({"client_api": safe_api}, indent=2, ensure_ascii=False)

@mcp.tool()
def run_client_api_request(method: str, *args, **kwargs) -> Any:
    """
    Execute a specified request on the Home Assistant.

    Use the api_dictionary_json object to look up what method to call on the client and execute it with the provided arguments.
    Allows an LLM to execute requests such as turning on lights, setting temperature, or rebooting Home Assistant.
    
    Args:
        method: The name of the method to call on the Home Assistant client
        *args: Positional arguments to pass to the method
        **kwargs: Keyword arguments to pass to the method
    
    Returns:
        The result of the method execution
    
    Raises:
        ValueError: If the method is not found in the API or is not callable
        RuntimeError: If the method execution fails
    """

    # Get the API dictionary as JSON string
    api_dictionary_json = get_client_api()
    api_dict = json.loads(api_dictionary_json)
    client_api = api_dict.get("client_api", [])

    # Find the requested method in the API dictionary
    method_info = None
    for api_item in client_api:
        if api_item.get("name") == method:
            method_info = api_item
            break

    # Validate that the method exists in the client API
    if method_info is None:
        available_methods = [item.get("name") for item in client_api if item.get("name")]
        raise ValueError(
            f"Method '{method}' not found in Home Assistant client API. "
            f"Available methods: {', '.join(available_methods)}"
        )

    # Verify the method is callable on the client
    if not hasattr(client, method):
        raise ValueError(f"Method '{method}' is not available on the client object")

    client_method = getattr(client, method)
    if not callable(client_method):
        raise ValueError(f"'{method}' is not callable on the client object")

    # Normalize MCP tool payload fields from the tool wrapper.
    # Some MCP runtimes send explicit args/kwargs fields even when the Python
    # method signature uses *args and **kwargs to model the tool input.
    payload_args = kwargs.pop("args", None)
    if payload_args is not None:
        if payload_args is None:
            payload_args = ()
        if not isinstance(payload_args, (list, tuple)):
            raise ValueError("The MCP tool 'args' field must be a list or tuple")
        args = tuple(payload_args) + args

    payload_kwargs = kwargs.pop("kwargs", None)
    if payload_kwargs is not None:
        if not isinstance(payload_kwargs, dict):
            raise ValueError("The MCP tool 'kwargs' field must be a dict")
        kwargs = {**payload_kwargs, **kwargs}

    # Execute the method with provided arguments and return the result
    try:
        if args:
            result = client_method(*args, **kwargs)
        else:
            result = client_method(**kwargs)
        return result
    except TypeError as e:
        raise ValueError(
            f"Invalid arguments for method '{method}': {str(e)}"
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"Error executing method '{method}': {str(e)}"
        ) from e


# Start the server when invoked directly.
if __name__ == "__main__":
    mcp.run()
