"""Slash/plugin command route helpers."""

from __future__ import annotations


def handle_commands_list(handler, *, json_response_fn):
    from api.commands import list_commands

    return json_response_fn(handler, {"commands": list_commands()})


def handle_command_exec(
    handler,
    body,
    *,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
):
    from api.commands import execute_plugin_command

    command = str(body.get("command", "") or "").strip()
    if not command:
        return bad_response_fn(handler, "command is required")
    try:
        return json_response_fn(handler, {"output": execute_plugin_command(command)})
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), 400)
    except KeyError:
        return bad_response_fn(handler, "Plugin command not found", 404)
    except RuntimeError as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 500)
