# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: High latency
- Severity: warning
- SLI/SLO liên quan: latency P95 ≤ 3000 ms
- Điều kiện và thời gian duy trì: response latency P95 > 3000 ms trong 5 phút
- Ảnh hưởng tới người dùng: phản hồi chậm, có thể timeout
- Ba bước kiểm tra đầu tiên: xem latency panel; mở trace chậm; tìm log cùng correlation ID
- Mitigation tạm thời: giảm concurrency hoặc tắt feature đang làm chậm request
- Owner: platform-oncall

## Alert 2

- Tên: Elevated error rate
- Severity: critical
- SLI/SLO liên quan: error rate ≤ 2%
- Điều kiện và thời gian duy trì: error rate > 2% trong 5 phút
- Ảnh hưởng tới người dùng: request thất bại hoặc không nhận được câu trả lời
- Ba bước kiểm tra đầu tiên: xem error breakdown; mở trace lỗi; tìm log request_failed
- Mitigation tạm thời: rollback prompt/feature release hoặc giảm tải upstream
- Owner: platform-oncall

## Alert 3

- Tên: Quality degradation
- Severity: warning
- SLI/SLO liên quan: quality proxy mean ≥ 0.75
- Điều kiện và thời gian duy trì: quality proxy mean < 0.75 trong 10 phút
- Ảnh hưởng tới người dùng: câu trả lời kém liên quan hoặc thiếu ngữ cảnh
- Ba bước kiểm tra đầu tiên: xem quality trend; so sánh prompt version; kiểm tra retrieved docs và trace
- Mitigation tạm thời: rollback prompt production về version ổn định
- Owner: ai-platform
