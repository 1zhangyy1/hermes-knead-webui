import io

from api.streaming_sse_facade import write_sse_from_facade


class _Handler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.flushed = False

    def flush(self):
        self.flushed = True


def test_write_sse_serializes_event_and_data_without_ascii_escaping():
    handler = _Handler()
    handler.wfile.flush = handler.flush

    write_sse_from_facade(handler, "clarify", {"text": "你好"})

    assert handler.wfile.getvalue().decode("utf-8") == 'event: clarify\ndata: {"text": "你好"}\n\n'
    assert handler.flushed is True
