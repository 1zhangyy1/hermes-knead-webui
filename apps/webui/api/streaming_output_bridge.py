"""Token, reasoning, and interim assistant callback bridge for WebUI streaming."""

from __future__ import annotations

import time
from typing import Callable

from api.metering import meter


class StreamingOutputBridge:
    """Translate AIAgent output callbacks into WebUI SSE events and live meter updates."""

    def __init__(
        self,
        *,
        stream_id: str,
        session_id: str,
        partial_texts: dict,
        reasoning_texts: dict,
        usage_snapshot: Callable[[], dict],
        put: Callable[[str, dict], None],
        meter_factory: Callable = meter,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.stream_id = stream_id
        self.session_id = session_id
        self.partial_texts = partial_texts
        self.reasoning_texts = reasoning_texts
        self.usage_snapshot = usage_snapshot
        self.put = put
        self.meter_factory = meter_factory
        self.clock = clock
        self._metering_last_emit = self.clock() - 1
        self._metering_output_deltas = 0
        self._metering_reasoning_deltas = 0
        self.token_sent = False
        self.reasoning_text = ''

    def emit_metering(self) -> bool:
        now = self.clock()
        if now - self._metering_last_emit < 0.1:
            return False
        self._metering_last_emit = now
        stats = self.meter_factory().get_stats()
        stats['session_id'] = self.session_id
        stats['usage'] = self.usage_snapshot()
        stats.setdefault('tps_available', False)
        stats.setdefault('estimated', False)
        self.put('metering', stats)
        return True

    def on_token(self, text) -> bool:
        if text is None:
            return False
        text = str(text)
        if self.stream_id in self.partial_texts:
            self.partial_texts[self.stream_id] += text
        self.put('token', {'text': text})
        self.token_sent = True
        self._metering_output_deltas += 1
        self.meter_factory().record_token(self.stream_id, self._metering_output_deltas)
        self.emit_metering()
        return True

    def on_reasoning(self, text) -> str:
        if text is None:
            return ''
        text = str(text)
        if self.stream_id in self.reasoning_texts:
            self.reasoning_texts[self.stream_id] += text
        self.reasoning_text += text
        self.put('reasoning', {'text': text})
        self._metering_reasoning_deltas += 1
        self.meter_factory().record_reasoning(self.stream_id, self._metering_reasoning_deltas)
        self.emit_metering()
        return text

    def on_interim_assistant(self, text, **cb_kwargs) -> bool:
        if text is None:
            return False
        visible = str(text).strip()
        if not visible:
            return False
        self.put('interim_assistant', {
            'text': visible,
            'already_streamed': bool(cb_kwargs.get('already_streamed', False)),
        })
        return True
