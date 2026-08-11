from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from structlog.contextvars import get_contextvars

from .pii import scrub_text


AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "data/audit.jsonl"))
_AUDIT_LOCK = Lock()


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: _scrub_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub_value(item) for item in value]
    return value


def write_audit_event(
    event: str,
    *,
    correlation_id: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: str = "system",
) -> None:
    context = get_contextvars()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "service": "audit",
        "event": event,
        "correlation_id": correlation_id or context.get("correlation_id", "system"),
        "actor": actor,
        "payload": _scrub_value(payload or {}),
    }
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with _AUDIT_LOCK:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
