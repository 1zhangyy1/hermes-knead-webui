from types import SimpleNamespace
from urllib.parse import urlparse

import api.logs_routes as logs_routes


def test_normalize_logs_tail_allows_known_values_only():
    assert logs_routes.normalize_logs_tail("100") == 100
    assert logs_routes.normalize_logs_tail("999999") == logs_routes.LOG_DEFAULT_TAIL
    assert logs_routes.normalize_logs_tail("not-a-number") == logs_routes.LOG_DEFAULT_TAIL


def test_handle_logs_rejects_unknown_files():
    captured = {}

    def bad(_handler, msg, status=400):
        captured["msg"] = msg
        captured["status"] = status
        return True

    handled = logs_routes.handle_logs(
        SimpleNamespace(),
        urlparse("/api/logs?file=../../etc/passwd"),
        error_responder=bad,
    )

    assert handled is True
    assert captured == {"msg": "Unknown log file", "status": 400}


def test_handle_logs_returns_bounded_tail_window(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "agent.log").write_text("\n".join(f"line {i}" for i in range(105)), encoding="utf-8")
    captured = {}

    def respond(_handler, payload, status=200, extra_headers=None):
        captured["payload"] = payload
        captured["status"] = status
        return True

    handled = logs_routes.handle_logs(
        SimpleNamespace(),
        urlparse("/api/logs?file=agent&tail=100"),
        responder=respond,
        hermes_home_factory=lambda: tmp_path,
    )

    assert handled is True
    assert captured["status"] == 200
    payload = captured["payload"]
    assert payload["file"] == "agent"
    assert payload["tail"] == 100
    assert payload["lines"][0] == "line 5"
    assert payload["lines"][-1] == "line 104"
    assert payload["truncated"] is False
