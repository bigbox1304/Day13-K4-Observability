from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import logging_config
from app.logging_config import scrub_event
from app.main import agent, app
from app.pii import hash_user_id
from app.schemas import LogRecord


GENERATED_REQUEST_ID = re.compile(r"^req-[0-9a-f]{8}$")
REQUIRED_FIELDS = {"ts", "level", "service", "event", "correlation_id"}
API_CONTEXT_FIELDS = {"user_id_hash", "session_id", "feature", "model", "env"}


def _read_events(log_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _chat_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "user_id": "student-01",
        "session_id": "session-01",
        "feature": "monitoring",
        "message": "Explain observability",
    }
    payload.update(overrides)
    return payload


def test_generated_correlation_id_is_shared_by_response_headers_and_logs(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post("/chat", json=_chat_payload())

    correlation_id = response.json()["correlation_id"]
    assert response.status_code == 200
    assert GENERATED_REQUEST_ID.fullmatch(correlation_id)
    assert response.headers["x-request-id"] == correlation_id
    assert float(response.headers["x-response-time-ms"]) >= 0

    api_events = [event for event in _read_events(log_path) if event["service"] == "api"]
    assert {event["correlation_id"] for event in api_events} == {correlation_id}


def test_safe_incoming_request_id_is_reused(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers={"x-request-id": "client-trace-123"},
            json=_chat_payload(),
        )

    assert response.json()["correlation_id"] == "client-trace-123"
    assert response.headers["x-request-id"] == "client-trace-123"


def test_invalid_incoming_request_id_is_replaced(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            headers={"x-request-id": "student@example.com"},
            json=_chat_payload(),
        )

    assert GENERATED_REQUEST_ID.fullmatch(response.json()["correlation_id"])


def test_request_context_is_enriched_and_isolated(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        first = client.post("/chat", json=_chat_payload())
        second = client.post(
            "/chat",
            json=_chat_payload(
                user_id="student-02",
                session_id="session-02",
                feature="qa",
            ),
        )

    assert first.json()["correlation_id"] != second.json()["correlation_id"]
    events = _read_events(log_path)
    api_events = [event for event in events if event["service"] == "api"]

    first_events = [
        event
        for event in api_events
        if event["correlation_id"] == first.json()["correlation_id"]
    ]
    second_events = [
        event
        for event in api_events
        if event["correlation_id"] == second.json()["correlation_id"]
    ]
    assert {event["event"] for event in first_events} == {
        "request_received",
        "response_sent",
    }
    assert {event["event"] for event in second_events} == {
        "request_received",
        "response_sent",
    }
    assert all(API_CONTEXT_FIELDS <= event.keys() for event in api_events)
    assert all(
        event["user_id_hash"] == hash_user_id("student-01")
        for event in first_events
    )
    assert all(
        event["user_id_hash"] == hash_user_id("student-02")
        for event in second_events
    )
    assert "student-01" not in log_path.read_text(encoding="utf-8")
    assert "student-02" not in log_path.read_text(encoding="utf-8")


def test_error_log_keeps_request_context_and_scrubs_detail(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    def fail_run(**_: str) -> None:
        raise RuntimeError("Contact student@example.com or 090 123 4567")

    monkeypatch.setattr(agent, "run", fail_run)
    with TestClient(app) as client:
        response = client.post("/chat", json=_chat_payload())

    assert response.status_code == 500
    assert GENERATED_REQUEST_ID.fullmatch(response.headers["x-request-id"])
    error_event = next(
        event for event in _read_events(log_path) if event["event"] == "request_failed"
    )
    assert error_event["correlation_id"] == response.headers["x-request-id"]
    assert API_CONTEXT_FIELDS <= error_event.keys()
    rendered = json.dumps(error_event, ensure_ascii=False)
    assert "student@example.com" not in rendered
    assert "090 123 4567" not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "[REDACTED_PHONE_VN]" in rendered


def test_scrub_event_recurses_through_nested_values() -> None:
    event = {
        "event": "request_failed",
        "payload": {
            "contacts": ["student@example.com", {"phone": "+84 90 123 4567"}],
            "identity": ("001234567890", "B1234567"),
            "card": "4111-1111-1111-1111",
        },
    }

    scrubbed = scrub_event(None, "error", event)
    rendered = json.dumps(scrubbed, ensure_ascii=False)

    for raw_value in (
        "student@example.com",
        "+84 90 123 4567",
        "001234567890",
        "B1234567",
        "4111-1111-1111-1111",
    ):
        assert raw_value not in rendered
    for marker in (
        "REDACTED_EMAIL",
        "REDACTED_PHONE_VN",
        "REDACTED_CCCD",
        "REDACTED_PASSPORT_VN",
        "REDACTED_CREDIT_CARD",
    ):
        assert marker in rendered


def test_every_written_record_satisfies_required_schema_fields(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    with TestClient(app) as client:
        response = client.post("/chat", json=_chat_payload())

    assert response.status_code == 200
    events = _read_events(log_path)
    assert events
    assert all(REQUIRED_FIELDS <= event.keys() for event in events)
    for event in events:
        LogRecord.model_validate(event)
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert isinstance(response_event["latency_ms"], int)
    assert isinstance(response_event["tokens_in"], int)
    assert isinstance(response_event["tokens_out"], int)
    assert isinstance(response_event["cost_usd"], float)
    assert isinstance(response_event["quality_score"], float)
