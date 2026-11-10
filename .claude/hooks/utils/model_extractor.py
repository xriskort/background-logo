#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///

"""
Find which model a Claude Code session is running, for the observability dashboard.

send_event.py imports get_model_from_transcript() from here. The upstream
repository (disler/claude-code-hooks-multi-agent-observability) references this
module but does not ship it, so this is a small stand-in: it reads the end of
the session transcript (JSONL) for the latest assistant message's "model", and
remembers the last answer per session in the system temp folder so a short
transcript tail still finds it.
"""

import json
import os
import tempfile

TAIL_BYTES = 512 * 1024


def _cache_path(session_id):
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:64] or "unknown"
    return os.path.join(tempfile.gettempdir(), "cc-observability-model-%s.txt" % safe)


def _read_cache(session_id):
    try:
        with open(_cache_path(session_id), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def get_model_from_transcript(session_id, transcript_path):
    """The model name of the session's latest assistant turn, or "" if unknown."""
    model = ""
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as fh:
            if size > TAIL_BYTES:
                fh.seek(size - TAIL_BYTES)
            lines = fh.read().decode("utf-8", "replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("model"):
                model = str(msg["model"])
                break
    except OSError:
        return _read_cache(session_id)
    if not model:
        return _read_cache(session_id)
    try:
        with open(_cache_path(session_id), "w", encoding="utf-8") as fh:
            fh.write(model)
    except OSError:
        pass
    return model
