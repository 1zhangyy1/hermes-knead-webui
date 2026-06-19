"""Dashboard route helpers."""

from __future__ import annotations


def handle_dashboard_status(handler, *, json_response_fn):
    from api import dashboard_probe

    json_response_fn(handler, dashboard_probe.get_dashboard_status())
    return True


def handle_dashboard_config_get(handler, *, json_response_fn, bad_response_fn):
    from api import dashboard_probe

    try:
        json_response_fn(handler, dashboard_probe.get_dashboard_config())
    except ValueError as exc:
        bad_response_fn(handler, str(exc), status=400)
    return True


def handle_dashboard_config_post(
    handler,
    body,
    *,
    json_response_fn,
    bad_response_fn,
    logger,
):
    from api import dashboard_probe

    try:
        json_response_fn(handler, dashboard_probe.save_dashboard_config(body))
    except ValueError as exc:
        bad_response_fn(handler, str(exc), status=400)
    except Exception as exc:
        logger.exception("dashboard config save failed")
        bad_response_fn(handler, str(exc), status=500)
    return True
