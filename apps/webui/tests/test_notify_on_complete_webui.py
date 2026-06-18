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
    conversation_src = (REPO / "api" / "streaming_conversation_run.py").read_text(encoding="utf-8")
    turn_start_src = (REPO / "api" / "streaming_turn_start.py").read_text(encoding="utf-8")
    process_src = (REPO / "api" / "streaming_process_notifications.py").read_text(encoding="utf-8")

    assert "_turn_input = _prepare_streaming_turn_input(" in src
    assert "_run_agent_conversation_and_handle_post_run(" in src
    assert "process_notifications = drain_process_notifications_fn(session_id, logger=logger)" in turn_start_src
    assert "message_text_with_process_notifications_fn(msg_text, process_notifications)" in turn_start_src
    assert "[*process_notifications, msg_text]" in process_src
    assert "build_native_multimodal_message_fn(" in turn_start_src
    assert "persist_user_message=msg_text" in conversation_src


def test_webui_sets_gateway_session_platform_for_background_watchers():
    src = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
    startup_src = (REPO / "api" / "streaming_worker_startup.py").read_text(encoding="utf-8")
    helper_src = (REPO / "api" / "streaming_runtime_helpers.py").read_text(encoding="utf-8")

    assert "'HERMES_SESSION_PLATFORM': 'webui'" in helper_src
    assert "_startup = _prepare_streaming_worker_startup(" in src
    assert "activation = activate_streaming_profile_runtime_fn(" in startup_src
    assert "_thread_env = build_thread_env_fn(" in helper_src
    assert "os.environ['HERMES_SESSION_PLATFORM'] = 'webui'" in helper_src
    assert "'HERMES_SESSION_PLATFORM'" in helper_src
    assert "runtime_env_snapshot" in startup_src
    assert "old_runtime_env = _startup.runtime_env_snapshot" in src
    assert "os.environ.pop(key, None)" in helper_src
