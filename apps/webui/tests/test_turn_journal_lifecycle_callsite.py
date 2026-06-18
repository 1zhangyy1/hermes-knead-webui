from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_streaming_appends_worker_started_before_running_phase():
    src = _read("api/streaming.py")
    context_src = _read("api/streaming_worker_context.py")
    startup_src = _read("api/streaming_worker_startup.py")
    journal_src = _read("api/streaming_turn_journal.py")
    run_idx = src.index("def _run_agent_streaming(")
    context_idx = src.index("_initialize_streaming_worker_context(", run_idx)
    startup_idx = src.index("_startup = _prepare_streaming_worker_startup(", run_idx)
    worker_idx = context_src.index("append_worker_started_turn_event_fn(")
    run_state_idx = context_src.index("initialize_run_state_fn(")

    assert context_idx < startup_idx
    assert worker_idx < run_state_idx
    assert 'update_active_run(stream_id, phase="running", session_id=session_id)' in startup_src
    assert '"event": "worker_started"' in journal_src


def test_streaming_appends_assistant_started_before_final_save():
    src = _read("api/streaming_turn_writeback.py")
    block_idx = src.index("def save_completed_turn_and_journal(")
    assistant_idx = src.index("append_assistant_started_turn_event(", block_idx)
    save_idx = src.index("session.save()", assistant_idx)

    assert block_idx < assistant_idx < save_idx


def test_streaming_assistant_started_uses_latest_assistant_message():
    src = _read("api/streaming_turn_journal.py")

    assert "range(len(messages or []) - 1, -1, -1)" in src
    assert '"assistant_message_index": assistant_idx' in src


def test_streaming_appends_completed_after_final_save():
    src = _read("api/streaming_turn_writeback.py")
    helper_idx = src.index("def save_completed_turn_and_journal(")
    save_idx = src.index("session.save()", helper_idx)
    completed_idx = src.index("append_completed_turn_event(", save_idx)

    assert save_idx < completed_idx


def test_streaming_appends_interrupted_on_provider_error_path():
    src = _read("api/streaming.py")
    exception_src = _read("api/streaming_exception_handling.py")
    writeback_src = _read("api/streaming_error_writeback.py")
    err_idx = exception_src.index("print('[webui] stream error:")
    emit_idx = exception_src.index("emit_and_persist_exception_streaming_error_fn(", err_idx)
    callback_idx = exception_src.index("append_interrupted_turn_event=append_interrupted_turn_event", emit_idx)
    interrupted_idx = writeback_src.index("append_interrupted_turn_event(")
    apperror_idx = writeback_src.index("put('apperror'", interrupted_idx)

    assert "_handle_streaming_exception(" in src
    assert err_idx < emit_idx < callback_idx
    assert interrupted_idx < apperror_idx
