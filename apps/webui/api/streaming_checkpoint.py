"""Periodic checkpoint runner for WebUI streaming workers."""

from __future__ import annotations

import threading


class StreamingCheckpointRunner:
    """Save pending turn state whenever streaming tool activity advances."""

    def __init__(
        self,
        session,
        *,
        agent_lock,
        checkpoint_activity,
        interval: float = 15,
        logger=None,
        thread_name: str | None = None,
        thread_factory=threading.Thread,
        event_factory=threading.Event,
    ):
        self.session = session
        self.agent_lock = agent_lock
        self.checkpoint_activity = checkpoint_activity
        self.interval = interval
        self.logger = logger
        self.stop_event = event_factory()
        self.last_saved_activity = 0
        self.thread = thread_factory(target=self._run, daemon=True, name=thread_name)

    def start(self):
        self.thread.start()
        return self

    def stop_and_join(self, *, timeout: float = 15) -> None:
        self.stop_event.set()
        self.thread.join(timeout=timeout)

    def save_if_activity_advanced(self) -> bool:
        cur = self.checkpoint_activity[0]
        if cur <= self.last_saved_activity:
            return False
        with self.agent_lock:
            self.session.save(skip_index=True)
        self.last_saved_activity = cur
        return True

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                self.save_if_activity_advanced()
            except Exception as exc:
                if self.logger is not None:
                    self.logger.debug("Periodic checkpoint save failed: %s", exc)


def start_periodic_checkpoint(
    session,
    *,
    agent_lock,
    checkpoint_activity,
    session_id: str,
    logger=None,
    interval: float = 15,
) -> StreamingCheckpointRunner:
    return StreamingCheckpointRunner(
        session,
        agent_lock=agent_lock,
        checkpoint_activity=checkpoint_activity,
        interval=interval,
        logger=logger,
        thread_name=f"ckpt-{session_id[:8]}",
    ).start()


def stop_checkpoint_thread(checkpoint_stop, checkpoint_thread, *, timeout: float = 15) -> None:
    """Stop and join a checkpoint thread if it was started."""
    if checkpoint_stop is not None:
        checkpoint_stop.set()
    if checkpoint_thread is not None:
        checkpoint_thread.join(timeout=timeout)
