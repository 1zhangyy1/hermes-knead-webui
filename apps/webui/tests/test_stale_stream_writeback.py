import queue
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

import api.config as config
import api.models as models
import api.streaming as streaming
from api.models import Session

WEBUI_ROOT = Path(__file__).parent.parent
STREAMING_SRC = WEBUI_ROOT / "api/streaming.py"
STREAMING_TURN_PIPELINE_SRC = WEBUI_ROOT / "api/streaming_turn_pipeline.py"
STREAMING_COMPLETED_WRITEBACK_SRC = WEBUI_ROOT / "api/streaming_completed_writeback.py"
STREAMING_RECOVERY_SRC = WEBUI_ROOT / "api/streaming_recovery.py"
STREAMING_TURN_WRITEBACK_SRC = WEBUI_ROOT / "api/streaming_turn_writeback.py"


@pytest.fixture(autouse=True)
def _isolate_sessions(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    index_file = session_dir / "_index.json"
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(streaming, "SESSION_DIR", session_dir)
    monkeypatch.setattr(config, "SESSION_INDEX_FILE", index_file, raising=False)
    models.SESSIONS.clear()
    config.STREAMS.clear()
    config.CANCEL_FLAGS.clear()
    config.AGENT_INSTANCES.clear()
    config.SESSION_AGENT_LOCKS.clear()
    yield
    models.SESSIONS.clear()
    config.STREAMS.clear()
    config.CANCEL_FLAGS.clear()
    config.AGENT_INSTANCES.clear()
    config.SESSION_AGENT_LOCKS.clear()


def test_stream_writeback_requires_active_stream_ownership():
    s = Session(session_id="ownership", messages=[])
    s.active_stream_id = "current-stream"

    assert streaming._stream_writeback_is_current(s, "current-stream") is True

    s.active_stream_id = None
    assert streaming._stream_writeback_is_current(s, "current-stream") is False

    s.active_stream_id = "newer-stream"
    assert streaming._stream_writeback_is_current(s, "current-stream") is False


def test_cancel_stream_does_not_append_marker_after_stream_ownership_rotated():
    sid = "rotated_cancel_sid"
    old_stream = "old-stream"
    s = Session(
        session_id=sid,
        title="Rotated stream",
        messages=[{"role": "user", "content": "newer prompt"}],
    )
    s.active_stream_id = "newer-stream"
    s.pending_user_message = "newer prompt"
    s.pending_started_at = 456.0
    s.save()
    models.SESSIONS[sid] = s

    config.STREAMS[old_stream] = queue.Queue()
    config.CANCEL_FLAGS[old_stream] = threading.Event()
    mock_agent = Mock()
    mock_agent.session_id = sid
    mock_agent.interrupt = Mock()
    config.AGENT_INSTANCES[old_stream] = mock_agent

    assert streaming.cancel_stream(old_stream) is True

    assert s.active_stream_id == "newer-stream"
    assert s.pending_user_message == "newer prompt"
    assert [m["content"] for m in s.messages] == ["newer prompt"]
    assert all(m.get("content") != "*Task cancelled.*" for m in s.messages)


def test_success_path_checks_stream_ownership_before_persisting_result():
    src = STREAMING_SRC.read_text(encoding="utf-8")
    pipeline_src = STREAMING_TURN_PIPELINE_SRC.read_text(encoding="utf-8")
    completed_src = STREAMING_COMPLETED_WRITEBACK_SRC.read_text(encoding="utf-8")
    writeback_src = STREAMING_TURN_WRITEBACK_SRC.read_text(encoding="utf-8")
    helper_call = "prepare_success_turn_writeback_fn("
    helper_pos = completed_src.find(helper_call)
    result_merge_pos = completed_src.find("apply_agent_result_to_session_fn(")
    compression_pos = completed_src.find("apply_streaming_context_compression_side_effects_fn(")
    guard = "if not ephemeral and not stream_writeback_is_current(session, stream_id):"

    assert "_run_streaming_turn_pipeline(" in src
    assert "handle_completed_conversation_writeback_fn(" in pipeline_src
    assert helper_pos != -1
    assert result_merge_pos != -1
    assert compression_pos != -1
    assert guard in writeback_src
    assert helper_pos < result_merge_pos
    assert helper_pos < compression_pos


def test_self_heal_retry_success_checks_stream_ownership_before_writeback():
    src = STREAMING_RECOVERY_SRC.read_text(encoding="utf-8")
    start = src.index("def persist_exception_self_heal_result(")
    end = src.rindex("return True")
    block = src[start:end]
    guard = "if not ephemeral and not stream_writeback_is_current(session, stream_id):"

    assert guard in block
    assert block.index(guard) < block.index("apply_agent_result_to_session(")
    assert block.index(guard) < block.index("session.save()")


def test_outer_exception_path_checks_stream_ownership_before_error_writeback():
    src = (WEBUI_ROOT / "api/streaming_error_writeback.py").read_text(encoding="utf-8")
    start = src.index("def emit_and_persist_exception_streaming_error(")
    end = src.index("finalize_product_turn(", start)
    block = src[start:end]
    guard = "if not ephemeral and not stream_writeback_is_current(session, stream_id):"

    assert guard in block
    assert block.index(guard) < block.index("persist_error_message_fn(")
