"""Cron route helpers."""

from __future__ import annotations

import datetime
import re
import time
from urllib.parse import parse_qs


def cron_output_usage_metadata(text: str) -> dict:
    """Extract optional token/cost metadata from a cron output markdown file."""
    head = text.split("## Response", 1)[0].split("# Response", 1)[0]
    usage: dict = {}

    def _intish(value: str):
        cleaned = re.sub(r"[^0-9]", "", value or "")
        return int(cleaned) if cleaned else None

    def _floatish(value: str):
        match = re.search(r"[-+]?\d+(?:\.\d+)?", (value or "").replace(",", ""))
        return float(match.group(0)) if match else None

    for raw_line in head.splitlines():
        line = raw_line.strip()
        model_match = re.match(r"\*\*(?:Model|Model Used):\*\*\s*(.+)$", line, re.I)
        if model_match:
            usage["model"] = model_match.group(1).strip()
            continue
        provider_match = re.match(r"\*\*Provider:\*\*\s*(.+)$", line, re.I)
        if provider_match:
            usage["provider"] = provider_match.group(1).strip()
            continue
        cost_match = re.match(r"\*\*(?:Estimated cost|Cost):\*\*\s*(.+)$", line, re.I)
        if cost_match:
            cost = _floatish(cost_match.group(1))
            if cost is not None:
                usage["estimated_cost_usd"] = cost
            continue
        duration_match = re.match(r"\*\*(?:Duration|Elapsed):\*\*\s*(.+)$", line, re.I)
        if duration_match:
            seconds = _floatish(duration_match.group(1))
            if seconds is not None:
                usage["duration_seconds"] = seconds
            continue
        tokens_match = re.match(r"\*\*Tokens:\*\*\s*(.+)$", line, re.I)
        if tokens_match:
            value = tokens_match.group(1)
            input_match = re.search(r"([0-9][0-9,]*)\s*(?:input|in)\b", value, re.I)
            output_match = re.search(r"([0-9][0-9,]*)\s*(?:output|out)\b", value, re.I)
            total_match = re.search(r"([0-9][0-9,]*)\s*(?:total\s*)?tokens?\b", value, re.I)
            if input_match:
                usage["input_tokens"] = _intish(input_match.group(1))
            if output_match:
                usage["output_tokens"] = _intish(output_match.group(1))
            if total_match and "total_tokens" not in usage:
                usage["total_tokens"] = _intish(total_match.group(1))

    if "total_tokens" not in usage:
        total = sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens"))
        if total:
            usage["total_tokens"] = total
    return usage


def cron_output_snippet(text: str, limit: int = 600) -> str:
    """Extract the response body from a cron output .md file for preview."""
    lines = text.split("\n")
    response_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("## Response") or line.startswith("# Response"):
            response_idx = i
            break
    body = ("\n".join(lines[response_idx + 1 :]) if response_idx >= 0 else "\n".join(lines)).strip()
    return body[:limit] or "(empty)"


def handle_cron_output(
    handler,
    parsed,
    *,
    json_response_fn,
    content_window_fn,
    logger,
) -> bool:
    from cron.jobs import OUTPUT_DIR as cron_out

    qs = parse_qs(parsed.query)
    job_id = qs.get("job_id", [""])[0]
    limit = int(qs.get("limit", ["5"])[0])
    if not job_id:
        return json_response_fn(handler, {"error": "job_id required"}, status=400)
    out_dir = cron_out / job_id
    outputs = []
    if out_dir.exists():
        files = sorted(out_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                outputs.append({"filename": path.name, "content": content_window_fn(text)})
            except Exception:
                logger.debug("Failed to read cron output file %s", path)
    return json_response_fn(handler, {"job_id": job_id, "outputs": outputs})


def handle_cron_status(
    handler,
    parsed,
    *,
    json_response_fn,
    is_cron_running_fn,
    running_jobs: dict,
    running_jobs_lock,
) -> bool:
    """Return running status for one or all cron jobs."""
    qs = parse_qs(parsed.query)
    job_id = qs.get("job_id", [""])[0]
    if job_id:
        running, elapsed = is_cron_running_fn(job_id)
        return json_response_fn(handler, {"job_id": job_id, "running": running, "elapsed": round(elapsed, 1)})
    with running_jobs_lock:
        all_running = {jid: round(time.time() - started_at, 1) for jid, started_at in running_jobs.items()}
    return json_response_fn(handler, {"running": all_running})


def handle_cron_recent(handler, parsed, *, json_response_fn) -> bool:
    """Return cron jobs that have completed since a given timestamp."""
    qs = parse_qs(parsed.query)
    since = float(qs.get("since", ["0"])[0])
    try:
        from cron.jobs import list_jobs

        jobs = list_jobs(include_disabled=True)
        completions = []
        for job in jobs:
            last_run = job.get("last_run_at")
            if not last_run:
                continue
            if isinstance(last_run, str):
                try:
                    ts = datetime.datetime.fromisoformat(last_run.replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError):
                    continue
            else:
                ts = float(last_run)
            if ts > since:
                completions.append(
                    {
                        "job_id": job.get("id", ""),
                        "name": job.get("name", "Unknown"),
                        "status": job.get("last_status", "unknown"),
                        "completed_at": ts,
                        "toast_notifications": job.get("toast_notifications") is not False,
                    }
                )
        return json_response_fn(handler, {"completions": completions, "since": since})
    except ImportError:
        return json_response_fn(handler, {"completions": [], "since": since})
