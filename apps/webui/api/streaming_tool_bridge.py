"""Live tool callback bridge for WebUI streaming."""

from __future__ import annotations

import json
from typing import Callable


class StreamingToolEventBridge:
    """Translate AIAgent tool callbacks into WebUI SSE events and live state."""

    def __init__(
        self,
        *,
        stream_id: str,
        session_id: str,
        live_tool_calls: list,
        shared_live_tool_calls: dict,
        checkpoint_activity: list,
        seen_tool_call_ids: set,
        put: Callable[[str, dict], None],
        emit_reasoning: Callable[[str], None],
        emit_metering_snapshot: Callable[[], None],
        bump_live_prompt_estimate: Callable[[list], int],
        tool_result_snippet: Callable[[object], str],
    ):
        self.stream_id = stream_id
        self.session_id = session_id
        self.live_tool_calls = live_tool_calls
        self.shared_live_tool_calls = shared_live_tool_calls
        self.checkpoint_activity = checkpoint_activity
        self.seen_tool_call_ids = seen_tool_call_ids
        self.put = put
        self.emit_reasoning = emit_reasoning
        self.emit_metering_snapshot = emit_metering_snapshot
        self.bump_live_prompt_estimate = bump_live_prompt_estimate
        self.tool_result_snippet = tool_result_snippet

    def record_live_tool_start(self, tool_call_id, name, args):
        if not tool_call_id or tool_call_id in self.seen_tool_call_ids:
            return
        self.seen_tool_call_ids.add(tool_call_id)
        _tool_call = {
            'id': tool_call_id,
            'type': 'function',
            'function': {
                'name': str(name or ''),
                'arguments': json.dumps(args if isinstance(args, dict) else {}, ensure_ascii=False, sort_keys=True),
            },
        }
        self.bump_live_prompt_estimate([{
            'role': 'assistant',
            'content': '',
            'tool_calls': [_tool_call],
        }])

    def record_live_tool_complete(self, tool_call_id, name, function_result):
        if not tool_call_id:
            return
        _result_text = self.tool_result_snippet(function_result)
        self.bump_live_prompt_estimate([{
            'role': 'tool',
            'name': str(name or ''),
            'tool_call_id': tool_call_id,
            'content': _result_text,
        }])

    def on_tool_start(self, tool_call_id, name, args):
        self.record_live_tool_start(tool_call_id, name, args)
        self.emit_metering_snapshot()

    def on_tool_complete(self, tool_call_id, name, args, function_result):
        self.record_live_tool_complete(tool_call_id, name, function_result)
        self.emit_metering_snapshot()

    def on_tool(self, *cb_args, **cb_kwargs):
        event_type, name, preview, args = self._parse_callback_args(cb_args)

        if event_type in ('reasoning.available', '_thinking'):
            reason_text = preview if event_type == 'reasoning.available' else name
            if reason_text:
                self.emit_reasoning(str(reason_text))
            return

        args_snap = self._args_snapshot(args)

        if event_type in (None, 'tool.started'):
            self._append_live_tool_started(name, args)
            self.put('tool', {
                'event_type': event_type or 'tool.started',
                'name': name,
                'preview': preview,
                'args': args_snap,
            })
            self.emit_metering_snapshot()
            self._emit_pending_approval_if_present()
            return

        if event_type == 'tool.completed':
            self._mark_live_tool_completed(name, cb_kwargs)
            self.checkpoint_activity[0] += 1
            self.put('tool_complete', {
                'event_type': event_type,
                'name': name,
                'preview': preview,
                'args': args_snap,
                'duration': cb_kwargs.get('duration'),
                'is_error': bool(cb_kwargs.get('is_error', False)),
            })
            self.emit_metering_snapshot()

    @staticmethod
    def _parse_callback_args(cb_args):
        event_type = None
        name = None
        preview = None
        args = None

        if len(cb_args) >= 4:
            event_type, name, preview, args = cb_args[:4]
        elif len(cb_args) == 3:
            name, preview, args = cb_args
            event_type = 'tool.started'
        elif len(cb_args) == 2:
            event_type, name = cb_args
        elif len(cb_args) == 1:
            name = cb_args[0]
            event_type = 'tool.started'
        return event_type, name, preview, args

    @staticmethod
    def _args_snapshot(args):
        args_snap = {}
        if isinstance(args, dict):
            for k, v in list(args.items())[:4]:
                s2 = str(v)
                args_snap[k] = s2[:120] + ('...' if len(s2) > 120 else '')
        return args_snap

    def _append_live_tool_started(self, name, args):
        tool_args = args if isinstance(args, dict) else {}
        self.live_tool_calls.append({
            'name': name,
            'args': tool_args,
        })
        if self.stream_id in self.shared_live_tool_calls:
            self.shared_live_tool_calls[self.stream_id].append({
                'name': name,
                'args': tool_args,
                'done': False,
            })

    def _mark_live_tool_completed(self, name, cb_kwargs):
        for live_tc in reversed(self.live_tool_calls):
            if live_tc.get('done'):
                continue
            if not name or live_tc.get('name') == name:
                live_tc['done'] = True
                live_tc['duration'] = cb_kwargs.get('duration')
                live_tc['is_error'] = bool(cb_kwargs.get('is_error', False))
                break

        if self.stream_id in self.shared_live_tool_calls:
            for shared_tc in reversed(self.shared_live_tool_calls[self.stream_id]):
                if shared_tc.get('done'):
                    continue
                if not name or shared_tc.get('name') == name:
                    shared_tc['done'] = True
                    shared_tc['duration'] = cb_kwargs.get('duration')
                    shared_tc['is_error'] = bool(cb_kwargs.get('is_error', False))
                    break

    def _emit_pending_approval_if_present(self):
        try:
            from tools.approval import has_pending as _has_pending, _pending, _lock
            if _has_pending(self.session_id):
                with _lock:
                    p = dict(_pending.get(self.session_id, {}))
                if p:
                    self.put('approval', p)
        except ImportError:
            pass

