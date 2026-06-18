import threading

import pytest

from api.streaming_context import TurnStartSnapshot
from api.streaming_turn_start import StreamingTurnInput, prepare_streaming_turn_input


class _Session:
    workspace = "/workspace"
    personality = "careful"

    def __init__(self, calls):
        self.calls = calls

    def save(self, **kwargs):
        self.calls.append(("save", kwargs))


class _CheckpointRunner:
    def __init__(self, calls):
        self.calls = calls
        self.stop_event = object()
        self.thread = object()

    def stop_and_join(self):
        self.calls.append(("stop_and_join", None))


def test_prepare_streaming_turn_input_builds_prompt_snapshot_checkpoint_and_user_message():
    calls = []
    session = _Session(calls)
    agent = object()
    checkpoint_runner = _CheckpointRunner(calls)
    snapshot = TurnStartSnapshot(
        started_at=12.0,
        previous_messages=[{"role": "user", "content": "old"}],
        previous_context_messages=[{"role": "system", "content": "summary"}],
        pre_compression_count=3,
    )

    def configure_prompt(agent_arg, **kwargs):
        calls.append(("configure", agent_arg, kwargs))

    def capture_snapshot(session_arg, agent_arg, msg_text):
        calls.append(("capture", session_arg, agent_arg, msg_text))
        return snapshot

    def start_checkpoint(session_arg, **kwargs):
        calls.append(("checkpoint", session_arg, kwargs))
        return checkpoint_runner

    def drain_notifications(session_id, *, logger):
        calls.append(("drain", session_id, logger))
        return ["done"]

    def merge_notifications(msg_text, notifications):
        calls.append(("merge", msg_text, notifications))
        return "done\n\nhello"

    def build_message(workspace_ctx, msg_text, attachments, workspace, *, cfg):
        calls.append(("build", workspace_ctx, msg_text, attachments, workspace, cfg))
        return {"content": msg_text}

    result = prepare_streaming_turn_input(
        session=session,
        agent=agent,
        msg_text="hello",
        attachments=[{"name": "a.png"}],
        workspace="/workspace",
        config={"mode": "test"},
        product_context={"product": "demo"},
        agent_lock=threading.Lock(),
        checkpoint_activity=[0],
        session_id="sid-1",
        personality_name="careful",
        webui_ephemeral_system_prompt=lambda personality, product=None: "prompt",
        logger="logger",
        workspace_context_prefix_fn=lambda workspace: f"[WS {workspace}]\n",
        build_workspace_system_message_fn=lambda workspace: f"system:{workspace}",
        configure_agent_runtime_prompt_fn=configure_prompt,
        capture_turn_start_snapshot_fn=capture_snapshot,
        start_periodic_checkpoint_fn=start_checkpoint,
        drain_process_notifications_fn=drain_notifications,
        message_text_with_process_notifications_fn=merge_notifications,
        build_native_multimodal_message_fn=build_message,
    )

    assert isinstance(result, StreamingTurnInput)
    assert result.user_message == {"content": "done\n\nhello"}
    assert result.system_message == "system:/workspace"
    assert result.turn_start is snapshot
    assert result.checkpoint_runner is checkpoint_runner
    assert [call[0] for call in calls] == [
        "configure",
        "capture",
        "save",
        "checkpoint",
        "drain",
        "merge",
        "build",
    ]
    assert calls[0][2]["personality_name"] == "careful"
    assert calls[0][2]["product_context"] == {"product": "demo"}
    assert calls[2] == ("save", {"touch_updated_at": True, "skip_index": False})
    assert calls[3][2]["session_id"] == "sid-1"
    assert calls[-1] == (
        "build",
        "[WS /workspace]\n",
        "done\n\nhello",
        [{"name": "a.png"}],
        "/workspace",
        {"mode": "test"},
    )


def test_prepare_streaming_turn_input_stops_checkpoint_when_message_build_fails():
    calls = []

    def build_message(*_args, **_kwargs):
        calls.append(("build", None))
        raise RuntimeError("bad attachment")

    with pytest.raises(RuntimeError, match="bad attachment"):
        prepare_streaming_turn_input(
            session=_Session(calls),
            agent=object(),
            msg_text="hello",
            attachments=[],
            workspace="/workspace",
            config={},
            product_context=None,
            agent_lock=threading.Lock(),
            checkpoint_activity=[0],
            session_id="sid-1",
            personality_name=None,
            webui_ephemeral_system_prompt=lambda personality, product=None: "prompt",
            logger=None,
            workspace_context_prefix_fn=lambda workspace: "",
            build_workspace_system_message_fn=lambda workspace: "system",
            configure_agent_runtime_prompt_fn=lambda *_args, **_kwargs: None,
            capture_turn_start_snapshot_fn=lambda *_args, **_kwargs: TurnStartSnapshot(1, [], [], 0),
            start_periodic_checkpoint_fn=lambda *_args, **_kwargs: _CheckpointRunner(calls),
            drain_process_notifications_fn=lambda *_args, **_kwargs: [],
            message_text_with_process_notifications_fn=lambda msg, _notifications: msg,
            build_native_multimodal_message_fn=build_message,
        )

    assert calls[-2:] == [("build", None), ("stop_and_join", None)]
