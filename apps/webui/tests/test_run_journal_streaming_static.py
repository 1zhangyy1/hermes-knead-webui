from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_streaming_initializes_one_run_journal_writer_per_stream():
    src = (REPO / "api" / "streaming.py").read_text(encoding="utf-8")
    context_src = (REPO / "api" / "streaming_worker_context.py").read_text(encoding="utf-8")
    run_state_src = (REPO / "api" / "streaming_run_state.py").read_text(encoding="utf-8")
    context_call_idx = src.index("_initialize_streaming_worker_context(")
    register_idx = context_src.index("register_active_run_fn(")
    writer_idx = context_src.index("run_journal_factory(session_id, stream_id)", register_idx)
    init_idx = context_src.index("initialize_run_state_fn(", writer_idx)
    cancel_idx = run_state_src.index("cancel_event = event_factory()")
    stream_register_idx = run_state_src.index("cancel_flags[stream_id] = cancel_event", cancel_idx)
    sink_idx = run_state_src.index("event_sink = event_sink_factory(", stream_register_idx)

    assert "from api.run_journal import RunJournalWriter" in context_src
    assert context_call_idx != -1
    assert register_idx < writer_idx < init_idx
    assert cancel_idx < stream_register_idx < sink_idx


def test_streaming_journals_sse_events_before_queue_delivery():
    src = (REPO / "api" / "streaming_event_sink.py").read_text(encoding="utf-8")
    put_idx = src.index("def put(self, event, data):")
    journal_idx = src.index("run_journal.append_sse_event(event, data)", put_idx)
    # Stage-364 maintainer fix: put() now pushes 3-tuples (event, data, event_id)
    # so the SSE consumer can emit `id:` on live frames. Accept either shape
    # so this test survives both the v0.51.71 in-flight fix and a future revert.
    try:
        queue_idx = src.index("q.put_nowait((event, data, event_id))", put_idx)
    except ValueError:
        queue_idx = src.index("q.put_nowait((event, data))", put_idx)
    block = src[put_idx:queue_idx]

    assert put_idx < journal_idx < queue_idx
    assert "Failed to append run journal event" in block
