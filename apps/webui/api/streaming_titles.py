"""Title, transcript text, and workspace-prefix helpers for streaming."""

from __future__ import annotations

import re
from typing import Callable


WORKSPACE_PREFIX_RE = re.compile(r'^\s*\[Workspace::v1:\s*(?:\\.|[^\]\\])+\]\s*')
LEGACY_WORKSPACE_PREFIX_RE = re.compile(r'^\s*\[Workspace:[^\]]+\]\s*')
WORKSPACE_PREFIX_ANY_RE = re.compile(r'\[Workspace::v1:\s*(?:\\.|[^\]\\])+\]\s*')
LEGACY_WORKSPACE_PREFIX_ANY_RE = re.compile(r'\[Workspace:[^\]]+\]\s*')


def strip_thinking_markup(text: str) -> str:
    """Remove common reasoning/thinking wrappers from model text."""
    if not text:
        return ''
    s = str(text)
    s = re.sub(r'^\s*<think>.*?</think>\s*', ' ', s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r'^\s*<\|channel\|?>thought\n?.*?<channel\|>\s*', ' ', s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r'^\s*<\|turn\|>thinking\n.*?<turn\|>\s*', ' ', s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r'^\s*(the|ther)\s+user\s+is\s+asking[^\n]*(?:\n|$)', ' ', s, flags=re.IGNORECASE)
    s = re.sub(
        r"^\s*(?:here(?:'s| is) (?:a |my )?(?:thinking|thought) (?:process|trace|through)\b[^\n]*\n?"
        r"|let me (?:think|work|reason|analyze|walk) (?:through|about|this|step)\b[^\n]*\n?"
        r"|i(?:'ll| will) (?:think|work|reason|analyze|break this down)\b[^\n]*\n?"
        r"|(?:okay|alright|sure|of course),?\s+let me\b[^\n]*\n?)",
        ' ', s, flags=re.IGNORECASE
    )
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def sanitize_generated_title(text: str) -> str:
    """Sanitize LLM-generated title text before persisting to session."""
    s = strip_thinking_markup(text or '')
    s = re.sub(
        r'^\s*(?:[*_`~]+\s*)?(?:session\s+title|title)\s*:\s*(?:[*_`~]+\s*)?',
        '',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r'^\s*title\s*:\s*', '', s, flags=re.IGNORECASE)
    s = s.strip(" \t\r\n\"'`*_~")
    s = re.sub(r'\s+', ' ', s).strip()
    if looks_invalid_generated_title(s):
        return ''
    return s[:80]


def looks_invalid_generated_title(text: str) -> bool:
    s = str(text or '')
    if not s.strip():
        return True
    return bool(
        re.search(r'<think>|<\|channel\|>thought|<\|turn\|>thinking', s, flags=re.IGNORECASE)
        or re.search(r'^\s*(the|ther)\s+user\s+', s, flags=re.IGNORECASE)
        or re.search(r'^\s*user\s+\w+\s+', s, flags=re.IGNORECASE)
        or re.search(r'\b(they|user)\s+want(s)?\s+me\s+to\b', s, flags=re.IGNORECASE)
        or re.search(r'^\s*(i|we)\s+(should|need to|will|can)\b', s, flags=re.IGNORECASE)
        or re.search(r'^\s*let me\b', s, flags=re.IGNORECASE)
        or re.search(r"^\s*here(?:'s| is) (?:a |my )?(?:thinking|thought)", s, flags=re.IGNORECASE)
        or re.search(r'^\s*(ok|okay|done|all set|complete|completed|finished)\b[\s.!?]*$', s, flags=re.IGNORECASE)
    )


def message_text(value) -> str:
    """Extract plain text from mixed message content payloads."""
    if isinstance(value, list):
        parts = []
        for p in value:
            if not isinstance(p, dict):
                continue
            ptype = str(p.get('type') or '').lower()
            if ptype in ('', 'text', 'input_text', 'output_text'):
                parts.append(str(p.get('text') or p.get('content') or ''))
        return strip_thinking_markup('\n'.join(parts).strip())
    return strip_thinking_markup(str(value or '').strip())


def escape_workspace_prefix_path(path: str) -> str:
    return str(path or '').replace('\\', '\\\\').replace(']', '\\]')


def workspace_context_prefix(path: str) -> str:
    return f"[Workspace::v1: {escape_workspace_prefix_path(path)}]\n"


def strip_workspace_prefix(text: str, *, include_legacy: bool = False) -> str:
    """Remove WebUI-injected workspace tags without eating user-typed text."""
    value = str(text or '')
    stripped = WORKSPACE_PREFIX_RE.sub('', value, count=1)
    if include_legacy and stripped == value:
        stripped = LEGACY_WORKSPACE_PREFIX_RE.sub('', value, count=1)
    return stripped.strip()


def looks_like_current_user_turn(msg, msg_text) -> bool:
    """Match the current human turn even if an internal workspace tag leaked mid-text."""
    if not isinstance(msg, dict) or msg.get('role') != 'user':
        return False
    needle = " ".join(str(msg_text or '').split())
    if not needle:
        return False
    text = message_text(msg.get('content', ''))
    candidates = [strip_workspace_prefix(text, include_legacy=True)]
    for pattern in (WORKSPACE_PREFIX_ANY_RE, LEGACY_WORKSPACE_PREFIX_ANY_RE):
        for match in pattern.finditer(text):
            candidates.append(text[match.end():])
    return any(" ".join(str(candidate or '').split()) == needle for candidate in candidates)


def first_exchange_snippets(messages):
    """Return (first_user_text, first_assistant_text) snippets for title generation."""
    user_text = ''
    asst_text = ''
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = m.get('role')
        if role == 'user':
            candidate = message_text(m.get('content'))
            if not user_text and candidate:
                user_text = candidate
                continue
            if user_text and candidate:
                break
        elif role == 'assistant' and user_text:
            candidate = message_text(m.get('content'))
            if m.get('tool_calls') and (not candidate or looks_invalid_generated_title(candidate)):
                continue
            if candidate:
                asst_text = candidate
        if user_text and asst_text:
            break
    return user_text[:500], asst_text[:500]


def latest_exchange_snippets(messages):
    """Return (last_user_text, last_assistant_text) snippets for title refresh."""
    user_text = ''
    asst_text = ''
    for m in reversed(messages or []):
        if not isinstance(m, dict):
            continue
        role = m.get('role')
        if role == 'assistant' and not asst_text:
            candidate = message_text(m.get('content'))
            if m.get('tool_calls') and (not candidate or looks_invalid_generated_title(candidate)):
                continue
            if candidate:
                asst_text = candidate
        elif role == 'user' and not user_text:
            candidate = message_text(m.get('content'))
            if candidate:
                user_text = candidate
        if user_text and asst_text:
            break
    return user_text[:500], asst_text[:500]


def count_exchanges(messages):
    """Count the number of user messages."""
    count = 0
    for m in messages or []:
        if isinstance(m, dict) and m.get('role') == 'user':
            content = m.get('content', '')
            if isinstance(content, list):
                content = ' '.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
            if str(content).strip():
                count += 1
    return count


def is_provisional_title(current_title: str, messages, *, title_from_fn: Callable | None = None) -> bool:
    """Heuristic: title equals first-message substring placeholder."""
    derived = title_from_fn(messages, '') if title_from_fn else ''
    derived = derived or ''
    if not derived:
        return False
    current = re.sub(r'\s+', ' ', str(current_title or '')).strip()
    candidate = re.sub(r'\s+', ' ', str(derived[:64] or '')).strip()
    if not current or not candidate:
        return False
    return current == candidate


def title_prompts(user_text: str, assistant_text: str) -> tuple[str, list[str]]:
    qa = f"User question:\n{user_text[:500]}\n\nAssistant answer:\n{assistant_text[:500]}"
    prompts = [
        (
            "Generate a short session title from this conversation start.\n"
            "Use BOTH the user's question and the assistant's visible answer.\n"
            "Return only the title text, 3-8 words, as a topic label.\n"
            "Do not use markdown, bullets, labels, or prefixes like Session Title:.\n"
            "Do not output a full sentence.\n"
            "Do not output acknowledgements or completion phrases like OK, done, or all set.\n"
            "Do not describe internal reasoning.\n"
            "Bad: The user is asking..., OK, all set.\n"
            "Good: Title Generation Test, Clarify Dialog Layout, GitHub Issue Triage"
        ),
        (
            "Rewrite this conversation start as a concise noun-phrase title.\n"
            "Use the actual topic, not the task outcome.\n"
            "Return title text only.\n"
            "Do not use markdown, bullets, labels, or prefixes like Session Title:.\n"
            "Never output acknowledgements, completion status, or meta commentary."
        ),
    ]
    return qa, prompts


def fallback_title_from_exchange(user_text: str, assistant_text: str) -> str | None:
    """Generate a readable local fallback title when LLM title generation fails."""
    user_text = (user_text or '').strip()
    assistant_text = strip_thinking_markup(assistant_text or '').strip()
    if not user_text:
        return None
    user_text = strip_workspace_prefix(user_text)
    user_text = re.sub(r'\s+', ' ', user_text).strip()
    assistant_text = re.sub(r'\s+', ' ', assistant_text).strip()
    combined = f"{user_text} {assistant_text}".strip().lower()
    combined_raw = f"{user_text} {assistant_text}".strip()

    def _contains_latin(text: str) -> bool:
        return bool(re.search(r'[A-Za-z]', text or ''))

    def _extract_named_topic(text: str) -> str:
        m = re.search(r'"([^"\n]{2,24})"', text)
        if m:
            return (m.group(1) or '').strip()
        m = re.search(r'\u201c([^\u201d\n]{2,24})\u201d', text)
        if m:
            return (m.group(1) or '').strip()
        return ''

    topic_name = _extract_named_topic(combined_raw)
    if topic_name:
        if not _contains_latin(topic_name):
            if any(k in combined for k in ('time', 'schedule', 'efficiency', 'manage', 'fitness', 'singing', 'calligraphy')):
                return 'Time management discussion'
            if any(k in combined for k in ('hermes', 'codex', 'ai')):
                return 'AI productivity discussion'
            return 'Conversation topic'
        if any(k in combined for k in ('time', 'schedule', 'efficiency', 'manage', 'fitness', 'singing', 'calligraphy')):
            return f'{topic_name} time management'
        if any(k in combined for k in ('hermes', 'codex', 'ai')):
            return f'{topic_name} AI productivity'
        return f'{topic_name} discussion'

    if any(k in combined for k in ('title', 'session title')) and any(k in combined for k in ('summary', 'summar', 'short title')):
        if any(k in combined for k in ('test', 'ok', 'reply ok')):
            return 'Session title auto-summary test'
        return 'Session title auto-summary'
    if any(k in combined for k in ('clarify', 'clarification')) and any(k in combined for k in ('dialog', 'card')):
        return 'Clarify dialog card'
    if any(k in combined for k in ('issue', 'github', 'pr')) and any(k in combined for k in ('triage', 'bug', 'review')):
        return 'GitHub Issue Triage'

    head = re.split(r'[.!?\n]', user_text)[0].strip()
    if not head:
        return None

    stop_en = {
        'the', 'this', 'that', 'with', 'from', 'into', 'just', 'reply', 'please',
        'need', 'needs', 'want', 'wants', 'user', 'assistant', 'could', 'would',
        'should', 'about', 'there', 'here', 'test', 'testing', 'title', 'summary',
    }
    latin_word = r'A-Za-z0-9\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff'
    tokens = re.findall(rf'[{latin_word}][{latin_word}_./+-]*', head)
    if not tokens:
        return 'Conversation topic'

    picked = []
    for tok in tokens:
        lower_tok = tok.lower()
        if lower_tok in stop_en or len(lower_tok) < 3:
            continue
        if tok not in picked:
            picked.append(tok)
        if len(picked) >= 4:
            break

    if picked:
        return ' '.join(picked)[:60]
    return 'Conversation topic'


def is_generic_fallback_title(title: str) -> bool:
    """Return True for low-information fallback labels that should not be persisted."""
    return str(title or '').strip().lower() in {'conversation topic'}
