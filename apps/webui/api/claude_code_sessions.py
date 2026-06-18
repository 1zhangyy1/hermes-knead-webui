"""Read-only Claude Code JSONL session bridge."""

import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Callable


CLAUDE_CODE_SOURCE = 'claude_code'
CLAUDE_CODE_SOURCE_LABEL = 'Claude Code'
CLAUDE_CODE_MAX_FILES = 200
CLAUDE_CODE_MAX_FILE_BYTES = 10 * 1024 * 1024
CLAUDE_CODE_MAX_MESSAGES_PER_FILE = 1000
CLAUDE_CODE_MAX_CONTENT_CHARS = 200_000


def default_projects_dir() -> Path | None:
    """Resolve the Claude Code projects directory without touching real home in tests."""
    override = os.getenv('HERMES_WEBUI_CLAUDE_PROJECTS_DIR')
    if override:
        return Path(override).expanduser()
    if os.getenv('HERMES_WEBUI_TEST_STATE_DIR'):
        return None
    return Path.home() / '.claude' / 'projects'


def session_id_for_path(path: Path) -> str:
    digest = hashlib.sha256(str(path.expanduser().resolve()).encode('utf-8')).hexdigest()[:24]
    return f'{CLAUDE_CODE_SOURCE}_{digest}'


def parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


def extract_text(content) -> str:
    if content is None:
        return ''
    if isinstance(content, str):
        return content[:CLAUDE_CODE_MAX_CONTENT_CHARS]
    if isinstance(content, list):
        parts = []
        used = 0
        for item in content:
            text = ''
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                text = item.get('text') or item.get('content') or ''
            if not text:
                continue
            text = str(text)
            remaining = CLAUDE_CODE_MAX_CONTENT_CHARS - used
            if remaining <= 0:
                break
            parts.append(text[:remaining])
            used += len(parts[-1])
        return '\n'.join(parts)
    if isinstance(content, dict):
        return extract_text(content.get('text') or content.get('content'))
    return str(content)[:CLAUDE_CODE_MAX_CONTENT_CHARS]


def parse_jsonl(
    path: Path,
    *,
    max_messages: int = CLAUDE_CODE_MAX_MESSAGES_PER_FILE,
) -> tuple[list[dict], str | None, float | None, float | None]:
    messages: list[dict] = []
    summary_title = None
    first_ts = None
    last_ts = None
    try:
        with path.open('r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if len(messages) >= max_messages:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                if not summary_title:
                    summary = raw.get('summary') or raw.get('title')
                    if isinstance(summary, str) and summary.strip():
                        summary_title = ' '.join(summary.split())[:80]
                records = raw.get('messages') if isinstance(raw.get('messages'), list) else None
                if records is None:
                    records = [raw.get('message') if isinstance(raw.get('message'), dict) else raw]
                for record in records:
                    if len(messages) >= max_messages:
                        break
                    if not isinstance(record, dict):
                        continue
                    msg = record.get('message') if isinstance(record.get('message'), dict) else record
                    role = str(
                        msg.get('role')
                        or record.get('role')
                        or raw.get('role')
                        or raw.get('type')
                        or ''
                    ).strip().lower()
                    if role == 'human':
                        role = 'user'
                    if role not in {'user', 'assistant', 'system', 'tool'}:
                        continue
                    content = extract_text(
                        msg.get('content') if 'content' in msg else record.get('content')
                    )
                    if not content.strip():
                        continue
                    ts = parse_timestamp(
                        msg.get('timestamp')
                        or record.get('timestamp')
                        or raw.get('timestamp')
                        or raw.get('created_at')
                    )
                    if ts is not None:
                        first_ts = ts if first_ts is None else min(first_ts, ts)
                        last_ts = ts if last_ts is None else max(last_ts, ts)
                    item = {'role': role, 'content': content}
                    if ts is not None:
                        item['timestamp'] = ts
                    messages.append(item)
    except Exception:
        return [], None, None, None
    return messages, summary_title, first_ts, last_ts


def iter_jsonl_files(
    projects_dir: Path | str | None = None,
    *,
    default_projects_dir_fn: Callable[[], Path | None] = default_projects_dir,
    max_files: int = CLAUDE_CODE_MAX_FILES,
    max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES,
):
    root = Path(projects_dir).expanduser() if projects_dir is not None else default_projects_dir_fn()
    if root is None:
        return
    try:
        if root.is_symlink():
            return
        root = root.resolve(strict=False)
        if not root.exists() or not root.is_dir():
            return
        yielded = 0
        for project_dir in sorted(root.iterdir(), key=lambda p: p.name):
            if yielded >= max_files:
                return
            try:
                if project_dir.is_symlink() or not project_dir.is_dir():
                    continue
                for path in sorted(project_dir.iterdir(), key=lambda p: p.name):
                    if yielded >= max_files:
                        return
                    if path.is_symlink() or not path.is_file() or path.suffix.lower() != '.jsonl':
                        continue
                    try:
                        if path.stat().st_size > max_file_bytes:
                            continue
                    except OSError:
                        continue
                    yielded += 1
                    yield path
            except OSError:
                continue
    except OSError:
        return


def title_from_messages(messages: list[dict], summary_title: str | None) -> str:
    if summary_title:
        return summary_title
    for msg in messages:
        if msg.get('role') == 'user':
            text = ' '.join(str(msg.get('content') or '').split())
            if text:
                return text[:80]
    return 'Claude Code Session'


def get_sessions(
    projects_dir: Path | str | None = None,
    *,
    get_workspace: Callable[[], object],
    default_projects_dir_fn: Callable[[], Path | None] = default_projects_dir,
    max_files: int = CLAUDE_CODE_MAX_FILES,
    max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES,
) -> list:
    """Read Claude Code JSONL sessions as read-only external-agent rows."""
    sessions = []
    for path in iter_jsonl_files(
        projects_dir,
        default_projects_dir_fn=default_projects_dir_fn,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    ) or []:
        messages, summary_title, first_ts, last_ts = parse_jsonl(path)
        if not messages:
            continue
        stat_mtime = path.stat().st_mtime
        sessions.append({
            'session_id': session_id_for_path(path),
            'title': title_from_messages(messages, summary_title),
            'workspace': str(get_workspace()),
            'model': 'claude-code',
            'message_count': len(messages),
            'created_at': first_ts or last_ts or stat_mtime,
            'updated_at': last_ts or first_ts or stat_mtime,
            'last_message_at': last_ts or first_ts or stat_mtime,
            'pinned': False,
            'archived': False,
            'project_id': None,
            'profile': None,
            'source_tag': CLAUDE_CODE_SOURCE,
            'raw_source': CLAUDE_CODE_SOURCE,
            'session_source': 'external_agent',
            'source_label': CLAUDE_CODE_SOURCE_LABEL,
            'is_cli_session': True,
            'read_only': True,
        })
    sessions.sort(key=lambda s: s.get('last_message_at') or s.get('updated_at') or 0, reverse=True)
    return sessions


def get_session_messages(
    sid,
    projects_dir: Path | str | None = None,
    *,
    default_projects_dir_fn: Callable[[], Path | None] = default_projects_dir,
) -> list:
    """Return messages for one read-only Claude Code JSONL session."""
    sid = str(sid or '')
    if not sid.startswith(f'{CLAUDE_CODE_SOURCE}_'):
        return []
    for path in iter_jsonl_files(
        projects_dir,
        default_projects_dir_fn=default_projects_dir_fn,
    ) or []:
        if session_id_for_path(path) != sid:
            continue
        messages, _summary_title, _first_ts, _last_ts = parse_jsonl(path)
        return messages
    return []
