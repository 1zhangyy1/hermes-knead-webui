from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_webui_drains_only_matching_background_completion_events():
    streaming_src = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
    process_src = (REPO / "api" / "streaming_process_notifications.py").read_text(encoding="utf-8")

    assert "def _drain_webui_process_notifications(session_id: str)" in streaming_src
    assert "_drain_webui_process_notifications_impl(session_id, logger=logger)" in streaming_src
    assert "from tools.process_registry import process_registry" in process_src
    assert "proc = process_registry.get(evt_sid)" in process_src
    assert "getattr(proc, 'session_key', None) != session_id" in process_src
    assert "skipped_events.append(evt)" in process_src
    assert "completion_queue.put(evt)" in process_src


def test_webui_injects_process_notifications_without_persisting_them_as_user_text():
    src = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
    process_src = (REPO / "api" / "streaming_process_notifications.py").read_text(encoding="utf-8")

    assert "_process_notifications = _drain_webui_process_notifications(session_id)" in src
    assert "_message_text_with_process_notifications(msg_text, _process_notifications)" in src
    assert "[*process_notifications, msg_text]" in process_src
    assert "_build_native_multimodal_message(workspace_ctx, _agent_msg_text" in src
    assert "persist_user_message=msg_text" in src


def test_webui_sets_gateway_session_platform_for_background_watchers():
    src = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
    helper_src = (REPO / "api" / "streaming_runtime_helpers.py").read_text(encoding="utf-8")

    assert "'HERMES_SESSION_PLATFORM': 'webui'" in helper_src
    assert "_thread_env = _build_agent_thread_env(" in src
    assert "os.environ['HERMES_SESSION_PLATFORM'] = 'webui'" in src
    assert "old_session_platform = os.environ.get('HERMES_SESSION_PLATFORM')" in src
    assert "'HERMES_SESSION_PLATFORM': old_session_platform" in src
    assert "os.environ.pop(key, None)" in helper_src
