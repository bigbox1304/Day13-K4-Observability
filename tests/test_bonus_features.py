from __future__ import annotations

import json
import random
from pathlib import Path

from app import audit, mock_llm, runtime_config
from app.incidents import STATE
from scripts.detect_anomalies import detect_anomalies


def test_cost_optimization_caps_cost_spike_output_tokens() -> None:
    previous_incident = STATE["cost_spike"]
    previous_config = runtime_config.snapshot()
    try:
        STATE["cost_spike"] = True
        runtime_config.set_cost_optimization(enabled=False, max_output_tokens=180)
        random.seed(7)
        before = mock_llm.FakeLLM().generate("prompt").usage.output_tokens

        runtime_config.set_cost_optimization(enabled=True, max_output_tokens=180)
        random.seed(7)
        after = mock_llm.FakeLLM().generate("prompt").usage.output_tokens

        assert before > 180
        assert after == 180
    finally:
        STATE["cost_spike"] = previous_incident
        runtime_config.set_cost_optimization(
            enabled=previous_config["cost_optimization_enabled"],
            max_output_tokens=previous_config["max_output_tokens"],
        )


def test_audit_log_is_separate_and_scrubs_pii(monkeypatch, tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "AUDIT_LOG_PATH", audit_path)

    audit.write_audit_event(
        "config_changed",
        correlation_id="req-audit-01",
        payload={"email": "student@example.com", "setting": "cost_optimization"},
    )

    record = json.loads(audit_path.read_text(encoding="utf-8"))
    assert record["service"] == "audit"
    assert record["event"] == "config_changed"
    assert record["correlation_id"] == "req-audit-01"
    rendered = audit_path.read_text(encoding="utf-8")
    assert "student@example.com" not in rendered
    assert "[REDACTED_EMAIL]" in rendered


def test_anomaly_automation_detects_latency_and_pii() -> None:
    records = [
        {
            "event": "request_received",
            "feature": "monitoring",
            "correlation_id": "req-anomaly-01",
            "payload": {"message_preview": "Contact student@example.com"},
        },
        {
            "event": "response_sent",
            "feature": "monitoring",
            "latency_ms": 4000,
            "quality_score": 0.9,
            "correlation_id": "req-anomaly-01",
        },
    ]

    report = detect_anomalies(
        records,
        {"latency_p95_ms": 3000, "error_rate_pct": 2, "quality_score_avg": 0.75},
    )

    anomaly_types = {anomaly["type"] for anomaly in report["anomalies"]}
    assert "latency_p95" in anomaly_types
    assert "pii_leak" in anomaly_types
