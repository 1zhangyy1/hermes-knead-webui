"""Memory API route handlers."""

from __future__ import annotations

from pathlib import Path


def _memory_paths() -> tuple[Path, Path, Path]:
    try:
        from api.profiles import get_active_hermes_home

        home = get_active_hermes_home()
        mem_dir = home / "memories"
    except ImportError:
        home = Path.home() / ".hermes"
        mem_dir = home / "memories"
    return mem_dir / "MEMORY.md", mem_dir / "USER.md", home / "SOUL.md"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def handle_memory_read(
    handler,
    *,
    json_response_fn,
    redact_text_fn,
) -> bool:
    mem_file, user_file, soul_file = _memory_paths()
    memory = _read_text(mem_file)
    user = _read_text(user_file)
    soul = _read_text(soul_file)
    return json_response_fn(
        handler,
        {
            "memory": redact_text_fn(memory),
            "user": redact_text_fn(user),
            "soul": redact_text_fn(soul),
            "memory_path": str(mem_file),
            "user_path": str(user_file),
            "soul_path": str(soul_file),
            "memory_mtime": mem_file.stat().st_mtime if mem_file.exists() else None,
            "user_mtime": user_file.stat().st_mtime if user_file.exists() else None,
            "soul_mtime": soul_file.stat().st_mtime if soul_file.exists() else None,
        },
    )


def handle_memory_write(
    handler,
    body,
    *,
    require_fn,
    json_response_fn,
    bad_response_fn,
) -> bool:
    try:
        require_fn(body, "section", "content")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))

    mem_file, user_file, soul_file = _memory_paths()
    mem_file.parent.mkdir(parents=True, exist_ok=True)
    section = body["section"]
    if section == "memory":
        target = mem_file
    elif section == "user":
        target = user_file
    elif section == "soul":
        target = soul_file
    else:
        return bad_response_fn(handler, 'section must be "memory", "user", or "soul"')
    target.write_text(body["content"], encoding="utf-8")
    return json_response_fn(handler, {"ok": True, "section": section, "path": str(target)})
