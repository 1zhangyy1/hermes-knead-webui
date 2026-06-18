"""Helpers for reading and mutating CLI sessions in state.db."""

import datetime
import json
from contextlib import closing
from pathlib import Path
from typing import Callable


def json_loads_if_string(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return value


def get_session_messages(
    sid,
    *,
    db_path: Path,
    is_continuation_session: Callable[[dict, dict], bool],
) -> list:
    """Read messages for a single CLI/external-agent session."""
    try:
        import sqlite3
    except ImportError:
        return []

    if not db_path.exists():
        return []

    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(messages)")
            available = {str(row['name']) for row in cur.fetchall()}
            required = {'role', 'content', 'timestamp'}
            if not required.issubset(available):
                return []
            optional = [
                'tool_call_id',
                'tool_calls',
                'tool_name',
                'reasoning',
                'reasoning_details',
                'codex_reasoning_items',
                'reasoning_content',
                'codex_message_items',
            ]
            selected = ['role', 'content', 'timestamp'] + [c for c in optional if c in available]

            cur.execute("PRAGMA table_info(sessions)")
            session_cols = {str(row['name']) for row in cur.fetchall()}
            session_chain = [str(sid)]
            if {'parent_session_id', 'end_reason', 'started_at', 'source'}.issubset(session_cols):
                cur.execute(
                    """
                    SELECT id, source, started_at, parent_session_id, ended_at, end_reason
                    FROM sessions
                    WHERE id = ?
                    """,
                    (sid,),
                )
                rows_by_id = {}
                row = cur.fetchone()
                if row:
                    rows_by_id[str(row['id'])] = dict(row)
                    current_id = str(row['id'])
                    seen = {current_id}
                    for _ in range(20):
                        current = rows_by_id.get(current_id)
                        parent_id = current.get('parent_session_id') if current else None
                        if not parent_id or parent_id in seen:
                            break
                        cur.execute(
                            """
                            SELECT id, source, started_at, parent_session_id, ended_at, end_reason
                            FROM sessions
                            WHERE id = ?
                            """,
                            (parent_id,),
                        )
                        parent_row = cur.fetchone()
                        if not parent_row:
                            break
                        parent_dict = dict(parent_row)
                        rows_by_id[str(parent_row['id'])] = parent_dict
                        if not is_continuation_session(parent_dict, current):
                            break
                        session_chain.insert(0, str(parent_row['id']))
                        current_id = str(parent_row['id'])
                        seen.add(current_id)

            placeholders = ', '.join('?' for _ in session_chain)
            cur.execute(f"""
                SELECT {', '.join(selected)}, session_id
                FROM messages
                WHERE session_id IN ({placeholders})
                ORDER BY timestamp ASC, id ASC
            """, session_chain)
            msgs = []
            for row in cur.fetchall():
                msg = {
                    'role': row['role'],
                    'content': row['content'],
                    'timestamp': row['timestamp'],
                }
                for col in optional:
                    if col not in row.keys():
                        continue
                    value = row[col]
                    if value in (None, ''):
                        continue
                    if col in {
                        'tool_calls',
                        'reasoning_details',
                        'codex_reasoning_items',
                        'codex_message_items',
                    }:
                        value = json_loads_if_string(value)
                    msg[col] = value
                if msg.get('role') == 'tool' and msg.get('tool_name') and not msg.get('name'):
                    msg['name'] = msg['tool_name']
                msgs.append(msg)
    except Exception:
        return []
    return msgs


def count_conversation_rounds(sid: str, *, db_path: Path, since: float | None = None) -> int:
    """Count complete user/assistant rounds for a CLI session."""
    try:
        import sqlite3
    except ImportError:
        return 0

    if not db_path.exists():
        return 0

    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT role, timestamp FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
                (sid,),
            )
            rows = cur.fetchall()
    except Exception:
        return 0

    rounds = 0
    seen_user = False
    seen_agent_after_user = False

    for row in rows:
        role = (row['role'] or '').strip().lower()
        ts_raw = row['timestamp']

        if since is not None and ts_raw is not None:
            try:
                if isinstance(ts_raw, (int, float)):
                    ts_val = float(ts_raw)
                else:
                    ts_val = datetime.datetime.fromisoformat(
                        str(ts_raw).replace('Z', '+00:00')
                    ).timestamp()
                if ts_val <= since:
                    continue
            except Exception:
                pass

        if role == 'user':
            if seen_user and not seen_agent_after_user:
                pass
            elif seen_user and seen_agent_after_user:
                rounds += 1
                seen_agent_after_user = False
            seen_user = True
        elif role == 'assistant':
            if seen_user:
                seen_agent_after_user = True

    if seen_user and seen_agent_after_user:
        rounds += 1

    return rounds


def delete_session(sid, *, db_path: Path) -> bool:
    """Delete a CLI session from state.db."""
    try:
        import sqlite3
    except ImportError:
        return False

    if not db_path.exists():
        return False

    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            cur.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.commit()
            return cur.rowcount > 0
    except Exception:
        return False
