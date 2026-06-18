from types import SimpleNamespace

import api.streaming as streaming
import api.streaming_worker_pipeline_facade as facade


def test_streaming_worker_pipeline_facade_keeps_stream_local_callbacks(monkeypatch):
    captured = {}

    def fake_run_streaming_turn_pipeline(**kwargs):
        captured.update(kwargs)
        return "pipeline-result"

    def finalize_product_turn(**_kwargs):
        return None

    def put_cancel():
        return None

    monkeypatch.setattr(facade, "run_streaming_turn_pipeline", fake_run_streaming_turn_pipeline)

    result = facade.run_streaming_turn_pipeline_from_facade(
        agent_setup=SimpleNamespace(agent="agent"),
        session=SimpleNamespace(),
        session_id="sid",
        stream_id="stream",
        msg_text="hello",
        attachments=[],
        workspace="/tmp",
        product_context=None,
        model="model",
        profile_home="/profile",
        resolved_profile_name="default",
        run_state=SimpleNamespace(),
        cancel_event=SimpleNamespace(),
        agent_lock=SimpleNamespace(),
        ephemeral=False,
        goal_related=True,
        put=lambda *_args, **_kwargs: None,
        finalize_product_turn=finalize_product_turn,
        put_cancel=put_cancel,
        runtime_state={},
        checkpoint_state={},
    )

    assert result == "pipeline-result"
    assert captured["finalize_product_turn"] is finalize_product_turn
    assert captured["put_cancel"] is put_cancel
    assert captured["pending_goal_continuation"] is streaming.PENDING_GOAL_CONTINUATION
    assert captured["sanitize_messages_for_api"] is streaming._sanitize_messages_for_api
