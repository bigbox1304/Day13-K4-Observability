from __future__ import annotations

import os
from dataclasses import dataclass, replace
from threading import Lock
from typing import Any


DEFAULT_MAX_OUTPUT_TOKENS = 180


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class RuntimeConfig:
    cost_optimization_enabled: bool
    max_output_tokens: int


_CONFIG = RuntimeConfig(
    cost_optimization_enabled=_env_bool("COST_OPTIMIZATION_ENABLED", False),
    max_output_tokens=_env_int("LLM_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS),
)
_LOCK = Lock()


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            "cost_optimization_enabled": _CONFIG.cost_optimization_enabled,
            "max_output_tokens": _CONFIG.max_output_tokens,
        }


def set_cost_optimization(
    *, enabled: bool, max_output_tokens: int | None = None
) -> dict[str, Any]:
    global _CONFIG
    with _LOCK:
        cap = (
            _CONFIG.max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )
        if cap <= 0:
            raise ValueError("max_output_tokens phải là số nguyên dương")
        _CONFIG = replace(
            _CONFIG,
            cost_optimization_enabled=enabled,
            max_output_tokens=cap,
        )
    return snapshot()
