from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_streaming_appends_worker_started_before_running_phase():
    src = _read("api/streaming.py")
    journal_src = _read("api/streaming_turn_journal.py")
    run_idx = src.index("def _run_agent_streaming(")
    worker_idx = src.index("_append_worker_started_turn_event(", run_idx)
    running_idx = src.index('update_active_run(stream_id, phase="running"', run_idx)

    assert worker_idx < running_idx
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
    writeback_src = _read("api/streaming_error_writeback.py")
    err_idx = src.index("print('[webui] stream error:")
    emit_idx = src.index("_emit_and_persist_exception_streaming_error(", err_idx)
    callback_idx = src.index("append_interrupted_turn_event=_append_interrupted_turn_event", emit_idx)
    interrupted_idx = writeback_src.index("append_interrupted_turn_event(")
    apperror_idx = writeback_src.index("put('apperror'", interrupted_idx)

    assert err_idx < emit_idx < callback_idx
    assert interrupted_idx < apperror_idx
