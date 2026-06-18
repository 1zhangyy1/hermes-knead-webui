"""Chat steer endpoint helper for WebUI streaming."""

from __future__ import annotations


def handle_chat_steer(handler, body: dict, *, get_session, logger=None) -> bool:
    """Inject a /steer payload into the active agent for a session."""
    from api.helpers import j, bad
    from api import config as cfg

    sid = str((body or {}).get("session_id", "") or "").strip()
    text = str((body or {}).get("text", "") or "").strip()
    if not sid:
        return bad(handler, "session_id required")
    if not text:
        return bad(handler, "text required")

    with cfg.SESSION_AGENT_CACHE_LOCK:
        cached = cfg.SESSION_AGENT_CACHE.get(sid)
    if not cached:
        return j(handler, {"accepted": False, "fallback": "no_cached_agent", "stream_id": None})
    agent = cached[0]
    if not hasattr(agent, "steer"):
        return j(handler, {"accepted": False, "fallback": "agent_lacks_steer", "stream_id": None})

    try:
        session = get_session(sid)
    except KeyError:
        return j(handler, {"accepted": False, "fallback": "session_not_found", "stream_id": None})
    active_stream_id = getattr(session, "active_stream_id", None) or None
    if not active_stream_id:
        return j(handler, {"accepted": False, "fallback": "not_running", "stream_id": None})
    with cfg.STREAMS_LOCK:
        stream_alive = active_stream_id in cfg.STREAMS
    if not stream_alive:
        return j(handler, {"accepted": False, "fallback": "stream_dead", "stream_id": None})

    steer_text = text
    product_context = None
    product_body = body or {}
    try:
        from api.product_context import product_context_request_body

        product_body = product_context_request_body(product_body, session, text)
    except Exception:
        if logger is not None:
            logger.debug("Failed to restore product context body for steer session=%s", sid, exc_info=True)
    if product_body.get("product_id") or product_body.get("productId"):
        try:
            from api.product_context import product_context_from_request, product_ephemeral_prompt

            product_context = product_context_from_request(product_body, workspace=getattr(session, "workspace", None))
            if product_context and str(product_context.get("scope") or "") in {"product_init", "product_builder"}:
                product_prompt = product_ephemeral_prompt(product_context)
                if product_prompt:
                    steer_text = (
                        f"{product_prompt}\n\n"
                        "Steer update for the current running turn:\n"
                        f"{text}"
                    )
        except Exception:
            if logger is not None:
                logger.debug("Failed to attach product context to steer for session=%s", sid, exc_info=True)

    try:
        accepted = bool(agent.steer(steer_text))
    except Exception as exc:
        if logger is not None:
            logger.debug("agent.steer() raised for session=%s: %s", sid, exc)
        return j(handler, {"accepted": False, "fallback": "steer_error", "stream_id": active_stream_id})

    payload = {"accepted": accepted, "fallback": None, "stream_id": active_stream_id}
    if product_context:
        payload["product_scope"] = product_context.get("scope")
    return j(handler, payload)
