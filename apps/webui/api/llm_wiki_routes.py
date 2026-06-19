"""LLM Wiki status helpers for WebUI routes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable


def active_hermes_home() -> Path:
    try:
        from api.profiles import get_active_hermes_home

        return Path(get_active_hermes_home()).expanduser()
    except Exception:
        return Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()


def env_file_path(hermes_home: Path) -> str | None:
    env_path = hermes_home / ".env"
    if not env_path.exists() or not env_path.is_file():
        return None
    try:
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != "WIKI_PATH":
                continue
            value = value.strip().strip('"').strip("'")
            return value or None
    except Exception:
        return None
    return None


def get_config_path_value(config: dict, dotted_key: str) -> str | None:
    if not isinstance(config, dict):
        return None
    if dotted_key in config and config.get(dotted_key):
        return str(config.get(dotted_key))
    cur = config
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return str(cur) if cur else None


def config_path() -> str | None:
    try:
        from api.config import get_config as _get_cfg

        cfg = _get_cfg()
    except Exception:
        return None
    return (
        get_config_path_value(cfg, "skills.config.wiki.path")
        or get_config_path_value(cfg, "wiki.path")
    )


def resolve_path(
    *,
    active_home_fn: Callable[[], Path] = active_hermes_home,
    env_file_path_fn: Callable[[Path], str | None] = env_file_path,
    config_path_fn: Callable[[], str | None] = config_path,
) -> tuple[Path, str, bool]:
    hermes_home = active_home_fn()
    raw = os.getenv("WIKI_PATH") or env_file_path_fn(hermes_home)
    source = "WIKI_PATH" if raw else "default"
    configured = bool(raw)
    if not raw:
        raw = config_path_fn()
        if raw:
            source = "skills.config.wiki.path"
            configured = True
    if not raw:
        raw = "~/wiki"
    return Path(os.path.expandvars(raw)).expanduser(), source, configured


def safe_iso(ts: float | None) -> str | None:
    if not ts:
        return None
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def build_status(
    *,
    docs_url: str,
    resolve_path_fn: Callable[[], tuple[Path, str, bool]],
    page_files_fn: Callable[[Path], list[Path]],
    count_files_fn: Callable[[Path], int],
    safe_iso_fn: Callable[[float | None], str | None] = safe_iso,
) -> dict:
    """Return private-safe LLM Wiki status metadata without reading page bodies."""
    try:
        wiki_path, path_source, path_configured = resolve_path_fn()
        base = {
            "available": False,
            "enabled": False,
            "status": "missing",
            "entry_count": 0,
            "page_count": 0,
            "raw_source_count": 0,
            "last_updated": None,
            "last_writer": None,
            "path_configured": path_configured,
            "path_source": path_source,
            "toggle_available": False,
            "toggle_reason": "Hermes Agent exposes WIKI_PATH/wiki.path for location, but no stable on/off config flag is currently available.",
            "docs_url": docs_url,
        }
        if not wiki_path.exists():
            return base
        if not wiki_path.is_dir():
            base["status"] = "not_directory"
            return base

        page_files = page_files_fn(wiki_path)
        status_files = [path for path in (wiki_path / "SCHEMA.md", wiki_path / "index.md", wiki_path / "log.md") if path.exists() and path.is_file()]
        status_files.extend(page_files)
        latest = None
        for item in status_files:
            try:
                mtime = item.stat().st_mtime
            except Exception:
                continue
            latest = mtime if latest is None else max(latest, mtime)

        base.update({
            "available": True,
            "enabled": True,
            "status": "ready" if page_files else "empty",
            "entry_count": len(page_files),
            "page_count": len(page_files),
            "raw_source_count": count_files_fn(wiki_path / "raw"),
            "last_updated": safe_iso_fn(latest),
        })
        return base
    except Exception as exc:
        return {
            "available": False,
            "enabled": False,
            "status": "error",
            "entry_count": 0,
            "page_count": 0,
            "raw_source_count": 0,
            "last_updated": None,
            "last_writer": None,
            "path_configured": False,
            "path_source": "unknown",
            "toggle_available": False,
            "toggle_reason": "Unable to inspect LLM Wiki status safely.",
            "docs_url": docs_url,
            "error": type(exc).__name__,
        }
