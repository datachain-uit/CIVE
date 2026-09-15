# Giao thức LLM-only event-conditioned v7

> Trạng thái: v7.0.1 đã FAIL predictive gate và dừng trước threshold, action mapping, backtest hoặc sealed holdout. Đây là follow-up development sau khi đã xem kết quả âm v3-v6, không phải replication độc lập hoặc sealed confirmation.

## Câu hỏi nghiên cứu

V7 kiểm tra liệu cấu trúc sự kiện do LLM trích xuất từ headline có dự báo BTC return 24 giờ tốt hơn biểu diễn sentiment LLM tổng quát hay không. Đầu vào dự báo chỉ gồm output của LLM. Giá và lợi suất chỉ dùng để tạo nhãn và chấm điểm ngoài mẫu.

## Ranh giới LLM-only

- Được dùng: `btc_relevance`, `event_type`, `direction`, `severity`, `reported_surprise`, `expected_horizon` và `confidence` từ extractor v3.9 đã khóa.
- Không được dùng: OHLCV, return trễ, realized volatility, volume, funding, breadth, dispersion, regime, technical indicator, source identity, article length, recency hoặc các feature thị trường khác.
- Downstream Ridge chỉ nhận các trường bắt nguồn từ output LLM. Evaluator từ chối feature không có tiền tố `llm_` và các tên chứa thuật ngữ giá hoặc kỹ thuật.
- `h24_return` chỉ là target. Nó không xuất hiện trong feature, prompt hoặc aggregation.

## Ba arm

1. `prior`: trung bình `h24_return` của training fold, không có predictive feature.
2. `llm-sentiment`: direction fractions, signed direction, directional severity/confidence và mean/max của severity, reported surprise, confidence.
3. `llm-event-conditioned`: toàn bộ `llm-sentiment` cộng relevance fractions, event-type fractions, expected-horizon fractions và signed impact theo event type/relevance. Impact là tích cố định của direction sign, severity, reported surprise, confidence và relevance weight; không tuning trọng số.

Comparator chính là `llm-sentiment`; treatment duy nhất là `llm-event-conditioned`. `prior` chỉ là diagnostic.

## Dữ liệu và split

- Extractor v3.9: 39.393/39.393 headline thành công.
- Target: BTCUSDT `h24_return`, tính từ open 4H sau execution delay 4 giờ, kế thừa target panel v3.
- Headline trùng normalized text chỉ đóng góp ở lần xuất hiện đầu tiên.
- Năm expanding folds và purge 72 giờ kế thừa nguyên trạng từ v3.1.1; tổng cộng 699 OOS prediction.
- Ridge `alpha=10`, chuẩn hóa mean/std chỉ trên training fold, không tuning.

## Gate

Moving-block bootstrap theo fold dùng block 7 ngày, 5.000 lần, seed `20260907`. V7 chỉ PASS nếu đồng thời:

- cận dưới CI 95% của `MSE(llm-sentiment)-MSE(llm-event-conditioned)` lớn hơn 0;
- cận dưới CI 95% Pearson của prediction event-conditioned lớn hơn 0;
- event-conditioned thắng sentiment về MSE ở ít nhất 3/5 fold;
- có đúng 699 OOS prediction và prediction không hằng.

Nếu FAIL, khóa kết quả âm và dừng trước threshold, action mapping, trading backtest hoặc sealed holdout. Nếu PASS, quyền duy nhất được mở là predeclare một backtest LLM-only riêng trên development data.

## Giới hạn diễn giải

Kết quả v3 return/risk, v4 transfer, v5 full-text và v6 contrastive đã được biết trước khi thiết kế v7. Vì vậy v7 chỉ là kiểm định development có điều kiện, không được mô tả là xác nhận độc lập. PASS không tự động chứng minh lợi nhuận giao dịch hoặc khả năng chạy live.

## Protocol deviation v7.0

Lần chạy v7.0 đầu tiên dừng tại feature-name guard vì phép so khớp substring diễn giải `low` bên trong `flow` của `etf_institutional_flow` là feature bị cấm. Evaluator đã xác minh hash, đọc source JSON và tạo feature names nhưng chưa fit mô hình, tạo prediction, tính metric hoặc ghi panel/gate. Revision v7.0.1 chỉ đổi guard sang đối sánh token đầy đủ và thêm regression test cho `etf_institutional_flow`; target, feature values, folds, model, bootstrap và ngưỡng gate không đổi.

## Kết quả v7.0.1

V7.0.1 tạo đủ 699 prediction OOS và xác nhận `technical_or_market_features_used=false`. MSE của prior, generic LLM sentiment và LLM event-conditioned lần lượt là 0,0006345120, 0,0006445626 và 0,0006751356. Chênh lệch `MSE(sentiment)-MSE(event)` bằng -0,0000305730, tương ứng event-conditioned làm MSE xấu hơn 4,7432%; CI 95% [-0,0000537452; -0,0000089351] hoàn toàn âm. Pearson event prediction với `h24_return` bằng -0,02869, CI 95% [-0,10705; 0,05116], và event-conditioned thắng 0/5 fold.

Ba điều kiện hiệu quả chính đều fail. Theo stop rule, không chọn threshold, không ánh xạ action, không chạy trading backtest và không xem sealed holdout.
