"""Post-turn goal evaluation hook for WebUI streaming workers."""

from __future__ import annotations

from typing import Callable


def last_assistant_response_text(messages) -> str:
    """Return the latest assistant response text in API-safe display form."""
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            continue
        content = message.get('content', '')
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get('text') or part.get('content')
                    if text:
                        parts.append(str(text))
            return '\n'.join(parts)
        return str(content or '')
    return ''


def run_post_turn_goal_hook(
    session,
    *,
    session_id: str,
    profile_home,
    goal_related: bool,
    put: Callable[[str, dict], object],
    pending_goal_continuation,
    logger=None,
    has_active_goal_fn: Callable[..., bool] | None = None,
    evaluate_goal_after_turn_fn: Callable[..., dict] | None = None,
) -> dict:
    """Evaluate an active goal and emit follow-up SSE events before ``done``."""
    try:
        if has_active_goal_fn is None or evaluate_goal_after_turn_fn is None:
            from api.goals import evaluate_goal_after_turn, has_active_goal

            has_active_goal_fn = has_active_goal_fn or has_active_goal
            evaluate_goal_after_turn_fn = evaluate_goal_after_turn_fn or evaluate_goal_after_turn

        if not goal_related or not has_active_goal_fn(session_id, profile_home=profile_home):
            decision = {}
        else:
            last_goal_response = last_assistant_response_text(getattr(session, 'messages', None))
            put('goal', {
                'session_id': session_id,
                'state': 'evaluating',
                'message': 'Evaluating goal progress\u2026',
                'message_key': 'goal_evaluating_progress',
            })
            decision = evaluate_goal_after_turn_fn(
                session_id,
                last_goal_response,
                user_initiated=True,
                profile_home=profile_home,
            )

        decision = decision or {}
        goal_message = str(decision.get('message') or '').strip()
        if goal_message:
            put('goal', {
                'session_id': session_id,
                'state': 'continuing' if decision.get('should_continue') else 'idle',
                'message': goal_message,
                'message_key': decision.get('message_key') or ('goal_continuing' if goal_message else ''),
                'message_args': decision.get('message_args') or [],
                'decision': decision,
            })

        if decision.get('should_continue'):
            continuation_prompt = str(decision.get('continuation_prompt') or '').strip()
            if continuation_prompt:
                # #1932: mark this session as pending a goal continuation so
                # the next /chat/start creates a goal-related stream.
                pending_goal_continuation.add(session_id)
                put('goal_continue', {
                    'session_id': session_id,
                    'continuation_prompt': continuation_prompt,
                    'text': continuation_prompt,
                    'message': goal_message,
                    'message_key': decision.get('message_key') or 'goal_continuing',
                    'message_args': decision.get('message_args') or [],
                    'decision': decision,
                })
        return decision
    except Exception as exc:
        if logger is not None:
            logger.debug("Goal continuation hook failed for session %s: %s", session_id, exc)
        return {}
