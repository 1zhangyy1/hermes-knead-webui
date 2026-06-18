"""Attachment and native multimodal message helpers for streaming requests."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path


NATIVE_IMAGE_MAX_BYTES = 20 * 1024 * 1024

IMAGE_MAGIC: dict[bytes | None, frozenset[str]] = {
    b'\x89PNG\r\n\x1a\n': frozenset({'image/png'}),
    b'\xff\xd8\xff': frozenset({'image/jpeg'}),
    b'GIF87a': frozenset({'image/gif'}),
    b'GIF89a': frozenset({'image/gif'}),
    b'RIFF': frozenset({'image/webp'}),
    b'BM': frozenset({'image/bmp'}),
    None: frozenset({'image/svg+xml'}),
}


def attachment_name(att) -> str:
    if isinstance(att, dict):
        return str(att.get('name') or att.get('filename') or att.get('path') or '').strip()
    return str(att or '').strip()


def is_valid_image(path: Path, mime: str) -> bool:
    """Check that the file's first bytes match the expected image MIME type."""
    if not mime.startswith('image/'):
        return False
    mime_base = mime.split(';', 1)[0]
    if mime_base == 'image/svg+xml':
        return True
    try:
        with path.open('rb') as fh:
            head = fh.read(16)
    except OSError:
        return False
    for magic, mimes in IMAGE_MAGIC.items():
        if magic is not None and head.startswith(magic) and mime_base in mimes:
            return True
    return False


def resolve_image_input_mode(cfg: dict) -> str:
    """Return ``"native"`` or ``"text"`` based on WebUI image config."""
    agent_cfg = cfg.get("agent") or {}
    mode = str(agent_cfg.get("image_input_mode", "auto") or "auto").strip().lower()
    if mode not in ("auto", "native", "text"):
        mode = "auto"

    if mode == "native":
        return "native"
    if mode == "text":
        return "text"

    aux = cfg.get("auxiliary") or {}
    vision = aux.get("vision") or {}
    provider = str(vision.get("provider") or "").strip().lower()
    model_name = str(vision.get("model") or "").strip()
    base_url = str(vision.get("base_url") or "").strip()
    if provider not in ("", "auto") or model_name or base_url:
        return "text"

    return "native"


def build_native_multimodal_message(
    workspace_ctx: str,
    msg_text: str,
    attachments,
    workspace: str,
    *,
    cfg: dict = None,
):
    """Build native multimodal content parts for current-turn image uploads."""
    if not attachments:
        return workspace_ctx + msg_text

    if cfg is not None and resolve_image_input_mode(cfg) == "text":
        return workspace_ctx + msg_text

    parts = [{'type': 'text', 'text': workspace_ctx + msg_text}]
    workspace_root = Path(workspace).expanduser().resolve()
    try:
        from api.upload import _attachment_root
        attachment_root = _attachment_root()
        allowed_roots = (workspace_root, attachment_root)
    except Exception:
        allowed_roots = (workspace_root,)
    image_count = 0

    for att in attachments or []:
        if not isinstance(att, dict):
            continue
        raw_path = str(att.get('path') or '').strip()
        if not raw_path:
            continue
        try:
            path = Path(raw_path).expanduser().resolve()
            if not any(path.is_relative_to(root) for root in allowed_roots):
                continue
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size <= 0 or size > NATIVE_IMAGE_MAX_BYTES:
                continue
            mime = str(att.get('mime') or '').strip() or (mimetypes.guess_type(path.name)[0] or '')
            if not mime.startswith('image/') or not is_valid_image(path, mime):
                continue
            data = base64.b64encode(path.read_bytes()).decode('ascii')
        except Exception:
            continue
        parts.append({
            'type': 'image_url',
            'image_url': {'url': f'data:{mime};base64,{data}'},
        })
        image_count += 1

    return parts if image_count else workspace_ctx + msg_text
