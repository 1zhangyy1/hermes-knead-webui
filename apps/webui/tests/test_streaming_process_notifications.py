import queue
import threading
from types import SimpleNamespace

from api.streaming_process_notifications import (
    drain_webui_process_notifications,
    format_process_notification,
    mark_process_completion_consumed,
)


class _Registry:
    def __init__(self):
        self.completion_queue = queue.Queue()
        self._lock = threading.Lock()
        self._completion_consumed = set()
        self.procs = {}

    def is_completion_consumed(self, process_id):
        return process_id in self._completion_consumed

    def get(self, process_id):
        return self.procs.get(process_id)


def test_format_process_notification_truncates_large_output():
    text = "x" * 4100

    notification = format_process_notification({
        "type": "completion",
        "session_id": "proc1",
        "command": "npm test",
        "exit_code": 0,
        "output": text,
    })

    assert "Background process proc1 completed" in notification
    assert "Command: npm test" in notification
    assert "... (truncated)" in notification
    assert len(notification) < len(text) + 200


def test_drain_process_notifications_only_delivers_matching_session_and_requeues_others():
    registry = _Registry()
    registry.procs["match"] = SimpleNamespace(session_key="sid1")
    registry.procs["other"] = SimpleNamespace(session_key="sid2")
    registry.completion_queue.put({
        "type": "completion",
        "session_id": "other",
        "command": "sleep 1",
        "exit_code": 0,
        "output": "other done",
    })
    registry.completion_queue.put({
        "type": "completion",
        "session_id": "match",
        "command": "echo ok",
        "exit_code": 0,
        "output": "ok",
    })

    notifications = drain_webui_process_notifications("sid1", process_registry=registry)

    assert len(notifications) == 1
    assert "echo ok" in notifications[0]
    assert registry._completion_consumed == {"match"}
    requeued = registry.completion_queue.get_nowait()
    assert requeued["session_id"] == "other"
    assert registry.completion_queue.empty()


def test_mark_process_completion_consumed_is_best_effort():
    registry = _Registry()

    mark_process_completion_consumed(registry, "proc1")

    assert registry._completion_consumed == {"proc1"}

