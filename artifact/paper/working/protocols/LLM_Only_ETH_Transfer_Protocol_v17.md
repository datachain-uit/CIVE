# LLM-only ETH transfer v17

> Trạng thái: FEASIBILITY PASS, PREDICTIVE GATE FAIL. Dừng trước threshold, action mapping và LLM-only backtest.

V17 kiểm tra khả năng chuyển biểu diễn event-risk v3.9 từ target BTC sang ETHUSDT mà không chạy lại LLM. Alias xác định event ETH được khóa là `Ethereum`, `ETH` và `Ether`. Mọi feature bắt đầu bằng `llm_` và chỉ được suy ra từ output LLM; OHLCV, funding và feature kỹ thuật chỉ dùng để tạo nhãn hoặc cho external hybrid comparator độc lập.

Audit không đọc outcome yêu cầu extractor/input khớp 39.393 record, ít nhất 1.000 event ETH, ít nhất 700 ngày ETH và ít nhất 100 ngày ETH trong từng fold OOS. Audit đạt với 5.341 event trên 1.000 ngày; năm fold có 118, 131, 134, 132 và 137 ngày event.

Target duy nhất là ETHUSDT open-to-open 24 giờ, entry sau cutoff 4 giờ. Ba arm gồm train-mean prior, generic LLM-only và event-conditioned LLM-only. Ridge dùng alpha 10, chuẩn hóa trong train fold và năm fold expanding giống v3.1.1. Gate yêu cầu cận dưới CI 95% của `MSE(generic)-MSE(event)` dương, cận dưới CI Pearson event dương, event thắng ít nhất 3/5 fold và prediction không hằng.

Kết quả có 699 prediction OOS. MSE generic là 0,00136025 và event là 0,00142177; delta MSE bằng -0,00006152 với CI 95% [-0,00012406; -0,00001267]. Pearson event là -0,03741 với CI 95% [-0,09362; 0,03454]; event thắng 0/5 fold. Vì vậy gate FAIL. Đây là development transfer trên một corpus/extractor BTC-centric, không phải replication hoặc sealed validation.
