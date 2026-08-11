from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_SLO = REPO_ROOT / "config" / "slo.yaml"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.pii import PII_PATTERNS


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    index = min(
        len(items) - 1,
        max(0, round((percentile_value / 100) * len(items) + 0.5) - 1),
    )
    return float(items[index])


def read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            record["_line_number"] = line_number
            records.append(record)
    return records


def select_window(records: list[dict[str, Any]], window_minutes: int) -> list[dict[str, Any]]:
    if window_minutes <= 0:
        return records
    timestamps: list[datetime] = []
    for record in records:
        try:
            timestamps.append(datetime.fromisoformat(str(record["ts"]).replace("Z", "+00:00")))
        except (KeyError, TypeError, ValueError):
            continue
    if not timestamps:
        return records
    end = max(timestamps)
    start = end - timedelta(minutes=window_minutes)
    selected: list[dict[str, Any]] = []
    for record in records:
        try:
            timestamp = datetime.fromisoformat(str(record["ts"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if start <= timestamp <= end:
            selected.append(record)
    return selected


def load_thresholds(path: Path) -> dict[str, float]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    slis = payload.get("slis", {}) if isinstance(payload, dict) else {}
    return {
        "latency_p95_ms": float(slis.get("latency_p95_ms", {}).get("objective", 3000)),
        "error_rate_pct": float(slis.get("error_rate_pct", {}).get("objective", 2)),
        "quality_score_avg": float(slis.get("quality_score_avg", {}).get("objective", 0.75)),
    }


def detect_anomalies(
    records: list[dict[str, Any]], thresholds: dict[str, float]
) -> dict[str, Any]:
    requests = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failures = [record for record in records if record.get("event") == "request_failed"]
    anomalies: list[dict[str, Any]] = []

    response_by_feature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    request_by_feature: dict[str, int] = defaultdict(int)
    failure_by_feature: dict[str, int] = defaultdict(int)
    for record in responses:
        response_by_feature[str(record.get("feature") or "unknown")].append(record)
    for record in requests:
        request_by_feature[str(record.get("feature") or "unknown")] += 1
    for record in failures:
        failure_by_feature[str(record.get("feature") or "unknown")] += 1

    features = sorted(
        set(response_by_feature) | set(request_by_feature) | set(failure_by_feature)
    )
    for feature in features:
        feature_responses = response_by_feature.get(feature, [])
        latencies = [float(record["latency_ms"]) for record in feature_responses if record.get("latency_ms") is not None]
        if latencies:
            p95 = percentile(latencies, 95)
            if p95 > thresholds["latency_p95_ms"]:
                evidence = max(feature_responses, key=lambda record: float(record.get("latency_ms", 0)))
                anomalies.append(
                    {
                        "type": "latency_p95",
                        "severity": "warning",
                        "feature": feature,
                        "observed": p95,
                        "threshold": thresholds["latency_p95_ms"],
                        "evidence_line": evidence.get("_line_number"),
                        "correlation_id": evidence.get("correlation_id"),
                    }
                )

        quality_values = [
            float(record["quality_score"])
            for record in feature_responses
            if record.get("quality_score") is not None
        ]
        if quality_values:
            quality_mean = statistics.mean(quality_values)
            if quality_mean < thresholds["quality_score_avg"]:
                anomalies.append(
                    {
                        "type": "quality_mean",
                        "severity": "warning",
                        "feature": feature,
                        "observed": round(quality_mean, 4),
                        "threshold": thresholds["quality_score_avg"],
                    }
                )

        request_count = request_by_feature.get(feature, len(feature_responses))
        error_rate = failure_by_feature.get(feature, 0) / request_count * 100 if request_count else 0.0
        if error_rate > thresholds["error_rate_pct"]:
            anomalies.append(
                {
                    "type": "error_rate",
                    "severity": "critical",
                    "feature": feature,
                    "observed": round(error_rate, 4),
                    "threshold": thresholds["error_rate_pct"],
                }
            )

    for record in records:
        rendered = json.dumps(record, ensure_ascii=False)
        leaked_types = sorted(
            name for name, pattern in PII_PATTERNS.items() if re.search(pattern, rendered)
        )
        if leaked_types:
            anomalies.append(
                {
                    "type": "pii_leak",
                    "severity": "critical",
                    "line": record.get("_line_number"),
                    "event": record.get("event"),
                    "pii_types": leaked_types,
                }
            )

    for anomaly in anomalies:
        anomaly.pop("_line_number", None)
    return {
        "records_analyzed": len(records),
        "request_count": len(requests),
        "response_count": len(responses),
        "failure_count": len(failures),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tự động phát hiện anomaly từ structured logs")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--slo", type=Path, default=DEFAULT_SLO)
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not args.log.exists():
        print(f"Không tìm thấy log: {args.log}")
        return 2

    records = select_window(read_records(args.log), args.window_minutes)
    report = detect_anomalies(records, load_thresholds(args.slo))
    report["source"] = str(args.log)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print("--- Anomaly detection ---")
    print(f"Records analyzed: {report['records_analyzed']}")
    print(f"Requests: {report['request_count']} | Responses: {report['response_count']} | Failures: {report['failure_count']}")
    print(f"Anomalies found: {report['anomaly_count']}")
    for anomaly in report["anomalies"]:
        print(json.dumps(anomaly, ensure_ascii=False, sort_keys=True))
    return 1 if report["anomaly_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
