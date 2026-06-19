"""MCP management helpers for the WebUI route layer."""

from __future__ import annotations

import re
from urllib.parse import unquote

from api.helpers import _redact_text, bad, j


def mask_secrets(obj):
    """Mask sensitive values in env vars and headers."""
    if not isinstance(obj, dict):
        return obj
    sensitive = ("auth", "token", "key", "secret", "password", "credential")
    masked = {}
    for k, v in obj.items():
        if isinstance(v, str) and any(s in k.lower() for s in sensitive):
            masked[k] = "••••••"
        elif isinstance(v, dict):
            masked[k] = mask_secrets(v)
        else:
            masked[k] = v
    return masked


def parse_mcp_enabled(value) -> bool:
    """Parse Hermes MCP ``enabled`` values without raising on bad config."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return True


def mcp_runtime_status_by_name() -> dict[str, dict]:
    """Return already-known MCP runtime status without starting servers."""
    try:
        from tools.mcp_tool import get_mcp_status

        statuses = get_mcp_status()
    except Exception:
        return {}
    if not isinstance(statuses, list):
        return {}
    return {
        str(entry.get("name")): entry
        for entry in statuses
        if isinstance(entry, dict) and entry.get("name")
    }


def server_summary(name, cfg, runtime_status=None):
    """Return a safe summary of an MCP server config."""
    runtime_status = runtime_status if isinstance(runtime_status, dict) else {}
    out = {"name": name}
    if not isinstance(cfg, dict):
        out.update({
            "transport": "invalid",
            "timeout": 120,
            "connect_timeout": 60,
            "enabled": False,
            "active": False,
            "status": "invalid_config",
            "tool_count": None,
        })
        return out

    enabled = parse_mcp_enabled(cfg.get("enabled", True))
    connected = bool(runtime_status.get("connected")) if enabled else False
    if "url" in cfg:
        out["transport"] = "http"
        if "headers" in cfg:
            out["headers"] = mask_secrets(cfg["headers"])
        out["url"] = cfg["url"]
    elif "command" in cfg:
        out["transport"] = "stdio"
        out["command"] = cfg.get("command", "")
        out["args"] = cfg.get("args", [])
        if "env" in cfg:
            out["env"] = mask_secrets(cfg["env"])
    else:
        out["transport"] = "invalid"
        enabled = False
        connected = False

    out["timeout"] = cfg.get("timeout", 120)
    out["connect_timeout"] = cfg.get("connect_timeout", 60)
    out["enabled"] = enabled
    out["active"] = connected
    if out["transport"] == "invalid":
        out["status"] = "invalid_config"
    elif not enabled:
        out["status"] = "disabled"
    elif connected:
        out["status"] = "active"
    else:
        out["status"] = "configured"
    out["tool_count"] = runtime_status.get("tools") if runtime_status else None
    return out


def mcp_safe_display_text(value, *, limit: int) -> str:
    """Return redacted, bounded MCP text safe for WebUI inventory rows."""
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    value = _redact_text(value).strip()
    value = re.sub(r"Authorization:\s*Bearer\s+\S+", "[REDACTED CREDENTIAL]", value, flags=re.I)
    if len(value) > limit:
        value = value[: max(0, limit - 1)].rstrip() + "..."
    return value


def mcp_schema_type(schema) -> str:
    """Return a compact, non-sensitive display type for a JSON schema node."""
    if not isinstance(schema, dict):
        return "unknown"
    typ = schema.get("type")
    if isinstance(typ, list):
        typ = "/".join(str(t) for t in typ if t)
    if isinstance(typ, str) and typ:
        return typ
    for composite in ("anyOf", "oneOf", "allOf"):
        if isinstance(schema.get(composite), list) and schema[composite]:
            return composite
    if "enum" in schema:
        return "enum"
    return "unknown"


def mcp_schema_summary(schema, *, limit: int = 12) -> list[dict]:
    """Summarize an MCP input schema without exposing raw defaults/examples."""
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required = schema.get("required")
    required_names = set(required) if isinstance(required, list) else set()
    out = []
    for name, prop in properties.items():
        if len(out) >= limit:
            break
        if not isinstance(name, str):
            continue
        prop = prop if isinstance(prop, dict) else {}
        desc = prop.get("description", "")
        if not isinstance(desc, str):
            desc = ""
        desc = mcp_safe_display_text(desc, limit=180)
        out.append({
            "name": name,
            "type": mcp_schema_type(prop),
            "required": name in required_names,
            "description": desc,
        })
    return out


def mcp_tool_schema_from_payload(tool):
    if not isinstance(tool, dict):
        return {}
    for key in ("parameters", "inputSchema", "input_schema", "schema"):
        value = tool.get(key)
        if isinstance(value, dict):
            if key == "schema" and isinstance(value.get("parameters"), dict):
                return value["parameters"]
            return value
    return {}


def mcp_tool_summary(name, tool, server_summary_payload):
    """Return a safe global inventory row for one MCP tool."""
    server_summary_payload = server_summary_payload if isinstance(server_summary_payload, dict) else {}
    if isinstance(tool, str):
        tool = {"name": tool}
    elif not isinstance(tool, dict):
        tool = {}
    tool_name = str(tool.get("name") or name or "")
    description = tool.get("description") or ""
    if not isinstance(description, str):
        description = str(description)
    description = mcp_safe_display_text(description, limit=360)
    return {
        "name": tool_name,
        "server": str(server_summary_payload.get("name") or ""),
        "description": description,
        "active": bool(server_summary_payload.get("active")),
        "enabled": bool(server_summary_payload.get("enabled")),
        "status": server_summary_payload.get("status") or "unknown",
        "schema_summary": mcp_schema_summary(mcp_tool_schema_from_payload(tool)),
    }


def mcp_tools_from_runtime_status(runtime_by_name, server_summaries):
    """Read detailed MCP tool payloads from runtime status when available."""
    tools = []
    if not isinstance(runtime_by_name, dict):
        return tools
    for server_name, runtime in runtime_by_name.items():
        if not isinstance(runtime, dict):
            continue
        raw_tools = runtime.get("tools")
        if not isinstance(raw_tools, list):
            raw_tools = runtime.get("tool_schemas")
        if not isinstance(raw_tools, list):
            continue
        summary_payload = server_summaries.get(str(server_name), {"name": str(server_name)})
        for index, tool in enumerate(raw_tools):
            fallback_name = f"{server_name}:{index}"
            summary = mcp_tool_summary(fallback_name, tool, summary_payload)
            if summary["name"]:
                tools.append(summary)
    return tools


def mcp_tools_from_registry(server_summaries):
    """Read already-registered MCP tool schemas without probing MCP servers."""
    try:
        from tools.registry import registry
    except Exception:
        return []
    tools = []
    try:
        names = registry.get_all_tool_names()
    except Exception:
        return []
    for tool_name in names:
        try:
            toolset = registry.get_toolset_for_tool(tool_name)
        except Exception:
            continue
        if not isinstance(toolset, str) or not toolset.startswith("mcp-"):
            continue
        server_name = toolset[len("mcp-"):]
        schema = registry.get_schema(tool_name) or {}
        summary_payload = server_summaries.get(server_name, {
            "name": server_name,
            "enabled": True,
            "active": False,
            "status": "configured",
        })
        tools.append(mcp_tool_summary(tool_name, schema, summary_payload))
    return tools


def handle_mcp_tools_list(
    handler,
    *,
    get_config_fn,
    runtime_status_fn=mcp_runtime_status_by_name,
    responder=j,
):
    """List known MCP tools from already-available runtime inventory only."""
    cfg = get_config_fn()
    servers = cfg.get("mcp_servers", {})
    if not isinstance(servers, dict):
        servers = {}
    runtime = runtime_status_fn()
    server_summaries = {
        str(name): server_summary(str(name), scfg, runtime.get(str(name)))
        for name, scfg in servers.items()
    }
    tools = mcp_tools_from_runtime_status(runtime, server_summaries)
    source = "mcp_runtime_status"
    if not tools:
        tools = mcp_tools_from_registry(server_summaries)
        source = "tool_registry" if tools else "none"
    tools.sort(key=lambda row: (row.get("server", ""), row.get("name", "")))
    unavailable_servers = [
        summary["name"] for summary in server_summaries.values()
        if summary.get("enabled") and not summary.get("active")
    ]
    return responder(handler, {
        "tools": tools,
        "total": len(tools),
        "source": source,
        "inventory_scope": "already_known_runtime_only",
        "unavailable_servers": unavailable_servers,
    })


def handle_mcp_servers_list(
    handler,
    *,
    get_config_fn,
    runtime_status_fn=mcp_runtime_status_by_name,
    responder=j,
):
    """List configured MCP servers with safe, read-only runtime visibility."""
    cfg = get_config_fn()
    servers = cfg.get("mcp_servers", {})
    if not isinstance(servers, dict):
        servers = {}
    runtime = runtime_status_fn()
    result = [
        server_summary(name, scfg, runtime.get(str(name)))
        for name, scfg in servers.items()
    ]
    return responder(handler, {
        "servers": result,
        "toggle_supported": False,
        "reload_required": True,
    })


def handle_mcp_server_delete(
    handler,
    name,
    *,
    get_config_fn,
    save_config_fn,
    get_config_path_fn,
    reload_config_fn,
    responder=j,
    error_responder=bad,
):
    """Delete an MCP server by name."""
    name = unquote(name)
    if not name:
        return error_responder(handler, "name is required")
    cfg = get_config_fn()
    servers = cfg.get("mcp_servers", {})
    if not isinstance(servers, dict):
        servers = {}
    if name not in servers:
        return error_responder(handler, f"MCP server '{name}' not found", 404)
    del servers[name]
    cfg["mcp_servers"] = servers
    save_config_fn(get_config_path_fn(), cfg)
    reload_config_fn()
    return responder(handler, {"ok": True, "deleted": name})


MASKED_PLACEHOLDER = "••••••"


def strip_masked_values(submitted, existing):
    """Remove masked placeholder values from submitted dict, keeping originals."""
    if not isinstance(submitted, dict) or not isinstance(existing, dict):
        return submitted
    cleaned = {}
    for k, v in submitted.items():
        if isinstance(v, str) and v == MASKED_PLACEHOLDER:
            if k in existing and isinstance(existing[k], str):
                cleaned[k] = existing[k]
                continue
        elif isinstance(v, dict) and k in existing and isinstance(existing[k], dict):
            cleaned[k] = strip_masked_values(v, existing[k])
        else:
            cleaned[k] = v
    return cleaned


def handle_mcp_server_update(
    handler,
    name,
    body,
    *,
    get_config_fn,
    save_config_fn,
    get_config_path_fn,
    reload_config_fn,
    responder=j,
    error_responder=bad,
):
    """Add or update an MCP server."""
    name = unquote(name)
    if not name:
        return error_responder(handler, "name is required")
    server_cfg = {}
    cfg = get_config_fn()
    servers = cfg.get("mcp_servers", {})
    if not isinstance(servers, dict):
        servers = {}
    existing_cfg = servers.get(name, {})
    if body.get("url"):
        server_cfg["url"] = body["url"].strip()
        if body.get("headers"):
            server_cfg["headers"] = strip_masked_values(body["headers"], existing_cfg.get("headers", {}))
    elif body.get("command"):
        server_cfg["command"] = body["command"].strip()
        if body.get("args"):
            server_cfg["args"] = body["args"] if isinstance(body["args"], list) else [body["args"]]
        if body.get("env"):
            server_cfg["env"] = strip_masked_values(body["env"], existing_cfg.get("env", {}))
    else:
        return error_responder(handler, "url or command is required")
    if body.get("timeout") is not None:
        try:
            server_cfg["timeout"] = int(body["timeout"])
        except (ValueError, TypeError):
            pass
    servers[name] = server_cfg
    cfg["mcp_servers"] = servers
    save_config_fn(get_config_path_fn(), cfg)
    reload_config_fn()
    return responder(handler, {"ok": True, "server": server_summary(name, server_cfg)})
