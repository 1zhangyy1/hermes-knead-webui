from api.streaming_agent_status import emit_compression_status, is_compression_status


def test_is_compression_status_matches_lifecycle_markers():
    assert is_compression_status("lifecycle", "starting preflight compression")
    assert is_compression_status("lifecycle", "Compacting context now")
    assert is_compression_status("lifecycle", "context too large")
    assert not is_compression_status("tool", "context too large")
    assert not is_compression_status("lifecycle", "")


def test_emit_compression_status_puts_transient_sse_payload():
    events = []

    emitted = emit_compression_status(
        "lifecycle",
        "compressing context",
        session_id="sid1",
        put=lambda event, data: events.append((event, data)),
    )

    assert emitted is True
    assert events == [
        (
            "compressing",
            {
                "session_id": "sid1",
                "message": "Auto-compressing context to continue...",
            },
        )
    ]


def test_emit_compression_status_ignores_unrelated_statuses():
    events = []

    emitted = emit_compression_status(
        "lifecycle",
        "running tool",
        session_id="sid1",
        put=lambda event, data: events.append((event, data)),
    )

    assert emitted is False
    assert events == []

