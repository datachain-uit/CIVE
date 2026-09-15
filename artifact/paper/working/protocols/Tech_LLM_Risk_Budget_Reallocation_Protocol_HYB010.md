# HYB-010 — tái phân bổ risk budget bằng CryptoBERT

## Câu hỏi nghiên cứu

HYB-010 kiểm tra liệu tín hiệu CryptoBERT đã làm giảm tail loss trong HYB-009 có thể được dùng để phân bổ lại exposure giữa các cơ hội Tech, qua đó phục hồi hoặc tăng lợi nhuận mà vẫn giữ được lợi ích rủi ro hay không. Incremental value được đọc đúng theo đề cương: mọi thay đổi Tech+LLM so với Tech-only về lợi nhuận, rủi ro, chi phí, hiệu quả điều chỉnh theo rủi ro, độ ổn định và bất định thống kê đều phải được báo cáo; không yêu cầu LLM phải thắng lợi nhuận tổng thể mới được ghi nhận giá trị trên một chiều khác.

Đây là thí nghiệm development hậu outcome. CryptoBERT được chọn vì audit mô tả HYB-009 cho thấy nó tốt hơn shuffled và constant-0,75 trên closed-trade MDD, ES10 và worst trade. Vì vậy HYB-010 không phải validation độc lập, sealed holdout hoặc bằng chứng live.

## Chính sách khóa trước lần chạy mới

HYB-009 dùng `d = 1 - 0,5q`, với `q` là causal bearish percentile. HYB-010 dùng:

`w = 1,25 - 0,5q = d + 0,25`, giới hạn tự nhiên trong `[0,75; 1,25]`.

Quy tắc này:

- giữ nguyên entry, direction, exit, stop, fee, slippage và funding của frozen Tech-Control;
- hạ exposure tương đối khi bearish percentile cao;
- cho phép tăng exposure tối đa 1,25× khi bearish percentile thấp;
- không tạo giao dịch mới, không đảo chiều và không thay đổi thời điểm giao dịch;
- scale gross PnL và chi phí tuyến tính theo exposure như HYB-009.

## Đối chứng

- `Tech-Control`: exposure không đổi 1×.
- `shuffled reallocation`: cùng tập weight của primary nhưng hoán vị timestamp một lần bằng seed khóa.
- `constant matched budget`: exposure không đổi bằng mean weight của primary. Đối chứng này tách lợi ích chọn vị trí phân bổ khỏi lợi ích cơ học do exposure trung bình cao hơn 1×.

## Tiêu chí đánh giá

Mọi chênh lệch return, closed-trade MDD, ES10, worst trade, cost, ba chronological fold và CI 95% theo quarter-cluster bootstrap đều được báo cáo như các chiều incremental value.

Claim mạnh “chuyển phần rủi ro tiết kiệm thành lợi nhuận” chỉ được chấp nhận nếu đồng thời:

1. Primary thắng shuffled và constant-matched-budget về mean net delta và closed-trade MDD.
2. Compounded return cao hơn Tech, CI 95% của paired net delta có cận dưới dương và ít nhất 2/3 fold dương.
3. Closed-trade MDD không cao hơn Tech, ES10 không xấu hơn Tech và worst trade không xấu hơn Tech.

Nếu claim mạnh fail, các thay đổi riêng lẻ vẫn được ghi nhận theo định nghĩa incremental value của đề cương, cùng trade-off và độ bất định; không được đổi tên khái niệm hoặc che kết quả âm.

## Giới hạn

- Chỉ có 24 historical Tech opportunity.
- Chọn CryptoBERT dựa trên kết quả mô tả HYB-009, nên có selection bias cấp thí nghiệm.
- Closed-trade MDD không phải intrabar MDD.
- Không retune offset `0,25`, bounds hoặc comparator sau khi mở kết quả.

## Artifact dự kiến

- `paper/input/results/hybrid/hyb010_risk_budget_reallocation_predeclared.json`
- `paper/input/results/hybrid/hyb010_risk_budget_reallocation_evaluation.json`
- `tools/llm/predeclare_hyb010_risk_budget_reallocation.py`
- `tools/llm/evaluate_hyb010_risk_budget_reallocation.py`
- `tools/llm/test_hyb010_risk_budget_reallocation.py`
