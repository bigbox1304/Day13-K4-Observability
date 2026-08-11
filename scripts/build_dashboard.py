from __future__ import annotations

import argparse
import html
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "submission" / "evidence" / "dashboard.html"


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, round((percentile_value / 100) * len(values) + 0.5) - 1)
    return float(values[max(0, index)])


def read_records(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc
        if isinstance(record, dict):
            records.append(record)
    return records


def in_last_hour(records: list[dict]) -> tuple[list[dict], datetime | None, datetime | None]:
    timestamps = []
    for record in records:
        try:
            timestamps.append(datetime.fromisoformat(record["ts"].replace("Z", "+00:00")))
        except (KeyError, ValueError, TypeError):
            continue
    if not timestamps:
        return records, None, None
    end = max(timestamps)
    start = end - timedelta(minutes=60)
    selected = []
    for record in records:
        try:
            timestamp = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        if start <= timestamp <= end:
            selected.append(record)
    return selected, start, end


def build_metrics(records: list[dict]) -> dict[str, object]:
    requests = [r for r in records if r.get("event") == "request_received"]
    responses = [r for r in records if r.get("event") == "response_sent"]
    failures = [r for r in records if r.get("event") == "request_failed"]
    latencies = [float(r["latency_ms"]) for r in responses if r.get("latency_ms") is not None]
    costs = [float(r["cost_usd"]) for r in responses if r.get("cost_usd") is not None]
    input_tokens = sum(int(r.get("tokens_in", 0)) for r in responses)
    output_tokens = sum(int(r.get("tokens_out", 0)) for r in responses)
    quality = [float(r["quality_score"]) for r in responses if r.get("quality_score") is not None]
    return {
        "latency": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95), "p99": percentile(latencies, 99)},
        "traffic": {"requests": len(requests), "per_minute": len(requests) / 60},
        "errors": {"rate_pct": (len(failures) / len(requests) * 100) if requests else 0, "count": len(failures)},
        "cost": {"total_usd": sum(costs)},
        "tokens": {"input": input_tokens, "output": output_tokens},
        "quality": {"mean": statistics.mean(quality) if quality else 0},
    }


def load_thresholds() -> dict[str, dict]:
    config = yaml.safe_load((REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8"))
    return {panel["id"]: panel["threshold"] for panel in config["dashboard"]["panels"]}


def card(title: str, values: list[tuple[str, str]], threshold: str) -> str:
    rows = "".join(f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>" for label, value in values)
    return f'<section class="panel"><h2>{html.escape(title)}</h2><table>{rows}</table><p class="threshold">Threshold/SLO: {html.escape(threshold)}</p></section>'


def render(metrics: dict[str, object], thresholds: dict[str, dict], start: datetime | None, end: datetime | None, record_count: int) -> str:
    time_range = "No timestamped records"
    if start and end:
        time_range = f"{start.isoformat()} → {end.isoformat()} (60-minute window)"
    latency = metrics["latency"]
    traffic = metrics["traffic"]
    errors = metrics["errors"]
    cost = metrics["cost"]
    tokens = metrics["tokens"]
    quality = metrics["quality"]
    threshold = lambda panel: f'{thresholds[panel]["aggregation"]} {thresholds[panel]["operator"]} {thresholds[panel]["value"]}'
    panels = [
        card("Latency percentiles", [("P50", f'{latency["p50"]:.0f} ms'), ("P95", f'{latency["p95"]:.0f} ms'), ("P99", f'{latency["p99"]:.0f} ms')], threshold("latency")),
        card("Request traffic", [("Requests", str(traffic["requests"])), ("Rate", f'{traffic["per_minute"]:.2f} requests/min')], threshold("traffic")),
        card("Error rate and breakdown", [("Error rate", f'{errors["rate_pct"]:.2f}%'), ("Failed requests", str(errors["count"]))], threshold("errors")),
        card("Cost over time", [("Total", f'${cost["total_usd"]:.6f}')], threshold("cost")),
        card("Input and output tokens", [("Input", f'{tokens["input"]:,}'), ("Output", f'{tokens["output"]:,}')], threshold("tokens")),
        card("Quality proxy", [("Mean score", f'{quality["mean"]:.3f}')], threshold("quality")),
    ]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Day 13 AI Observability Dashboard</title>
<style>body{{font-family:system-ui,sans-serif;background:#f5f7fb;color:#172033;margin:2rem}}h1{{margin-bottom:.25rem}}.meta{{color:#536174;margin-bottom:1.5rem}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:1rem}}.panel{{background:white;border:1px solid #d9e0ea;border-radius:10px;padding:1rem;box-shadow:0 2px 8px #17203312}}h2{{font-size:1rem;margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:.4rem 0;border-bottom:1px solid #edf0f5}}td{{text-align:right;font-variant-numeric:tabular-nums}}.threshold{{font-size:.8rem;color:#536174;margin-bottom:0}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}}}</style></head>
<body><h1>Day 13 AI Observability</h1><div class="meta">Source: data/logs.jsonl · Records: {record_count} · Time range: {html.escape(time_range)} · Refresh contract: 30 seconds</div>
<div class="grid">{"".join(panels)}</div></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the six-panel dashboard from real JSONL logs")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = read_records(args.log)
    selected, start, end = in_last_hour(records)
    metrics = build_metrics(selected)
    html_text = render(metrics, load_thresholds(), start, end, len(selected))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "records": len(selected), "metrics": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
