"""Gateway notification registration for WebUI streaming turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class GatewayNotificationRegistrations:
    unregister_approval: Callable[[str], object] | None = None
    approval_registered: bool = False
    unregister_clarify: Callable[[str], object] | None = None
    clarify_registered: bool = False
    logger: object | None = None

    def unregister(self, session_id: str) -> None:
        """Unregister callbacks and unblock any pending gateway waits."""
        if self.approval_registered and self.unregister_approval is not None:
            try:
                self.unregister_approval(session_id)
            except Exception:
                if self.logger is not None:
                    self.logger.debug("Failed to unregister approval callback")
        if self.clarify_registered and self.unregister_clarify is not None:
            try:
                self.unregister_clarify(session_id)
            except Exception:
                if self.logger is not None:
                    self.logger.debug("Failed to unregister clarify callback")


def register_streaming_gateway_notifications(
    session_id: str,
    *,
    put,
    logger=None,
) -> GatewayNotificationRegistrations:
    """Register approval/clarify gateway callbacks for a streaming turn."""
    registrations = GatewayNotificationRegistrations(logger=logger)
    try:
        from tools.approval import (
            register_gateway_notify as register_approval_notify,
            unregister_gateway_notify as unregister_approval_notify,
        )

        def approval_notify_cb(approval_data):
            put('approval', approval_data)

        register_approval_notify(session_id, approval_notify_cb)
        registrations.unregister_approval = unregister_approval_notify
        registrations.approval_registered = True
    except ImportError:
        if logger is not None:
            logger.debug("Approval module not available, falling back to polling")

    try:
        from api.clarify import (
            register_gateway_notify as register_clarify_notify,
            unregister_gateway_notify as unregister_clarify_notify,
        )

        def clarify_notify_cb(clarify_data):
            put('clarify', clarify_data)

        register_clarify_notify(session_id, clarify_notify_cb)
        registrations.unregister_clarify = unregister_clarify_notify
        registrations.clarify_registered = True
    except ImportError:
        if logger is not None:
            logger.debug("Clarify module not available, falling back to polling")

    return registrations
