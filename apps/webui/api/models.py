"""Hermes Web UI -- Session model and in-memory session store."""
import collections
import copy
import datetime
import json
import logging
import os
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path

import api.config as _cfg
from api.config import (
    SESSION_DIR, SESSION_INDEX_FILE, SESSIONS, SESSIONS_MAX,
    LOCK, STREAMS, STREAMS_LOCK, DEFAULT_WORKSPACE, DEFAULT_MODEL, PROJECTS_FILE, HOME,
    get_effective_default_model, _get_session_agent_lock,
)
from api.workspace import get_last_workspace
from api.agent_sessions import (
    _is_continuation_session,
    read_importable_agent_session_rows,
    read_session_lineage_metadata,
)
from api.session_index import (
    _INDEX_WRITE_LOCK,
    _STALE_TMP_AGE_SECONDS,
    cleanup_stale_tmp_files as _cleanup_session_index_tmp_files,
    index_entry_exists as _session_index_entry_exists,
    lookup_index_message_count as _lookup_session_index_message_count,
    write_session_index as _write_session_index_impl,
)
from api.session_metadata import (
    find_top_level_json_key as _find_top_level_json_key_impl,
    read_metadata_json_prefix as _read_metadata_json_prefix_impl,
)
from api.session_json import build_session_payload, write_session_json_with_backup
from api.session_store import (
    load_session as _load_session_from_store,
    load_session_metadata_only as _load_session_metadata_only_from_store,
)
from api.session_sidebar import (
    enrich_sidebar_lineage_metadata as _enrich_sidebar_lineage_metadata_impl,
    has_live_sidebar_state as _has_live_sidebar_state_impl,
    hide_from_default_sidebar as _hide_from_default_sidebar_impl,
    prefer_fuller_snapshots_for_sidebar as _prefer_fuller_snapshots_for_sidebar_impl,
    sidebar_lineage_root_id as _sidebar_lineage_root_id_impl,
    sidebar_message_count as _sidebar_message_count_impl,
    sidebar_title_is_generic_webui as _sidebar_title_is_generic_webui_impl,
    strip_sidebar_internal_flags as _strip_sidebar_internal_flags_impl,
)
from api.session_cache import (
    cache_session as _cache_session,
    evict_cached_session_if_same as _evict_cached_session_if_same,
    get_cached_session as _get_cached_session,
)
from api.project_store import (
    backfill_project_profiles_if_needed as _backfill_project_profiles_impl,
    ensure_cron_project as _ensure_cron_project_impl,
    load_projects as _load_projects_impl,
    save_projects as _save_projects_impl,
)
from api.claude_code_sessions import (
    CLAUDE_CODE_MAX_CONTENT_CHARS,
    CLAUDE_CODE_MAX_FILE_BYTES,
    CLAUDE_CODE_MAX_FILES,
    CLAUDE_CODE_MAX_MESSAGES_PER_FILE,
    CLAUDE_CODE_SOURCE,
    CLAUDE_CODE_SOURCE_LABEL,
    default_projects_dir as _default_claude_code_projects_dir_impl,
    extract_text as _extract_claude_code_text_impl,
    get_session_messages as _get_claude_code_session_messages_impl,
    get_sessions as _get_claude_code_sessions_impl,
    iter_jsonl_files as _iter_claude_code_jsonl_files_impl,
    parse_jsonl as _parse_claude_code_jsonl_impl,
    parse_timestamp as _parse_claude_code_timestamp_impl,
    session_id_for_path as _claude_code_session_id_impl,
    title_from_messages as _claude_code_title_impl,
)

logger = logging.getLogger(__name__)
CLI_VISIBLE_SESSION_LIMIT = 20
_CLI_SESSIONS_CACHE_TTL_SECONDS = 5.0
_CLI_SESSIONS_CACHE_LOCK = threading.Lock()
_CLI_SESSIONS_CACHE = {}

def _cleanup_stale_tmp_files() -> None:
    _cleanup_session_index_tmp_files(SESSION_DIR, logger=logger)


def _index_entry_exists(session_id: str, in_memory_ids=None) -> bool:
    return _session_index_entry_exists(
        session_dir=SESSION_DIR,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        session_id=session_id,
        in_memory_ids=in_memory_ids,
    )


def _write_session_index(updates=None):
    _write_session_index_impl(
        session_dir=SESSION_DIR,
        index_file=SESSION_INDEX_FILE,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        updates=updates,
        load_session=Session.load,
        logger=logger,
    )


def _active_stream_ids():
    with STREAMS_LOCK:
        return set(STREAMS.keys())


def _append_recovered_turn_to_context(session, recovered: dict) -> None:
    context_messages = getattr(session, 'context_messages', None)
    if not isinstance(context_messages, list) or not context_messages:
        return
    recovered_text = " ".join(str(recovered.get('content') or '').split())
    if recovered_text:
        for existing in reversed(context_messages[-8:]):
            if not isinstance(existing, dict) or existing.get('role') != 'user':
                continue
            existing_text = " ".join(str(existing.get('content') or '').split())
            if existing_text == recovered_text:
                return
    context_entry = {k: v for k, v in recovered.items() if k != 'timestamp'}
    context_messages.append(context_entry)


def _append_recovered_pending_turn(session, *, timestamp: int | None = None) -> dict | None:
    pending_text = str(session.pending_user_message or '')
    if not pending_text:
        return None
    recovered_ts = int(time.time())
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        recovered_ts = int(timestamp)
    recovered: dict = {
        'role': 'user',
        'content': session.pending_user_message,
        'timestamp': recovered_ts,
        '_recovered': True,
    }
    if session.pending_attachments:
        recovered['attachments'] = list(session.pending_attachments)
    session.messages.append(recovered)
    _append_recovered_turn_to_context(session, recovered)
    return recovered


def _is_streaming_session(active_stream_id, active_stream_ids):
    return bool(active_stream_id and active_stream_id in active_stream_ids)

def _session_sort_timestamp(session):
    if isinstance(session, dict):
        return session.get('last_message_at') or session.get('updated_at') or 0
    return _last_message_timestamp(getattr(session, 'messages', None)) or getattr(session, 'updated_at', 0) or 0


def _message_timestamp(message):
    if not isinstance(message, dict):
        return None
    raw = message.get('_ts') or message.get('timestamp')
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _last_message_timestamp(messages):
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, dict) and message.get('role') == 'tool':
            continue
        ts = _message_timestamp(message)
        if ts:
            return ts
    return None


def _message_role(message):
    if not isinstance(message, dict):
        return ''
    return str(message.get('role', '')).strip().lower()


def _find_top_level_json_key(text, key):
    return _find_top_level_json_key_impl(text, key)


def _read_metadata_json_prefix(path, max_prefix_bytes=65536):
    return _read_metadata_json_prefix_impl(path, max_prefix_bytes=max_prefix_bytes)


def _lookup_index_message_count(session_id):
    return _lookup_session_index_message_count(SESSION_INDEX_FILE, session_id)


class Session:
    def __init__(self, session_id: str=None, title: str='Untitled',
                 workspace=str(DEFAULT_WORKSPACE), model=DEFAULT_MODEL,
                 model_provider=None,
                 messages=None, created_at=None, updated_at=None,
                 tool_calls=None, pinned: bool=False, archived: bool=False,
                 project_id: str=None, profile=None,
                 input_tokens: int=0, output_tokens: int=0, estimated_cost=None,
                 cache_read_tokens: int=0, cache_write_tokens: int=0,
                 personality=None,
                 active_stream_id: str=None,
                 pending_user_message: str=None,
                 pending_attachments=None,
                 pending_started_at=None,
                 context_messages=None,
                 compression_anchor_visible_idx=None,
                 compression_anchor_message_key=None,
                 compression_anchor_summary=None,
                 pre_compression_snapshot: bool=False,
                 context_length=None, threshold_tokens=None,
                 last_prompt_tokens=None,
                 gateway_routing=None, gateway_routing_history=None,
                 llm_title_generated: bool=False,
                parent_session_id: str=None,
                worktree_path=None,
                worktree_branch=None,
                worktree_repo_root=None,
                worktree_created_at=None,
                enabled_toolsets=None,
                product_id=None,
                product_scope=None,
                product_intent=None,
                product_line=None,
                composer_draft=None,
                **kwargs):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.title = title
        self.workspace = str(Path(workspace).expanduser().resolve())
        self.model = model
        self.model_provider = str(model_provider).strip().lower() if model_provider else None
        self.messages = messages or []
        self.tool_calls = tool_calls or []
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or time.time()
        self.pinned = bool(pinned)
        self.archived = bool(archived)
        self.project_id = project_id or None
        self.profile = profile
        self.input_tokens = input_tokens or 0
        self.output_tokens = output_tokens or 0
        self.estimated_cost = estimated_cost
        self.cache_read_tokens = cache_read_tokens or 0
        self.cache_write_tokens = cache_write_tokens or 0
        self.personality = personality
        self.active_stream_id = active_stream_id
        self.pending_user_message = pending_user_message
        self.pending_attachments = pending_attachments or []
        self.pending_started_at = pending_started_at
        self.context_messages = context_messages if isinstance(context_messages, list) else []
        self.compression_anchor_visible_idx = compression_anchor_visible_idx
        self.compression_anchor_message_key = compression_anchor_message_key
        self.compression_anchor_summary = compression_anchor_summary
        self.pre_compression_snapshot = bool(pre_compression_snapshot)
        self.context_length = context_length
        self.threshold_tokens = threshold_tokens
        self.last_prompt_tokens = last_prompt_tokens
        self.gateway_routing = gateway_routing if isinstance(gateway_routing, dict) else None
        self.gateway_routing_history = gateway_routing_history if isinstance(gateway_routing_history, list) else []
        self.llm_title_generated = bool(llm_title_generated)
        self.parent_session_id = parent_session_id
        self.worktree_path = str(Path(worktree_path).expanduser().resolve()) if worktree_path else None
        self.worktree_branch = str(worktree_branch) if worktree_branch else None
        self.worktree_repo_root = str(Path(worktree_repo_root).expanduser().resolve()) if worktree_repo_root else None
        self.worktree_created_at = worktree_created_at
        self.product_id = str(product_id).strip() if product_id else None
        self.product_scope = str(product_scope).strip() if product_scope else None
        self.product_intent = str(product_intent).strip() if product_intent else None
        # 造/用双会话线:'build' = 产品造物/调整会话,'use' = 任务使用会话。
        # None 视为 use(向后兼容旧会话)。
        _product_line = str(product_line).strip() if product_line else ''
        self.product_line = _product_line if _product_line in ('use', 'build') else None
        self.is_cli_session = bool(kwargs.get('is_cli_session', False))
        self.source_tag = kwargs.get('source_tag')
        self.raw_source = kwargs.get('raw_source')
        self.session_source = kwargs.get('session_source')
        self.source_label = kwargs.get('source_label')
        self.read_only = bool(kwargs.get('read_only', False))
        self.enabled_toolsets = enabled_toolsets  # List[str] or None — per-session toolset override
        self.composer_draft = composer_draft if isinstance(composer_draft, dict) else {}
        self._metadata_message_count = None

    @property
    def path(self):
        return SESSION_DIR / f'{self.session_id}.json'

    def save(self, touch_updated_at: bool = True, skip_index: bool = False) -> None:
        # ── #1558 P0 guard ──────────────────────────────────────────────
        # Refuse to save a session that was loaded with metadata_only=True.
        # Such sessions have messages=[] (it's the whole point of the partial
        # load), and save() unconditionally writes self.messages to disk via
        # an atomic os.replace(). Saving a metadata-only stub thus wipes the
        # full conversation history — which is exactly the v0.50.279
        # _clear_stale_stream_state() regression that lost users 1000+
        # message conversations. Any caller that needs to mutate persisted
        # fields on a metadata-only session must reload with
        # metadata_only=False first.
        if getattr(self, '_loaded_metadata_only', False):
            raise RuntimeError(
                f"Refusing to save metadata-only session {self.session_id!r}: "
                f"would atomically overwrite on-disk messages with []. "
                f"Reload with metadata_only=False before mutating state. "
                f"See #1558."
            )
        if touch_updated_at:
            self.updated_at = time.time()
        # Write metadata fields first so load_metadata_only() can read them
        # without parsing the full messages array (which may be 400KB+).
        # Fields are listed in the order they should appear in the JSON file.
        METADATA_FIELDS = [
            'session_id', 'title', 'workspace', 'model', 'model_provider', 'created_at', 'updated_at',
            'pinned', 'archived', 'project_id', 'profile',
            'input_tokens', 'output_tokens', 'estimated_cost',
            'cache_read_tokens', 'cache_write_tokens',
            'personality', 'active_stream_id',
            'pending_user_message', 'pending_attachments', 'pending_started_at',
            'compression_anchor_visible_idx', 'compression_anchor_message_key',
            'compression_anchor_summary', 'pre_compression_snapshot',
            'context_length', 'threshold_tokens', 'last_prompt_tokens',
            'gateway_routing', 'gateway_routing_history', 'llm_title_generated',
            'parent_session_id',
            'worktree_path', 'worktree_branch', 'worktree_repo_root', 'worktree_created_at',
            'product_id', 'product_scope', 'product_intent', 'product_line',
            'is_cli_session', 'source_tag', 'raw_source', 'session_source', 'source_label', 'read_only',
            'enabled_toolsets', 'composer_draft',
        ]
        payload = build_session_payload(self, METADATA_FIELDS)

        # ── #1558 backup safeguard ──────────────────────────────────────
        # Before overwriting the session file, copy the previous version to
        # ``<sid>.json.bak`` IFF the previous file has more messages than the
        # incoming payload. The asymmetric guard means:
        #   * Normal grow-the-conversation saves never produce a backup
        #     (incoming messages >= existing) — keeps disk overhead near zero.
        #   * Any save that would shrink the messages array (the failure mode
        #     of #1558, plus anything similar in the future) leaves a recoverable
        #     snapshot of the pre-shrink state on disk.
        # The recovery path is api/session_recovery.py — at server startup and
        # via /api/session/recover, sessions whose JSON has fewer messages than
        # their .bak get restored automatically.
        write_session_json_with_backup(self.path, payload, self.messages)
        if not skip_index:
            _write_session_index(updates=[self])

    @classmethod
    def load(cls, sid):
        # Validate session ID format to prevent path traversal
        return _load_session_from_store(cls, SESSION_DIR, sid)

    @classmethod
    def load_metadata_only(cls, sid):
        """Load only the compact metadata fields, skipping the messages array.

        Session JSON files have metadata fields (session_id, title, model, etc.)
        at the top level, before the large messages array. Read only up to the
        top-level "messages" field and synthesize a small metadata-only object.
        Falls back to load() for legacy or unexpected file layouts.
        """
        return _load_session_metadata_only_from_store(
            cls,
            SESSION_DIR,
            SESSION_INDEX_FILE,
            sid,
        )

    def compact(self, include_runtime=False, active_stream_ids=None) -> dict:
        active_stream_ids = active_stream_ids if active_stream_ids is not None else set()
        has_pending_user_message = bool(self.pending_user_message)
        message_count = (
            self._metadata_message_count
            if self._metadata_message_count is not None
            else len(self.messages)
        )
        if has_pending_user_message:
            message_count = max(message_count, 1)
        last_message_at = _last_message_timestamp(self.messages) or self.updated_at
        if has_pending_user_message and self.pending_started_at:
            last_message_at = self.pending_started_at
        return {
            'session_id': self.session_id,
            'title': self.title,
            'workspace': self.workspace,
            'model': self.model,
            'model_provider': self.model_provider,
            'message_count': message_count,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_message_at': last_message_at,
            'pinned': self.pinned,
            'archived': self.archived,
            'project_id': self.project_id,
            'profile': self.profile,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'estimated_cost': self.estimated_cost,
            'cache_read_tokens': self.cache_read_tokens,
            'cache_write_tokens': self.cache_write_tokens,
            'personality': self.personality,
            'compression_anchor_visible_idx': self.compression_anchor_visible_idx,
            'compression_anchor_message_key': self.compression_anchor_message_key,
            'compression_anchor_summary': self.compression_anchor_summary,
            'pre_compression_snapshot': self.pre_compression_snapshot,
            'context_length': self.context_length,
            'threshold_tokens': self.threshold_tokens,
            'last_prompt_tokens': self.last_prompt_tokens,
            'gateway_routing': self.gateway_routing,
            'gateway_routing_history': self.gateway_routing_history,
            # Only emit 'parent_session_id' when set (the /branch fork link, #1342).
            # Sessions without a fork must not leak None — see test_session_lineage_metadata_api.
            **({'parent_session_id': self.parent_session_id} if self.parent_session_id else {}),
            **({
                'worktree_path': self.worktree_path,
                'worktree_branch': self.worktree_branch,
                'worktree_repo_root': self.worktree_repo_root,
                'worktree_created_at': self.worktree_created_at,
            } if self.worktree_path else {}),
            **({
                'product_id': self.product_id,
                'product_scope': self.product_scope or 'product_usage',
                'product_intent': self.product_intent or '',
                'product_line': self.product_line or 'use',
            } if self.product_id else {}),
            'user_message_count': sum(
                1 for message in self.messages if _message_role(message) == 'user'
            ) if isinstance(self.messages, list) else 0,
            'active_stream_id': self.active_stream_id,
            'pending_user_message': self.pending_user_message,
            'has_pending_user_message': has_pending_user_message,
            'is_cli_session': self.is_cli_session,
            'source_tag': self.source_tag,
            'raw_source': self.raw_source,
            'session_source': self.session_source,
            'source_label': self.source_label,
            'read_only': self.read_only,
            'enabled_toolsets': self.enabled_toolsets,
            'composer_draft': self.composer_draft if isinstance(self.composer_draft, dict) else {},
            'is_streaming': _is_streaming_session(
                self.active_stream_id, active_stream_ids
            ) if include_runtime else False,
        }

def _get_profile_home(profile) -> Path:
    """Resolve the hermes agent home directory for the given profile.

    Prefers the profile-specific helper from api.profiles; falls back to the
    HERMES_HOME environment variable or ~/.hermes, expanding ~ correctly.
    """
    try:
        from api.profiles import get_hermes_home_for_profile
        return Path(get_hermes_home_for_profile(profile))
    except ImportError:
        return Path(os.environ.get('HERMES_HOME') or '~/.hermes').expanduser()


def _interrupted_recovery_marker(*, recovered_output: bool = False) -> dict:
    if recovered_output:
        content = (
            '**Response interrupted.**\n\n'
            'The WebUI process restarted before this turn finished. '
            'The partial output above was recovered from the run journal, '
            'but the interrupted agent process could not continue.'
        )
    else:
        content = (
            '**Response interrupted.**\n\n'
            'The WebUI process restarted before this turn finished. '
            'The user message above was preserved, but no agent output was recovered.'
        )
    return {
        'role': 'assistant',
        'content': content,
        'timestamp': int(time.time()),
        '_error': True,
        'type': 'interrupted',
    }


def _truncate_journal_tool_args(args, limit: int = 4) -> dict:
    if not isinstance(args, dict):
        return {}
    out = {}
    for key, value in list(args.items())[:limit]:
        text = str(value)
        out[str(key)] = text[:120] + ('...' if len(text) > 120 else '')
    return out


def _normalize_journal_recovery_text(value) -> str:
    return " ".join(str(value or "").split())


def _find_existing_assistant_for_journal_content(session, content: str) -> int | None:
    candidate = _normalize_journal_recovery_text(content)
    if not candidate:
        return None
    for idx, message in enumerate(session.messages or []):
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            continue
        if message.get('_error'):
            continue
        existing = _normalize_journal_recovery_text(message.get('content'))
        if not existing:
            continue
        if existing == candidate:
            return idx
        if len(candidate) >= 24 and candidate in existing:
            return idx
    return None


def _journal_tool_already_present(session, name: str, preview: str) -> bool:
    candidate_name = str(name or '')
    candidate_preview = _normalize_journal_recovery_text(preview)
    for tool_call in session.tool_calls or []:
        if not isinstance(tool_call, dict):
            continue
        if str(tool_call.get('name') or '') != candidate_name:
            continue
        existing_preview = _normalize_journal_recovery_text(
            tool_call.get('preview') or tool_call.get('snippet') or ''
        )
        if existing_preview == candidate_preview:
            return True
    return False


def _run_journal_has_visible_output(session, stream_id: str | None) -> bool:
    if not stream_id:
        return False
    try:
        from api.run_journal import read_run_events
        journal = read_run_events(session.session_id, stream_id)
    except Exception:
        return False
    for event in journal.get('events') or []:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get('event') or event.get('type') or '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        if event_name == 'token' and str(payload.get('text') or ''):
            return True
        if event_name == 'interim_assistant':
            if payload.get('already_streamed'):
                continue
            if str(payload.get('text') or '').strip():
                return True
        if event_name == 'tool':
            return True
    return False


def _append_journaled_partial_output(
    session,
    stream_id: str | None,
    *,
    dedupe_existing: bool = False,
) -> bool:
    """Recover already-emitted visible output from a dead stream journal.

    This repair path is intentionally conservative: it restores user-visible
    assistant text and tool-card metadata that had already been emitted over
    SSE before the WebUI process died. It does not restore hidden reasoning and
    it does not try to continue execution.
    """
    if not stream_id:
        return False

    try:
        from api.run_journal import read_run_events
        journal = read_run_events(session.session_id, stream_id)
    except Exception:
        logger.debug(
            "Session %s: failed to read run journal for stream %s",
            getattr(session, 'session_id', '?'),
            stream_id,
            exc_info=True,
        )
        return False

    events = [event for event in journal.get('events') or [] if isinstance(event, dict)]
    if not events:
        return False

    appended_any = False
    assistant_parts: list[str] = []
    assistant_started_at: float | None = None
    current_assistant_idx: int | None = None
    recovered_tool_calls: list[dict] = []

    def flush_assistant() -> int | None:
        nonlocal appended_any, assistant_parts, assistant_started_at, current_assistant_idx
        content = ''.join(assistant_parts).strip()
        assistant_parts = []
        if not content:
            return current_assistant_idx
        if dedupe_existing:
            existing_idx = _find_existing_assistant_for_journal_content(session, content)
            if existing_idx is not None:
                current_assistant_idx = existing_idx
                assistant_started_at = None
                return existing_idx
        timestamp = int(assistant_started_at or time.time())
        session.messages.append({
            'role': 'assistant',
            'content': content,
            'timestamp': timestamp,
            '_recovered_from_run_journal': True,
            '_recovered_stream_id': stream_id,
        })
        current_assistant_idx = len(session.messages) - 1
        assistant_started_at = None
        appended_any = True
        return current_assistant_idx

    def ensure_assistant_anchor(created_at: float | None = None) -> int:
        nonlocal appended_any, current_assistant_idx
        idx = flush_assistant()
        if idx is not None:
            return idx
        # A stream can start with tools before any text. Keep those tools
        # visible after restart with an empty recovered assistant anchor instead
        # of inventing synthetic progress prose.
        session.messages.append({
            'role': 'assistant',
            'content': '',
            'timestamp': int(created_at or time.time()),
            '_recovered_from_run_journal': True,
            '_recovered_stream_id': stream_id,
        })
        current_assistant_idx = len(session.messages) - 1
        appended_any = True
        return current_assistant_idx

    for event in events:
        event_name = str(event.get('event') or event.get('type') or '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        created_at = event.get('created_at') if isinstance(event.get('created_at'), (int, float)) else None
        if event_name == 'token':
            text = str(payload.get('text') or '')
            if not text:
                continue
            if not assistant_parts and assistant_started_at is None:
                assistant_started_at = created_at or time.time()
            assistant_parts.append(text)
            continue
        if event_name == 'interim_assistant':
            if payload.get('already_streamed'):
                flush_assistant()
                continue
            text = str(payload.get('text') or '').strip()
            if not text:
                continue
            if not assistant_parts and assistant_started_at is None:
                assistant_started_at = created_at or time.time()
            if assistant_parts and not ''.join(assistant_parts).endswith(('\n', ' ')):
                assistant_parts.append('\n\n')
            assistant_parts.append(text)
            flush_assistant()
            continue
        if event_name == 'tool':
            anchor_idx = flush_assistant()
            if anchor_idx is None:
                anchor_idx = ensure_assistant_anchor(created_at)
            name = str(payload.get('name') or 'tool')
            preview = str(payload.get('preview') or '')
            if dedupe_existing and _journal_tool_already_present(session, name, preview):
                current_assistant_idx = anchor_idx
                continue
            recovered_tool_calls.append({
                'name': name,
                'preview': preview,
                'snippet': preview,
                'tid': f"journal-{event.get('seq') or len(recovered_tool_calls) + 1}",
                'assistant_msg_idx': anchor_idx,
                'args': _truncate_journal_tool_args(payload.get('args') or {}),
                'done': False,
                '_recovered_from_run_journal': True,
                '_recovered_stream_id': stream_id,
            })
            appended_any = True
            current_assistant_idx = anchor_idx
            continue
        if event_name == 'tool_complete':
            name = str(payload.get('name') or '')
            for tool_call in reversed(recovered_tool_calls):
                if tool_call.get('done'):
                    continue
                if not name or tool_call.get('name') == name:
                    tool_call['done'] = True
                    if payload.get('preview'):
                        tool_call['preview'] = str(payload.get('preview') or '')
                        tool_call['snippet'] = str(payload.get('preview') or '')
                    if payload.get('duration') is not None:
                        tool_call['duration'] = payload.get('duration')
                    tool_call['is_error'] = bool(payload.get('is_error', False))
                    break
            continue
        if event_name in {'done', 'stream_end', 'cancel', 'apperror', 'error'}:
            flush_assistant()

    flush_assistant()
    if recovered_tool_calls:
        session.tool_calls = list(session.tool_calls or []) + recovered_tool_calls
        appended_any = True
    return appended_any


def _apply_core_sync_or_error_marker(
    session,
    core_path,
    stream_id_for_recheck=None,
    *,
    require_stream_dead=True,
    touch_updated_at=True,
) -> bool:
    """Inner repair logic. Must be called with the per-session lock already held.

    Re-checks session state under the lock, then either syncs messages from the
    core transcript (if present and non-empty) or restores the pending user
    message as a recovered user turn and appends an error marker.

    stream_id_for_recheck: when provided, repair bails if session.active_stream_id
    changed (e.g. context compression rotated it).  The cache-miss repair path
    also requires the stream to be absent from active streams; the streaming
    thread's final fallback passes require_stream_dead=False because it runs
    before its own stream is removed from STREAMS.

    Returns True if repair was applied, False if the re-check bailed out.
    Must never raise — caller is responsible for exception handling.
    """
    sid = session.session_id
    # Bail if pending is unset — nothing to repair.
    if not session.pending_user_message:
        return False
    if stream_id_for_recheck is not None:
        # Bail if active_stream_id rotated between the pre-lock check and now.
        # Cache-miss repair must also skip if the stream is alive again, but the
        # streaming thread's final fallback runs before removing its own stream
        # from STREAMS and must be allowed to repair that same active stream.
        if session.active_stream_id != stream_id_for_recheck:
            return False
        if require_stream_dead and session.active_stream_id in _active_stream_ids():
            return False

    # When messages is already non-empty, do not overwrite history from any core
    # transcript. The pending user turn may still be the only durable copy of a
    # prompt submitted just before a server restart, so materialize it before
    # clearing runtime stream state.
    if len(session.messages) != 0:
        _pending_text = " ".join(str(session.pending_user_message or "").split())
        _already_checkpointed = False
        if _pending_text and session.messages:
            _last_msg = session.messages[-1]
            if isinstance(_last_msg, dict) and _last_msg.get('role') == 'user':
                _last_text = " ".join(str(_last_msg.get('content') or "").split())
                _already_checkpointed = _last_text == _pending_text
        _recovered_ts = int(time.time())
        if isinstance(session.pending_started_at, (int, float)) and session.pending_started_at > 0:
            _recovered_ts = int(session.pending_started_at)
        if not _already_checkpointed:
            _append_recovered_pending_turn(session, timestamp=_recovered_ts)
        else:
            recovered = {
                'role': 'user',
                'content': session.pending_user_message,
                '_recovered': True,
            }
            if session.pending_attachments:
                recovered['attachments'] = list(session.pending_attachments)
            _append_recovered_turn_to_context(session, recovered)
        recovered_output = _append_journaled_partial_output(
            session,
            stream_id_for_recheck or session.active_stream_id,
        )
        session.active_stream_id = None
        session.pending_user_message = None
        session.pending_attachments = []
        session.pending_started_at = None
        session.messages.append(_interrupted_recovery_marker(recovered_output=recovered_output))
        session.save(touch_updated_at=touch_updated_at)
        logger.info(
            "Session %s: recovered pending user turn (messages non-empty), added error marker",
            sid,
        )
        return True

    # ── messages *is* empty ─ full repair ─────────────────────────────────

    if core_path.exists():
        with open(core_path, encoding='utf-8') as f:
            core = json.load(f)
        core_messages = core.get('messages', [])
        if core_messages:
            _stream_id = stream_id_for_recheck or session.active_stream_id
            session.messages = core_messages
            session.tool_calls = core.get('tool_calls', [])
            for field in ('input_tokens', 'output_tokens', 'estimated_cost'):
                if core.get(field) is not None:
                    setattr(session, field, core[field])
            _pending_text = _normalize_journal_recovery_text(session.pending_user_message)
            _already_checkpointed = False
            if _pending_text and session.messages:
                for _last_msg in reversed(session.messages):
                    if isinstance(_last_msg, dict) and _last_msg.get('role') == 'user':
                        _last_text = _normalize_journal_recovery_text(_last_msg.get('content'))
                        _already_checkpointed = _last_text == _pending_text
                        break
            if (
                _pending_text
                and not _already_checkpointed
                and _run_journal_has_visible_output(session, _stream_id)
            ):
                _recovered_ts = int(time.time())
                if isinstance(session.pending_started_at, (int, float)) and session.pending_started_at > 0:
                    _recovered_ts = int(session.pending_started_at)
                _append_recovered_pending_turn(session, timestamp=_recovered_ts)
            recovered_output = _append_journaled_partial_output(
                session,
                _stream_id,
                dedupe_existing=True,
            )
            session.active_stream_id = None
            session.pending_user_message = None
            session.pending_attachments = []
            session.pending_started_at = None
            if recovered_output:
                session.messages.append(
                    _interrupted_recovery_marker(recovered_output=True)
                )
            session.save(touch_updated_at=touch_updated_at)
            logger.info(
                "Session %s: synced %d messages from core transcript%s",
                sid,
                len(core_messages),
                " and recovered journaled output" if recovered_output else "",
            )
            return True

    # Core missing or empty — restore the pending user message as a recovered
    # user turn (preserving the draft), then append an error marker.
    if session.pending_user_message:
        # Use the original send time if available so the recovered turn
        # appears in the correct chronological position.
        _recovered_ts = int(time.time())
        if isinstance(session.pending_started_at, (int, float)) and session.pending_started_at > 0:
            _recovered_ts = int(session.pending_started_at)
        _append_recovered_pending_turn(session, timestamp=_recovered_ts)
    recovered_output = _append_journaled_partial_output(
        session,
        stream_id_for_recheck or session.active_stream_id,
    )
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    session.messages.append(_interrupted_recovery_marker(recovered_output=recovered_output))
    session.save(touch_updated_at=touch_updated_at)
    logger.info("Session %s: no core transcript found, added error marker", sid)
    return True


# ── _repair_stale_pending grace period (#1624) ─────────────────────────────
#
# Defense-in-depth against a narrow race between the streaming thread clearing
# pending_user_message and STREAMS.pop(stream_id). Without this guard, any
# fast turn (e.g. command approval) that exits the thread before the on-disk
# pending clear has flushed gets misdiagnosed as a crashed turn, producing a
# spurious "Response interrupted." marker.
#
# 30s covers the worst-case post-loop persistence window: LLM finishing a tool
# batch + lock contention with the checkpoint thread + a multi-MB session.save.
# A legitimately crashed turn whose pending_started_at is < 30s old will not
# repair on the first get_session() call, but WILL repair on the next call
# after the grace period elapses (typically the user's next interaction).
#
# Missing/falsy pending_started_at (legacy sidecars from before that field
# existed, or any path that forgot to set it) is treated as "old enough" so
# repair still recovers them — preserves current behavior for legacy data.
_REPAIR_STALE_PENDING_GRACE_SECONDS = 30


def _repair_stale_pending(session) -> bool:
    """Recover a sidecar stuck with messages=[] and stale pending state.

    Fires only when messages is empty, pending_user_message is set,
    active_stream_id is set, the stream is no longer alive, AND the turn is
    older than _REPAIR_STALE_PENDING_GRACE_SECONDS (#1624).

    Uses a non-blocking lock acquire so a caller that already holds the
    per-session lock (e.g. retry_last, undo_last, cancel_stream) cannot
    deadlock when get_session() triggers this on a cache miss.

    Returns True if repair was applied, False otherwise.
    Must never raise — all errors are caught and logged.
    """
    # Capture the stream id seen at pre-check time; the under-lock re-check in
    # _apply_core_sync_or_error_marker uses this to detect a rotated active_stream_id
    # (e.g. context compression) or a stream that came back alive.
    _seen_stream_id = session.active_stream_id
    if (not session.pending_user_message
            or not _seen_stream_id
            or _seen_stream_id in _active_stream_ids()):
        return False

    # Grace-period guard: bail if the turn is too fresh to be a real crash.
    # Falsy pending_started_at (None, 0, missing) means "old enough" — preserve
    # legacy-data recovery semantics for sessions that pre-date the field.
    _started = getattr(session, 'pending_started_at', None)
    if _started:
        try:
            _age = time.time() - float(_started)
        except (TypeError, ValueError):
            _age = float('inf')
        if _age < _REPAIR_STALE_PENDING_GRACE_SECONDS:
            logger.debug(
                "_repair_stale_pending: skipping repair for session %s — "
                "pending_started_at age=%.1fs < %ds grace window",
                session.session_id, _age, _REPAIR_STALE_PENDING_GRACE_SECONDS,
            )
            return False
    else:
        # Treat missing/falsy pending_started_at as "old enough" (legacy data).
        _age = float('inf')

    sid = session.session_id
    if not sid or not all(c in '0123456789abcdefghijklmnopqrstuvwxyz_' for c in sid):
        return False

    try:
        profile_home = _get_profile_home(session.profile)
        core_path = profile_home / 'sessions' / f'session_{sid}.json'

        lock = _get_session_agent_lock(sid)
        # Non-blocking acquire: bail immediately if the caller already holds this
        # lock (e.g. retry_last, undo_last, cancel_stream). Blocking would deadlock
        # because _get_session_agent_lock returns a non-reentrant threading.Lock.
        if not lock.acquire(blocking=False):
            logger.debug(
                "_repair_stale_pending: lock contended, skipping repair for session %s", sid,
            )
            return False
        try:
            # Telemetry (#1624): log legitimate repair firings so the next batch
            # of user reports tells us whether the underlying race still fires
            # post-fix. Rate-limit by age (Opus pre-release SHOULD-FIX): WARNING
            # for the diagnostically valuable race window (< 5 min — actual
            # leak-path candidates that slipped past the grace guard) and DEBUG
            # for the long-tail (orphaned sidecars from prior process lifetimes)
            # so reconnect loops on stuck sessions don't flood the log.
            _DIAG_WARN_WINDOW_SECONDS = 300  # 5 min
            _age_str = ('inf' if _age == float('inf') else f'{_age:.1f}s')
            _log = logger.warning if _age < _DIAG_WARN_WINDOW_SECONDS else logger.debug
            _log(
                "_repair_stale_pending firing: session=%s stream_id=%s pending_age=%s",
                sid, _seen_stream_id, _age_str,
            )
            return _apply_core_sync_or_error_marker(
                session, core_path, stream_id_for_recheck=_seen_stream_id,
            )
        finally:
            lock.release()
    except Exception:
        logger.exception("_repair_stale_pending failed for session %s", sid)
        return False


def get_session(sid, metadata_only=False):
    """Load a session, optionally with metadata only (skipping the messages array).

    Metadata-only loads intentionally do not populate the full-session cache.
    Otherwise a later full load could return a compact object with an empty
    messages list. Use this when you only need compact() metadata and not the
    actual message history (e.g., for fast sidebar switching).
    """
    cached = _get_cached_session(SESSIONS, LOCK, sid)
    if cached is not None:
        return cached
    if metadata_only:
        s = Session.load_metadata_only(sid)
        if s:
            return s
    else:
        s = Session.load(sid)
    if s:
        _cache_session(SESSIONS, LOCK, sid, s, SESSIONS_MAX)
        if not metadata_only:
            try:
                repaired = _repair_stale_pending(s)
                # If repair had to bail because the per-session lock was held,
                # do not pin the still-stale sidecar in the LRU cache forever.
                # Leaving it cached would prevent future get_session() calls from
                # re-entering the cache-miss repair path after the lock holder exits.
                if not repaired and (len(s.messages) == 0
                        and s.pending_user_message
                        and s.active_stream_id
                        and s.active_stream_id not in _active_stream_ids()):
                    _evict_cached_session_if_same(SESSIONS, LOCK, sid, s)
            except Exception:
                pass  # repair is best-effort
        return s
    raise KeyError(sid)

def new_session(workspace=None, model=None, profile=None, model_provider=None, project_id=None, worktree_info=None):
    """Create a new in-memory session.

    The session lives in the SESSIONS dict only — no disk write happens until
    the first message is appended (#1171 follow-up).  This avoids the
    "ghost Untitled session on disk" pile-up that occurred when users clicked
    New Conversation, reloaded the page, or completed onboarding without ever
    sending a message.  Subsequent code paths that populate state immediately
    (btw / background agent at api/routes.py) call ``s.save()`` themselves
    after setting title/messages, and ``_handle_chat_start`` saves the
    session as soon as the user actually sends a message — both are the
    natural first-write moments for a real session.

    Crash-safety: if the process exits between session creation and first
    message, the session is lost.  Since it had no messages, there is
    nothing to lose.  Worktree-backed sessions are the exception: they are
    saved immediately because creating the session also creates real
    filesystem state that must remain discoverable after restart.

    *profile* — when supplied by the caller (e.g. from the request body sent
    by the active browser tab), it is used directly so that concurrent clients
    on different profiles don't fight over a shared process-global.  If not
    supplied, we fall back to the process-level active profile (the pre-#798
    behaviour, preserved for calls that originate outside a request context).
    """
    if profile is None:
        # Fallback: read process-level global (single-client or startup path)
        try:
            from api.profiles import get_active_profile_name
            profile = get_active_profile_name()
        except ImportError:
            profile = None
    effective_model = model or get_effective_default_model()
    wt = worktree_info if isinstance(worktree_info, dict) else None
    workspace_path = (wt.get('path') if wt and wt.get('path') else workspace) if wt else workspace
    s = Session(
        workspace=workspace_path or get_last_workspace(),
        model=effective_model,
        model_provider=model_provider,
        profile=profile,
        project_id=project_id,
        worktree_path=wt.get('path') if wt else None,
        worktree_branch=wt.get('branch') if wt else None,
        worktree_repo_root=wt.get('repo_root') if wt else None,
        worktree_created_at=wt.get('created_at') if wt else None,
    )
    _cache_session(SESSIONS, LOCK, s.session_id, s, SESSIONS_MAX)
    if wt:
        s.save()
    return s

def _hide_from_default_sidebar(session: dict) -> bool:
    return _hide_from_default_sidebar_impl(session)


def _sidebar_message_count(session: dict) -> int:
    return _sidebar_message_count_impl(session)


def _sidebar_lineage_root_id(session: dict, sessions_by_id: dict[str, dict]) -> str:
    return _sidebar_lineage_root_id_impl(session, sessions_by_id)


def _has_live_sidebar_state(session: dict) -> bool:
    return _has_live_sidebar_state_impl(session)


def _prefer_fuller_snapshots_for_sidebar(sessions: list[dict]) -> list[dict]:
    return _prefer_fuller_snapshots_for_sidebar_impl(
        sessions,
        sort_timestamp=_session_sort_timestamp,
    )


def _strip_sidebar_internal_flags(sessions: list[dict]) -> None:
    _strip_sidebar_internal_flags_impl(sessions)


def _active_state_db_path() -> Path:
    """Return state.db for the active Hermes profile, degrading to HERMES_HOME."""
    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()
    return hermes_home / 'state.db'


def _sidebar_title_is_generic_webui(title: str | None) -> bool:
    return _sidebar_title_is_generic_webui_impl(title)


def _enrich_sidebar_lineage_metadata(sessions: list[dict]) -> None:
    _enrich_sidebar_lineage_metadata_impl(
        sessions,
        state_db_path=_active_state_db_path(),
        read_lineage_metadata=read_session_lineage_metadata,
    )


def _diag_stage(diag, name: str) -> None:
    if diag is not None:
        try:
            diag.stage(name)
        except Exception:
            pass


def all_sessions(diag=None):
    _diag_stage(diag, "all_sessions.active_streams")
    active_stream_ids = _active_stream_ids()
    # Phase C: try index first for O(1) read; fall back to full scan
    _diag_stage(diag, "all_sessions.index_exists")
    if SESSION_INDEX_FILE.exists():
        try:
            _diag_stage(diag, "all_sessions.read_index")
            index = json.loads(SESSION_INDEX_FILE.read_text(encoding='utf-8'))
            _diag_stage(diag, "all_sessions.prune_index")
            with LOCK:
                in_memory_ids = set(SESSIONS.keys())
            index = [
                s for s in index
                if _index_entry_exists(s.get('session_id'), in_memory_ids=in_memory_ids)
            ]
            backfilled = []
            for i, s in enumerate(index):
                if 'last_message_at' not in s:
                    _diag_stage(diag, "all_sessions.backfill_load")
                    full = Session.load(s.get('session_id'))
                    if full:
                        index[i] = full.compact()
                        backfilled.append(full)
            if backfilled:
                try:
                    _diag_stage(diag, "all_sessions.backfill_write")
                    _write_session_index(updates=backfilled)
                except Exception:
                    logger.debug("Failed to persist last_message_at backfill")
            _diag_stage(diag, "all_sessions.mark_streaming")
            for s in index:
                s['is_streaming'] = _is_streaming_session(
                    s.get('active_stream_id'),
                    active_stream_ids,
                )
            # Overlay any in-memory sessions that may be newer than the index
            _diag_stage(diag, "all_sessions.overlay_lock")
            index_map = {s['session_id']: s for s in index}
            with LOCK:
                for s in SESSIONS.values():
                    index_map[s.session_id] = s.compact(
                        include_runtime=True,
                        active_stream_ids=active_stream_ids,
                    )
            _diag_stage(diag, "all_sessions.sort_filter")
            result = sorted(index_map.values(), key=lambda s: (s.get('pinned', False), _session_sort_timestamp(s)), reverse=True)
            # Hide empty Untitled sessions from the UI entirely — they are ephemeral
            # scratch pads that only become real once the first message is sent (#1171).
            # No grace window: a 0-message Untitled session is never shown in the list
            # regardless of age. This means page refreshes and accidental New Conversation
            # clicks never leave orphan entries in the sidebar.
            #
            # Exception: sessions with active_stream_id set are actively streaming (#1327).
            # #1184 deferred the first save() until the first message, so during the
            # initial streaming turn the session still looks like Untitled+0-messages.
            # Without this exemption, navigating away during a long first turn causes
            # the session to vanish from the sidebar.
            result = [s for s in result if not (
                s.get('title', 'Untitled') == 'Untitled'
                and s.get('message_count', 0) == 0
                and not s.get('active_stream_id')
                and not s.get('has_pending_user_message')
                and not s.get('worktree_path')
            )]
            result = _prefer_fuller_snapshots_for_sidebar(result)
            result = [s for s in result if not _hide_from_default_sidebar(s)]
            _strip_sidebar_internal_flags(result)
            # Backfill: sessions created before Sprint 22 have no profile tag.
            # Attribute them to 'default' so the client profile filter works correctly.
            for s in result:
                if not s.get('profile'):
                    s['profile'] = 'default'
            _diag_stage(diag, "all_sessions.lineage_metadata")
            _enrich_sidebar_lineage_metadata(result)
            return result
        except Exception:
            logger.debug("Failed to load session index, falling back to full scan")
    # Full scan fallback
    _diag_stage(diag, "all_sessions.full_scan")
    out = []
    for p in SESSION_DIR.glob('*.json'):
        if p.name.startswith('_'): continue
        try:
            s = Session.load(p.stem)
            if s: out.append(s)
        except Exception:
            logger.debug("Failed to load session from %s", p)
    _diag_stage(diag, "all_sessions.full_scan_overlay")
    for s in SESSIONS.values():
        if all(s.session_id != x.session_id for x in out): out.append(s)
    _diag_stage(diag, "all_sessions.full_scan_sort_filter")
    out.sort(key=lambda s: (getattr(s, 'pinned', False), _session_sort_timestamp(s)), reverse=True)
    # Hide empty Untitled sessions from the UI entirely — kept consistent with the
    # index-path filter above. No grace window: a 0-message Untitled session is
    # never shown regardless of age (#1171).  Same streaming exemption as above (#1327).
    result = [s.compact(include_runtime=True, active_stream_ids=active_stream_ids) for s in out if not (
        s.title == 'Untitled'
        and len(s.messages) == 0
        and not s.active_stream_id
        and not s.pending_user_message
        and not getattr(s, 'worktree_path', None)
    )]
    result = _prefer_fuller_snapshots_for_sidebar(result)
    result = [s for s in result if not _hide_from_default_sidebar(s)]
    _strip_sidebar_internal_flags(result)
    for s in result:
        if not s.get('profile'):
            s['profile'] = 'default'
    _diag_stage(diag, "all_sessions.lineage_metadata")
    _enrich_sidebar_lineage_metadata(result)
    return result


def title_from(messages, fallback: str='Untitled'):
    """Derive a session title from the first user message."""
    for m in messages:
        if m.get('role') == 'user':
            c = m.get('content', '')
            if isinstance(c, list):
                c = ' '.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text')
            text = str(c).strip()
            if text:
                return text[:64]
    return fallback


# ── Project helpers ──────────────────────────────────────────────────────────

_PROJECTS_MIGRATION_LOCK = threading.Lock()
_projects_migrated = False


def _backfill_project_profiles_if_needed(projects: list) -> bool:
    """Tag any legacy untagged projects (`profile` missing) with a sensible default.

    Strategy:
      1. For each untagged project, look at the sessions assigned to it via
         the session index. If any session carries a profile, take that
         profile.  Most installs are single-profile so this picks up the
         right answer for everyone.
      2. Otherwise default to 'default'.

    Returns True if any project was mutated. Safe to call repeatedly — once
    every project is tagged, this is a no-op. Runs at most once per process
    (cached via the module-level _projects_migrated flag) but the result is
    persisted so it's a one-time write.
    """
    return _backfill_project_profiles_impl(
        projects,
        session_index_file=SESSION_INDEX_FILE,
        logger=logger,
    )


def _get_projects_migrated() -> bool:
    return _projects_migrated


def _set_projects_migrated(value: bool) -> None:
    global _projects_migrated
    _projects_migrated = bool(value)


def load_projects(*, _migrate: bool = True) -> list:
    """Load project list from disk. Returns list of project dicts.

    On first call, runs a one-time migration to back-fill the `profile` field
    on legacy untagged projects (#1614). Disable via `_migrate=False` for
    callsites that want the raw on-disk shape (test fixtures, e.g.).
    """
    return _load_projects_impl(
        projects_file=PROJECTS_FILE,
        session_index_file=SESSION_INDEX_FILE,
        migration_lock=_PROJECTS_MIGRATION_LOCK,
        get_migrated=_get_projects_migrated,
        set_migrated=_set_projects_migrated,
        save_projects_fn=save_projects,
        logger=logger,
        _migrate=_migrate,
    )


def save_projects(projects) -> None:
    """Write project list to disk."""
    _save_projects_impl(PROJECTS_FILE, projects)


CRON_PROJECT_NAME = 'Cron Jobs'
_CRON_PROJECT_LOCK = threading.Lock()


def ensure_cron_project() -> str:
    """Return the project_id of the system "Cron Jobs" project for the active profile.

    Each profile gets its own "Cron Jobs" project so cron-spawned sessions in
    profile A don't surface under the cron chip of profile B (#1614). Lookup
    keys on (name, profile) — a legacy untagged "Cron Jobs" project (no
    `profile` field) is treated as belonging to whichever profile first calls
    this in a given install, then re-tagged.

    Thread-safe and idempotent.  Returns a 12-char hex project_id string.
    """
    from api.profiles import get_active_profile_name, _is_root_profile

    return _ensure_cron_project_impl(
        load_projects_fn=load_projects,
        save_projects_fn=save_projects,
        cron_lock=_CRON_PROJECT_LOCK,
        get_active_profile_name=get_active_profile_name,
        is_root_profile=_is_root_profile,
        make_project_id=lambda: uuid.uuid4().hex[:12],
        now=time.time,
        cron_project_name=CRON_PROJECT_NAME,
    )


def is_cron_session(session_id: str, source_tag: str = None) -> bool:
    """Return True if a session originates from a cron job."""
    if source_tag == 'cron':
        return True
    sid = str(session_id or '')
    return sid.startswith('cron_')



def import_cli_session(
    session_id: str,
    title: str,
    messages,
    model: str='unknown',
    profile=None,
    created_at=None,
    updated_at=None,
    parent_session_id=None,
):
    """Create a new WebUI session populated with CLI/agent messages.

    Preserve parent_session_id from state.db so imported continuation segments
    keep their lineage in the WebUI store and sidebar instead of reappearing as
    detached orphan chats.
    """
    s = Session(
        session_id=session_id,
        title=title,
        workspace=get_last_workspace(),
        model=model,
        messages=messages,
        profile=profile,
        created_at=created_at,
        updated_at=updated_at,
        parent_session_id=parent_session_id,
    )
    s.save(touch_updated_at=False)
    return s


# ── CLI session bridge ──────────────────────────────────────────────────────


def _default_claude_code_projects_dir() -> Path | None:
    """Resolve the Claude Code projects directory without touching real home in tests."""
    return _default_claude_code_projects_dir_impl()


def _claude_code_session_id(path: Path) -> str:
    return _claude_code_session_id_impl(path)


def _parse_claude_code_timestamp(value):
    return _parse_claude_code_timestamp_impl(value)


def _extract_claude_code_text(content) -> str:
    return _extract_claude_code_text_impl(content)


def _parse_claude_code_jsonl(path: Path, *, max_messages: int = CLAUDE_CODE_MAX_MESSAGES_PER_FILE) -> tuple[list[dict], str | None, float | None, float | None]:
    return _parse_claude_code_jsonl_impl(path, max_messages=max_messages)


def _iter_claude_code_jsonl_files(projects_dir: Path | str | None = None, *, max_files: int = CLAUDE_CODE_MAX_FILES, max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES):
    return _iter_claude_code_jsonl_files_impl(
        projects_dir,
        default_projects_dir_fn=_default_claude_code_projects_dir,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )


def _claude_code_title(messages: list[dict], summary_title: str | None) -> str:
    return _claude_code_title_impl(messages, summary_title)


def get_claude_code_sessions(projects_dir: Path | str | None = None, *, max_files: int = CLAUDE_CODE_MAX_FILES, max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES) -> list:
    """Read Claude Code JSONL sessions as read-only external-agent rows.

    The bridge is additive and defensive: it skips symlinks, oversized files,
    malformed lines, and per-file errors rather than crashing WebUI session
    listing. Tests pass ``projects_dir`` fixtures so Michael's real ~/.claude is
    never read during test runs.
    """
    return _get_claude_code_sessions_impl(
        projects_dir,
        get_workspace=get_last_workspace,
        default_projects_dir_fn=_default_claude_code_projects_dir,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )


def get_claude_code_session_messages(sid, projects_dir: Path | str | None = None) -> list:
    """Return messages for one read-only Claude Code JSONL session."""
    return _get_claude_code_session_messages_impl(
        sid,
        projects_dir,
        default_projects_dir_fn=_default_claude_code_projects_dir,
    )


def clear_cli_sessions_cache() -> None:
    with _CLI_SESSIONS_CACHE_LOCK:
        _CLI_SESSIONS_CACHE.clear()


def _copy_cli_sessions(sessions: list) -> list:
    return copy.deepcopy(sessions)


def _cli_sessions_cache_ttl_seconds() -> float:
    try:
        return max(0.0, float(_CLI_SESSIONS_CACHE_TTL_SECONDS))
    except (TypeError, ValueError):
        return 5.0


def _path_cache_key(path) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).expanduser().resolve(strict=False))
    except Exception:
        return str(path)


def _path_stat_cache_key(path):
    if path is None:
        return None
    try:
        st = Path(path).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _sqlite_file_stat_cache_key(db_path: Path):
    """Return a cheap invalidation key for a SQLite DB and WAL sidecars."""
    return (
        _path_stat_cache_key(db_path),
        _path_stat_cache_key(Path(f"{db_path}-wal")),
        _path_stat_cache_key(Path(f"{db_path}-shm")),
    )


def _resolve_cli_sessions_context():
    # Use the active WebUI profile's HERMES_HOME to find state.db.
    # The active profile is determined by what the user has selected in the UI
    # (stored in the server's runtime config). This means:
    #   - default profile  -> ~/.hermes/state.db
    #   - named profile X  -> ~/.hermes/profiles/X/state.db
    # We resolve the active profile's home directory rather than just using
    # HERMES_HOME (which is the server's launch profile, not necessarily the
    # active one after a profile switch).
    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()

    try:
        from api.profiles import get_active_profile_name
        cli_profile = get_active_profile_name()
    except Exception:
        cli_profile = None

    db_path = hermes_home / 'state.db'
    projects_dir = _default_claude_code_projects_dir()
    cache_key = (
        str(hermes_home),
        str(cli_profile or ''),
        str(db_path),
        _sqlite_file_stat_cache_key(db_path),
        _path_cache_key(projects_dir),
        _path_stat_cache_key(projects_dir),
        _path_stat_cache_key(SESSION_INDEX_FILE),
    )
    return hermes_home, db_path, cli_profile, cache_key


def _load_cli_sessions_uncached(hermes_home: Path, db_path: Path, _cli_profile) -> list:
    cli_sessions = []
    try:
        cli_sessions.extend(get_claude_code_sessions())
    except Exception:
        logger.debug("Claude Code session scan failed", exc_info=True)

    if not db_path.exists():
        return cli_sessions

    # Memoize the cron project ID for this scan so we don't pay a lock-acquire +
    # disk-read of projects.json per cron session in the loop below.
    # Resolved lazily on the first cron session we encounter.
    _cron_pid_cache = [None]  # list-as-cell so the closure can mutate
    def _cron_pid():
        if _cron_pid_cache[0] is None:
            _cron_pid_cache[0] = ensure_cron_project()
        return _cron_pid_cache[0]

    for row in read_importable_agent_session_rows(
        db_path,
        limit=CLI_VISIBLE_SESSION_LIMIT,
        log=logger,
        exclude_sources=None,
    ):
        sid = row['id']
        raw_ts = row['last_activity'] or row['started_at']
        # Prefer the CLI session's own profile from the DB; fall back to
        # the active CLI profile so sidebar filtering works either way.
        profile = _cli_profile  # CLI DB has no profile column; use active profile

        _source = row['source'] or 'cli'
        _title = row['title']
        if not _title and _source == 'cron' and sid.startswith('cron_'):
            # Extract job_id from session ID (cron_{job_id}_{timestamp})
            # and look up the human-friendly job name from jobs.json
            parts = sid.split('_')
            if len(parts) >= 3:
                _job_id = parts[1]
                try:
                    _jobs_path = hermes_home / 'cron' / 'jobs.json'
                    if _jobs_path.exists():
                        import json as _json
                        _jobs_data = _json.loads(_jobs_path.read_text())
                        for _j in _jobs_data.get('jobs', []):
                            if _j.get('id') == _job_id:
                                _title = _j.get('name') or _title
                                break
                except Exception:
                    pass  # degrade gracefully
        # If a WebUI JSON file exists for this session (e.g. previously
        # imported or renamed in the sidebar), prefer its title over the
        # state.db title.  This fixes rename-not-persisting for CLI sessions
        # after compression chain extension (#1486).
        try:
            _webui_meta = Session.load_metadata_only(sid)
            if _webui_meta and getattr(_webui_meta, 'title', None):
                _title = _webui_meta.title
        except Exception:
            pass
        _display_title = _title or f'{_source.title()} Session'
        cli_sessions.append({
            'session_id': sid,
            'title': _display_title,
            'workspace': str(get_last_workspace()),
            'model': row['model'] or None,
            'message_count': row['message_count'] or row['actual_message_count'] or 0,
            'created_at': row['started_at'],
            'updated_at': raw_ts,
            'pinned': False,
            'archived': False,
            'project_id': _cron_pid() if is_cron_session(sid, _source) else None,
            'profile': profile,
            'source_tag': _source,
            'raw_source': row.get('raw_source'),
            'user_id': row.get('user_id'),
            'chat_id': row.get('chat_id') or row.get('origin_chat_id'),
            'chat_type': row.get('chat_type'),
            'thread_id': row.get('thread_id'),
            'session_key': row.get('session_key'),
            'platform': row.get('platform'),
            'session_source': row.get('session_source'),
            'source_label': row.get('source_label'),
            'parent_session_id': row.get('parent_session_id'),
            'parent_title': row.get('parent_title'),
            'parent_source': row.get('parent_source'),
            'relationship_type': row.get('relationship_type'),
            '_parent_lineage_root_id': row.get('_parent_lineage_root_id'),
            'end_reason': row.get('end_reason'),
            'actual_message_count': row.get('actual_message_count'),
            'user_message_count': row.get('actual_user_message_count'),
            '_lineage_root_id': row.get('_lineage_root_id'),
            '_lineage_tip_id': row.get('_lineage_tip_id'),
            '_compression_segment_count': row.get('_compression_segment_count'),
            'is_cli_session': True,
        })

    return cli_sessions


def get_cli_sessions() -> list:
    """Read CLI sessions from the agent's SQLite store and return them as
    dicts in a format the WebUI sidebar can render alongside local sessions.

    Returns empty list if the SQLite DB is missing or any error occurs -- the
    bridge is purely additive and never crashes the WebUI.
    """
    hermes_home, db_path, cli_profile, cache_key = _resolve_cli_sessions_context()
    ttl = _cli_sessions_cache_ttl_seconds()
    now = time.monotonic()

    if ttl > 0:
        with _CLI_SESSIONS_CACHE_LOCK:
            cached = _CLI_SESSIONS_CACHE.get(cache_key)
            if cached:
                expires_at, cached_sessions = cached
                if expires_at > now:
                    return _copy_cli_sessions(cached_sessions)
                _CLI_SESSIONS_CACHE.pop(cache_key, None)
            try:
                sessions = _load_cli_sessions_uncached(hermes_home, db_path, cli_profile)
            except Exception as _cli_err:
                logger.warning(
                    "get_cli_sessions() failed — check state.db schema or path (%s): %s",
                    db_path, _cli_err,
                )
                return []
            _CLI_SESSIONS_CACHE[cache_key] = (
                time.monotonic() + ttl,
                _copy_cli_sessions(sessions),
            )
            return _copy_cli_sessions(sessions)

    try:
        return _load_cli_sessions_uncached(hermes_home, db_path, cli_profile)
    except Exception as _cli_err:
        logger.warning(
            "get_cli_sessions() failed — check state.db schema or path (%s): %s",
            db_path, _cli_err,
        )
        return []


def _json_loads_if_string(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return value


def get_cli_session_messages(sid) -> list:
    """Read messages for a single CLI/external-agent session.

    Preserve tool-call/result and reasoning metadata from the agent state.db so
    CLI-origin transcripts render with the same tool cards as WebUI-native
    sessions. When the requested session is the tip of a compression/CLI-close
    continuation chain, return the stitched full transcript across all segments
    in chronological order. Returns empty list on any error.
    """
    if str(sid or '').startswith(f'{CLAUDE_CODE_SOURCE}_'):
        return get_claude_code_session_messages(sid)
    try:
        import sqlite3
    except ImportError:
        return []

    db_path = _active_state_db_path()
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
                        if not _is_continuation_session(parent_dict, current):
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
                    if col in {'tool_calls', 'reasoning_details', 'codex_reasoning_items', 'codex_message_items'}:
                        value = _json_loads_if_string(value)
                    msg[col] = value
                if msg.get('role') == 'tool' and msg.get('tool_name') and not msg.get('name'):
                    msg['name'] = msg['tool_name']
                msgs.append(msg)
    except Exception:
        return []
    return msgs


def count_conversation_rounds(sid: str, since: float | None = None) -> int:
    """Count conversation rounds for a session from state.db.

    A "round" = one user message + one agent reply.  Consecutive user
    messages are merged into a single round so that multi-part questions
    don't inflate the count.

    Parameters
    ----------
    sid : str
        Gateway session ID (e.g. ``20260430_151231_7209a0``).
    since : float | None
        Unix timestamp.  If provided, only messages **after** this
        timestamp are counted.

    Returns
    -------
    int
        Number of complete conversation rounds.
    """
    import os, sqlite3, datetime

    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()
    db_path = hermes_home / 'state.db'
    if not db_path.exists():
        return 0

    try:
        with sqlite3.connect(str(db_path)) as conn:
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
    seen_user = False          # have we seen a user msg in the current round?
    seen_agent_after_user = False  # have we seen an agent reply after that user msg?

    for row in rows:
        role = (row['role'] or '').strip().lower()
        ts_raw = row['timestamp']

        # Parse timestamp and apply the ``since`` filter.
        if since is not None and ts_raw is not None:
            try:
                if isinstance(ts_raw, (int, float)):
                    ts_val = float(ts_raw)
                else:
                    # ISO-8601 string
                    ts_val = datetime.datetime.fromisoformat(
                        str(ts_raw).replace('Z', '+00:00')
                    ).timestamp()
                if ts_val <= since:
                    continue
            except Exception:
                pass

        if role == 'user':
            if seen_user and not seen_agent_after_user:
                # Consecutive user message — merge into current round.
                pass
            elif seen_user and seen_agent_after_user:
                # Previous round completed, starting a new one.
                rounds += 1
                seen_agent_after_user = False
            seen_user = True
        elif role == 'assistant':
            if seen_user:
                seen_agent_after_user = True

    # Close the last round if it was completed.
    if seen_user and seen_agent_after_user:
        rounds += 1

    return rounds


CONVERSATION_ROUND_THRESHOLD = 10


def delete_cli_session(sid) -> bool:
    """Delete a CLI session from state.db (messages + session row).
    Returns True if deleted, False if not found or error.
    """
    import os
    try:
        import sqlite3
    except ImportError:
        return False

    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()
    db_path = hermes_home / 'state.db'
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
