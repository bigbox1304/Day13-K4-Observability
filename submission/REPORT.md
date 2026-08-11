# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: Cerberus
- Repository URL: [https://github.com/bigbox1304/K4-DAY13-2A202601990.git](https://github.com/bigbox1304/K4-DAY13-2A202601990.git)
- Commit SHA cuối: Hoàn thành lab Day 13 - 2A202601990
- Thành viên và vai trò:
  - Đỗ Phan Huy Hoàng — MSSV `2A202601990` — Role 1
  - Nguyễn Tuấn Vũ — MSSV `2A202601666` — Role 2
  - Lương Sỹ Linh — MSSV `2A202601214` — Role 3

## 2. Kết quả kỹ thuật

- Kết quả validator cuối: `100/100` trên 144 log records; 0 record thiếu field bắt buộc, 0 record thiếu enrichment và 0 nguy cơ PII. Xem [cp1-final-validator.txt](evidence/cp1-final-validator.txt).
- Tổng số traces: 14 production traces queried from Langfuse, gồm 4 CP2 prompt-version traces; xem [cp2-trace-summary.txt](evidence/cp2-trace-summary.txt), [cp2-test-results.txt](evidence/cp2-test-results.txt) và [cp3-challenge-summary.txt](evidence/cp3-challenge-summary.txt).
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard: [dashboard.html](evidence/dashboard.html) và [dashboard.png](evidence/dashboard.png)

## 3. Logging và tracing

- Evidence correlation ID: [cp1-final-validator.txt](evidence/cp1-final-validator.txt), [cp1-test-results.txt](evidence/cp1-test-results.txt)
- Evidence PII redaction: [cp1-final-validator.txt](evidence/cp1-final-validator.txt), [cp1-test-results.txt](evidence/cp1-test-results.txt)
- Evidence trace waterfall: [cp2-trace-summary.txt](evidence/cp2-trace-summary.txt); ảnh [baseline](evidence/cp2tracebaseline.png), [candidate](evidence/cp2tracecandicate.png), [production v1 sau rollback](evidence/cp2traceprov1.png) và [production v2](evidence/cp2traceprov2.png).
- Giải thích một span đáng chú ý: span `run` dạng `GENERATION` trong CP3 tăng lên khoảng `2.65–3.69 s` vì retrieval path bị inject `rag_slow` sleep `2.5 giây`; log `response_sent` có cùng correlation ID và latency cao, chứng minh root cause nằm ở RAG/retrieval path.

## 4. Prompt versioning

- Prompt name: `day13-chat`
- Version/label baseline: version 1 / `baseline` (restored to `production`)
- Version/label candidate: version 2 / `candidate`
- Trace ID của mỗi version: `9f18b27111b2ed7c4e5ba5d741950674` (baseline v1), `7a07cd53d084e6164c284da053efb088` (candidate v2), `b2b7149ce9fa6fbb6465bdc4a0f55755` (production v2), `f6015a0df36c9cb58b64a2d0bceff17a` (production v1 after rollback)
- Bằng chứng đổi label hoặc rollback: [cp2-trace-summary.txt](evidence/cp2-trace-summary.txt), [promptversions.png](evidence/promptversions.png)

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: `HỢP LỆ: 6/6 panel có trong dashboard contract.`
- Evidence dashboard: [dashboard.html](evidence/dashboard.html), [dashboard.png](evidence/dashboard.png), [cp2-dashboard-validator.txt](evidence/cp2-dashboard-validator.txt), [validator.png](evidence/validator.png)
- SLO đã chọn và lý do: latency P95 ≤ 3000 ms, error rate ≤ 2%, quality proxy mean ≥ 0.75; theo `config/dashboard.yaml` và `config/slo.yaml`.
- Alert rules và runbook: `config/alert_rules.yaml`, `docs/alerts.md`

## 6. Điều tra challenge

- Challenge ID: `day13-k4-observability-v1` (K4), incident `rag_slow`, affected feature `monitoring`.
- Triệu chứng từ metrics: trong lúc incident bật, 5 request chính thức đều thành công nhưng latency P95 = `3682 ms`, P99 = `3682 ms`, vượt threshold chính thức `2000 ms`; error rate = `0%`, quality average = `0.84`.
- Trace ID liên quan: `e6becc0ae89faaf2702e826864d7726a` (session `k4-challenge-s01`, latency `3.685 s`) và bốn trace còn lại trong [cp3-challenge-summary.txt](evidence/cp3-challenge-summary.txt).
- Log line/correlation ID liên quan: `data/logs.jsonl:6`, correlation ID `req-595fdc46`, event `response_sent`, latency `3682 ms`; toàn bộ 5 correlation ID và log line được liệt kê trong [cp3-challenge-summary.txt](evidence/cp3-challenge-summary.txt).
- Root cause: nhánh RAG bị inject `rag_slow` sleep `2.5 giây` trong `app/mock_rag.py`; phép đo latency của `app/agent.py` bao gồm thời gian retrieval nên span `run` và `response_sent` đều tăng cao.
- Fix action: tắt incident và khôi phục retrieval bình thường; production nên bỏ blocking delay, thêm timeout retrieval và fallback/circuit breaker.
- Preventive measure: tạo span riêng cho retrieval, log duration/tool name, đặt alert latency P95 và thêm regression/load test cho retrieval và end-to-end latency.
- Evidence đầy đủ: [cp3-challenge-summary.txt](evidence/cp3-challenge-summary.txt).

## 7. Bonus

- Cost Optimization: cùng workload 10 query với `cost_spike`, `total_cost_usd` giảm từ `0.0786` xuống `0.0280`, tương đương `64.4%`; output tokens giảm từ `5,176` xuống `1,800`, quality proxy giữ ở `0.88`. Evidence: [cost-optimization-before-after.txt](evidence/cost-optimization-before-after.txt), [before](evidence/cost-optimization-before.png), [after](evidence/cost-optimization-after.png).
- Audit Log: `data/audit.jsonl` tách riêng, hiện có 12 event gồm `incident_enabled`, `incident_disabled` và `config_changed`, có PII scrubbing. Evidence: [audit-log-summary.txt](evidence/audit-log-summary.txt), [audit-sample.jsonl](evidence/audit-sample.jsonl).
- Custom Automation: `scripts/detect_anomalies.py` phân tích 144 records và phát hiện latency P95 của `monitoring` là `3682 ms`, vượt ngưỡng `3000 ms`; không phát hiện raw PII, error anomaly hoặc quality anomaly. Evidence: [anomaly-detection-summary.txt](evidence/anomaly-detection-summary.txt), [anomaly-report.json](evidence/anomaly-report.json).

## 8. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên        | Phần việc | Commit/PR  | Điều đã học |
| ----------------- | --------- | ---------- | ----------- |
| Đỗ Phan Huy Hoàng | Role 1    | .          |             |
| Nguyễn Tuấn Vũ    | Role 2    | tuanvu-cp2 |             |
| Lương Sỹ Linh     | Role 3    | sylinh-cp3 |             |
