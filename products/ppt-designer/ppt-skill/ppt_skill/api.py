from __future__ import annotations
"""fal.ai GPT Image 2 wrappers: gen (text-to-image) and edit (image-to-image).

Both calls go through `_with_retries`, which handles transient network errors
and provider rate-limiting with exponential backoff (longer for rate-limit).
"""

import os
import random
import sys
import time
import urllib.request
from pathlib import Path

FAL_GEN_ENDPOINT = "openai/gpt-image-2"
FAL_EDIT_ENDPOINT = "openai/gpt-image-2/edit"

MAX_RETRIES = 3                 # 4 attempts total
BASE_DELAY_SEC = 2              # exponential base for normal errors
RATE_LIMIT_DELAY_SEC = 30       # longer base for rate-limit
JITTER_FRAC = 0.3               # ±30% jitter so parallel callers don't sync


def _fal():
    if not os.environ.get("FAL_KEY"):
        print("Error: FAL_KEY not set. Put it in .env next to ppt.py.", file=sys.stderr)
        sys.exit(1)
    try:
        import fal_client
    except ImportError:
        print("Error: fal-client not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)
    return fal_client


def _parse_size(size_str: str | None) -> dict | str | None:
    """Accept presets like 'landscape_4_3', explicit 'WxH', or None."""
    if not size_str:
        return None
    if "x" in size_str.lower():
        w, h = size_str.lower().split("x")
        return {"width": int(w), "height": int(h)}
    return size_str


def _on_update(update) -> None:
    fal_client = _fal()
    if isinstance(update, fal_client.InProgress):
        for log in update.logs or []:
            print(f"  [fal] {log['message']}")


def _download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, out_path)


def _first_image_url(result: dict) -> str:
    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"No images in result: {result}")
    return images[0]["url"]


def _is_rate_limit(exc: BaseException) -> bool:
    """Best-effort rate-limit detection across requests / fal_client error shapes."""
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return status == 429


def _retry_delay(attempt: int, *, rate_limited: bool) -> float:
    """Exponential backoff with jitter. attempt is 0-indexed."""
    base = RATE_LIMIT_DELAY_SEC if rate_limited else BASE_DELAY_SEC
    delay = base * (2 ** attempt)
    jitter = delay * JITTER_FRAC * (2 * random.random() - 1)
    return max(1.0, delay + jitter)


def _with_retries(label: str, fn, *, max_retries: int = MAX_RETRIES):
    """Run `fn()` with retries. `label` shows up in log lines."""
    last_exc: BaseException | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except BaseException as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            limited = _is_rate_limit(exc)
            delay = _retry_delay(attempt, rate_limited=limited)
            tag = "rate-limited" if limited else "transient error"
            print(
                f"  [{label}] {tag}: {type(exc).__name__}: {exc} — "
                f"retry {attempt + 1}/{max_retries} in {delay:.1f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(
        f"{label} failed after {max_retries + 1} attempts. Last error: {last_exc}"
    ) from last_exc


def gen_image(
    *,
    prompt: str,
    out_path: Path,
    size: str | None = None,
    quality: str = "high",
) -> str:
    """Text-to-image via openai/gpt-image-2. Returns the remote URL it was downloaded from."""
    fal_client = _fal()

    arguments: dict = {
        "prompt": prompt,
        "quality": quality,
        "output_format": "png",
        "num_images": 1,
    }
    parsed = _parse_size(size)
    if parsed is not None:
        arguments["image_size"] = parsed

    print(f"[gen] size={size or 'default'} quality={quality}")

    def _call():
        return fal_client.subscribe(
            FAL_GEN_ENDPOINT, arguments=arguments, with_logs=True, on_queue_update=_on_update,
        )

    result = _with_retries("gen", _call)
    url = _first_image_url(result)
    _download(url, out_path)
    print(f"[gen] saved -> {out_path}")
    return url


def edit_image(
    *,
    prompt: str,
    refs: list[str],
    out_path: Path,
    size: str | None = None,
    quality: str = "high",
    mask: str | None = None,
) -> str:
    """Image-to-image edit via openai/gpt-image-2/edit. `refs` are local paths or URLs."""
    fal_client = _fal()

    image_urls: list[str] = []
    for ref in refs:
        if ref.startswith(("http://", "https://")):
            image_urls.append(ref)
        else:
            p = Path(ref)
            if not p.exists():
                raise FileNotFoundError(f"Reference not found: {ref}")
            print(f"[edit] uploading {p.name}...")
            image_urls.append(_with_retries("upload", lambda p=p: fal_client.upload_file(str(p))))

    arguments: dict = {
        "prompt": prompt,
        "image_urls": image_urls,
        "quality": quality,
        "output_format": "png",
        "num_images": 1,
    }
    parsed = _parse_size(size)
    if parsed is not None:
        arguments["image_size"] = parsed
    if mask:
        if mask.startswith(("http://", "https://")):
            arguments["mask_url"] = mask
        else:
            arguments["mask_url"] = _with_retries(
                "upload-mask", lambda: fal_client.upload_file(mask),
            )

    print(f"[edit] refs={len(image_urls)} quality={quality}")

    def _call():
        return fal_client.subscribe(
            FAL_EDIT_ENDPOINT, arguments=arguments, with_logs=True, on_queue_update=_on_update,
        )

    result = _with_retries("edit", _call)
    url = _first_image_url(result)
    _download(url, out_path)
    print(f"[edit] saved -> {out_path}")
    return url
