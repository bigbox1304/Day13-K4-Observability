# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: 100/100 trên 62 log records
- Tổng số traces: 14 production traces queried from Langfuse, including 4 CP2 prompt-version traces
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard: `submission/evidence/dashboard.html`

## 3. Logging và tracing

- Evidence correlation ID: `submission/evidence/cp1-final-validator.txt`, `submission/evidence/cp1-test-results.txt`
- Evidence PII redaction: `submission/evidence/cp1-final-validator.txt`, `submission/evidence/cp1-test-results.txt`
- Evidence trace waterfall: `submission/evidence/cp2-trace-summary.txt` (trace IDs and prompt metadata)
- Giải thích một span đáng chú ý:

## 4. Prompt versioning

- Prompt name: `day13-chat`
- Version/label baseline: version 1 / `baseline` (restored to `production`)
- Version/label candidate: version 2 / `candidate`
- Trace ID của mỗi version: `9f18b27111b2ed7c4e5ba5d741950674` (baseline v1), `7a07cd53d084e6164c284da053efb088` (candidate v2), `b2b7149ce9fa6fbb6465bdc4a0f55755` (production v2), `f6015a0df36c9cb58b64a2d0bceff17a` (production v1 after rollback)
- Bằng chứng đổi label hoặc rollback: `submission/evidence/cp2-trace-summary.txt`

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel có trong dashboard contract.`
- Evidence dashboard: `submission/evidence/dashboard.html`, `submission/evidence/cp2-dashboard-validator.txt`
- SLO đã chọn và lý do: latency P95 ≤ 3000 ms, error rate ≤ 2%, quality proxy mean ≥ 0.75; theo `config/dashboard.yaml` và `config/slo.yaml`.
- Alert rules và runbook: `config/alert_rules.yaml`, `docs/alerts.md`

## 6. Điều tra challenge

- Challenge ID:
- Triệu chứng từ metrics:
- Trace ID liên quan:
- Log line/correlation ID liên quan:
- Root cause:
- Fix action:
- Preventive measure:

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| | | | |
