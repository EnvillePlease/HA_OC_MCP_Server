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
    return {
        "name": param.name,
        "kind": param.kind.name,
        "default": None if param.default is inspect._empty else param.default,
        "annotation": None if param.annotation is inspect._empty else _safe_repr(param.annotation),
    }

def _safe_repr(obj: Any) -> str:
    try:
        return repr(obj)
    except Exception:
        return type(obj).__name__

def _func_to_dict(name: str, func: Any) -> dict:
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
    except Exception:
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

def _extract_client_api(obj) -> list:
    results = []
    for name, member in inspect.getmembers(obj):
        if name.startswith("_"):
            continue
        # Prefer callables/methods
        if inspect.isroutine(member) or inspect.ismethod(member) or inspect.isfunction(member) or callable(member):
            try:
                results.append(_func_to_dict(name, member))
            except Exception:
                # fallback to minimal entry
                results.append({"name": name, "signature": None, "params": [], "doc": ""})
            continue
        # Non-callable attribute: include type and short repr
        try:
            value_repr = repr(member)
        except Exception:
            value_repr = "<unrepresentable>"
        results.append({
            "name": name,
            "attr_type": type(member).__name__,
            "value_repr": value_repr[:200],
            "doc": (inspect.getdoc(member) or "").splitlines()[:3]
        })
    return results

def _add_example_values(api_list: list[dict]) -> list[dict]:
    for item in api_list:
        examples = []
        for p in item.get("params", []):
            pname = p["name"].lower()
            ann = (p.get("annotation") or "").lower()
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
            else:
                example = "example_value"
            # redact defaults that may contain tokens
            if isinstance(p.get("default"), str) and ("token" in pname or "password" in pname):
                p["default"] = "<REDACTED>"
            examples.append({p["name"]: example})
        item["examples"] = examples
    return api_list

# Ensure we do not leak sensitive environment values
def _sanitize_export(data):
    sensitive_keys = {"HOME_ASSISTANT_TOKEN", "TOKEN", "PASSWORD", "API_KEY"}
    # Convert to JSON-safe structure and ensure no raw token values are present
    j = json.dumps(data, default=str)
    for key in sensitive_keys:
        if key in j:
            j = j.replace(os.getenv(key, ""), "<REDACTED>")
    return json.loads(j)

@mcp.tool()
def get_client_api():
    """Returns the Home Assistant client API description."""
    # Build the API description
    api = _extract_client_api(client)
    api = _add_example_values(api)

    safe_api = _sanitize_export(api)

    # Output JSON to stdout (MCP expects stdout)
    return (json.dumps({"client_api": safe_api}, indent=2, ensure_ascii=False))

# Start the server
if __name__ == "__main__":
    mcp.run()
