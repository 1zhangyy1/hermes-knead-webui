"""Rollback route adapters for the WebUI API."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

from api.helpers import bad, j

logger = logging.getLogger(__name__)


def handle_rollback_list(handler, parsed, *, responder=j, error_responder=bad) -> bool:
    qs = parse_qs(parsed.query)
    workspace = qs.get("workspace", [""])[0]
    if not workspace:
        return error_responder(handler, "workspace query parameter is required")
    try:
        from api.rollback import list_checkpoints

        return responder(handler, list_checkpoints(workspace))
    except ValueError as e:
        return error_responder(handler, str(e))
    except Exception as e:
        logger.exception("rollback/list failed")
        return error_responder(handler, str(e), status=500)


def handle_rollback_diff(handler, parsed, *, responder=j, error_responder=bad) -> bool:
    qs = parse_qs(parsed.query)
    workspace = qs.get("workspace", [""])[0]
    checkpoint = qs.get("checkpoint", [""])[0]
    if not workspace or not checkpoint:
        return error_responder(handler, "workspace and checkpoint query parameters are required")
    try:
        from api.rollback import get_checkpoint_diff

        return responder(handler, get_checkpoint_diff(workspace, checkpoint))
    except ValueError as e:
        return error_responder(handler, str(e))
    except Exception as e:
        logger.exception("rollback/diff failed")
        return error_responder(handler, str(e), status=500)


def handle_rollback_restore(handler, body, *, responder=j, error_responder=bad) -> bool:
    if not body:
        return error_responder(handler, "request body is required")
    workspace = body.get("workspace", "")
    checkpoint = body.get("checkpoint", "")
    if not workspace or not checkpoint:
        return error_responder(handler, "workspace and checkpoint are required")
    try:
        from api.rollback import restore_checkpoint

        return responder(handler, restore_checkpoint(workspace, checkpoint))
    except ValueError as e:
        return error_responder(handler, str(e))
    except Exception as e:
        logger.exception("rollback/restore failed")
        return error_responder(handler, str(e), status=500)
