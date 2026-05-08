# ========================================
# Home Assistant MCP Server
# ========================================
# File: home_assistant_mcp_server.py
# Function: Main MCP server script for Home Assistant integration
# Author: EnvillePlease
# Version: 1.0
# Created: 28 April 2026
# Modified: 08 May 2026
# ========================================

"""MCP server for Home Assistant integration using homeassistant_api client.
Produces a JSON description of the client's methods on stdout for MCP consumption.
"""

import os
import io
import sys
import json
import inspect
from typing import Any, Optional, get_type_hints
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from homeassistant_api import Client

# Load environment variables from .env file
load_dotenv()

# Ensure unbuffered output and no encoding issues
old_stdout, old_stderr = sys.stdout, sys.stderr
sys.stdout = io.TextIOWrapper(old_stdout.buffer, encoding="utf8", line_buffering=True)
sys.stderr = io.TextIOWrapper(old_stderr.buffer, encoding="utf8", line_buffering=True)

# Retrieve Home Assistant URL and token from environment variables
URL = os.getenv("HOME_ASSISTANT_URL")
TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

# Validate that required environment variables are set
if not URL or not TOKEN:
    raise ValueError(
        "HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN must be set in the environment")

# Initialize the Home Assistant API client
client = Client(URL, TOKEN)

# Create the MCP server instance (not used directly here but kept for
# integration)
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
        "annotation": None if param.annotation is inspect.Parameter.empty else _safe_repr(
            param.annotation),
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
        if inspect.isroutine(member) or inspect.ismethod(
                member) or inspect.isfunction(member) or callable(member):
            try:
                results.append(_func_to_dict(name, member))
            except (ValueError, TypeError, AttributeError):
                # fallback to minimal entry when introspection fails
                results.append(
                    {"name": name, "signature": None, "params": [], "doc": ""})
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
            if isinstance(
                    p.get("default"), str) and (
                    "token" in pname or "password" in pname):
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


def _build_device_catalogue_template(
        area: Optional[str] = None,
        group_by_areas: bool = False) -> str:
    """Build the Jinja template for device catalogue queries.

    Args:
        area: Specific area name to filter by, or None for all.
        group_by_areas: If True, group devices by areas.

    Returns:
        The Jinja template string.
    """
    if group_by_areas:
        # Template for grouping by areas
        return """
        {% set ns = namespace(area_map={}) %}

        {% for area_id in areas() %}

          {% set device_map = namespace(devices={}) %}

          {% for device_id in area_devices(area_id) %}

            {# Build entity dictionary for this device #}
            {% set entity_map = namespace(entities={}) %}

            {% for entity_id in device_entities(device_id) %}

              {% set entity_map.entities = dict(
                entity_map.entities,
                **{
                  entity_id: {
                    "state": states(entity_id),
                    "friendly_name": state_attr(entity_id, "friendly_name"),
                    "icon": state_attr(entity_id, "icon"),
                    "device_class": state_attr(entity_id, "device_class")
                  }
                }
              ) %}

            {% endfor %}

            {# Add device and its entity data #}
            {% set device_map.devices = dict(
              device_map.devices,
              **{
                device_id: {
                  "name": device_attr(device_id, "name"),
                  "entities": entity_map.entities
                }
              }
            ) %}

          {% endfor %}

          {# Add area and its devices #}
          {% set ns.area_map = dict(
            ns.area_map,
            **{
              area_id: {
                "name": area_name(area_id),
                "devices": device_map.devices
              }
            }
          ) %}

        {% endfor %}

        {{ ns.area_map }}
        """

    if group_by_areas and area:
        # Template for specific area
        return """
        {% set id = area_id('""" + area + """') %}

        {% set device_map = namespace(devices={}) %}

        {% for device_id in area_devices(id) %}

            {# Build entity dictionary for this device #}
            {% set entity_map = namespace(entities={}) %}

            {% for entity_id in device_entities(device_id) %}

            {% set entity_map.entities = dict(
                entity_map.entities,
                **{
                entity_id: {
                    "state": states(entity_id),
                    "friendly_name": state_attr(entity_id, "friendly_name"),
                "icon": state_attr(entity_id, "icon"),
                 "device_class": state_attr(entity_id, "device_class")
                }
                }
            ) %}

            {% endfor %}

            {# Add device and its entity data #}
            {% set device_map.devices = dict(
            device_map.devices,
            **{
                device_id: {
                "name": device_attr(device_id, "name"),
                "entities": entity_map.entities
                }
            }
            ) %}

        {% endfor %}

        {{ device_map.devices }}
        """

    # Flat template for all devices
    return """
    {% set device_map = namespace(devices={}) %}

    {% for device_id in devices() %}

      {# Build entity dictionary for this device #}
      {% set entity_map = namespace(entities={}) %}

      {% for entity_id in device_entities(device_id) %}

        {% set entity_map.entities = dict(
          entity_map.entities,
          **{
            entity_id: {
              "state": states(entity_id),
              "friendly_name": state_attr(entity_id, "friendly_name"),
              "icon": state_attr(entity_id, "icon"),
              "device_class": state_attr(entity_id, "device_class")
              }
            }
        ) %}

      {% endfor %}

      {# Add device and its entity data #}
      {% set device_map.devices = dict(
        device_map.devices,
        **{
          device_id: {
          "name": device_attr(device_id, "name"),
          "entities": entity_map.entities
          }
        }
      ) %}

    {% endfor %}

    {{ device_map }}
    """

@mcp.tool()
def get_client_api() -> str:
    """Returns the Home Assistant client API description as a JSON string.

    This MCP tool exposes metadata about the Home Assistant client and
    its public callable members to MCP consumers.
    """
    api = _extract_client_api(client)
    api = _add_example_values(api)
    safe_api = _sanitize_export(api)
    return json.dumps({"client_api": safe_api}, indent=2, ensure_ascii=False)

@mcp.tool()
def get_device_catalogue_grouped_by_areas() -> str:
    """Return a catalogue of all devices and entities grouped by area from Home Assistant.
    
    This tool provides a snapshot of all the current devices and entities
    available in Home Assistant.
    """
    device_catalogue_query = _build_device_catalogue_template(
        group_by_areas=True)
    try:
        result = json.dumps(
            client.get_rendered_template(device_catalogue_query))
        return result
    except Exception as e:
        print(f"Error occurred while fetching device catalogue: {e}")
        return json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)

@mcp.tool()
def get_device_catalogue() -> str:
    """Return a flat catalogue of all devices and entities from Home Assistant.

    This tool provides a snapshot of all the current devices and entities
    available in Home Assistant without area grouping.
    """
    device_catalogue_query = _build_device_catalogue_template()
    try:
        result = json.dumps(
            client.get_rendered_template(device_catalogue_query))
        return result
    except Exception as e:
        print(f"Error occurred while fetching device catalogue: {e}")
        return json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)

@mcp.tool()
def get_device_catalogue_by_area(area: str) -> str:
    """Return a catalogue of devices and entities filtered by a specific area from Home Assistant.

    This tool provides a snapshot of the current devices and entities
    available in a specified area within Home Assistant.
    """
    device_catalogue_query = _build_device_catalogue_template(area=area)
    try:
        result = json.dumps(
            client.get_rendered_template(device_catalogue_query))
        return result
    except Exception as e:
        print(
            f"Error occurred while fetching device catalogue for area '{area}': {e}")
        return json.dumps({"error": str(e)}, indent=2, ensure_ascii=False)

# Start the server when invoked directly.
if __name__ == "__main__":
    mcp.run()
