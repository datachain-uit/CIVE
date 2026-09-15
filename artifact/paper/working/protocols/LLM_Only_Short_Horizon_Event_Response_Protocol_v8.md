# Giao thức LLM-only short-horizon event response v8

> Trạng thái: v8 đã FAIL predictive gate và dừng trước threshold, action mapping, backtest hoặc sealed holdout. Kết quả v3-v7 đã được biết; target 4 giờ và eligibility rule được khóa trước khi dựng panel hoặc xem prediction v8.

## Câu hỏi nghiên cứu

V8 kiểm tra liệu cấu trúc sự kiện do LLM trích xuất có dự báo được BTC return trong 4 giờ ngay sau thời điểm bài báo được xuất bản hay không. Đây là câu hỏi phản ứng sự kiện ngắn hạn, khác với dự báo return BTC tổng quát 24 giờ của v7.

## Ranh giới LLM-only

- Predictive inputs chỉ gồm output extractor v3.9: `btc_relevance`, `event_type`, `direction`, `severity`, `reported_surprise` và `confidence`.
- Không dùng OHLCV, lagged return, volatility, volume, funding, breadth, regime, technical indicator, source identity, article count, recency hoặc deterministic text metadata làm feature.
- Bybit BTCUSDT 4H chỉ được dùng để tạo target và chấm điểm OOS.
- Evaluator bắt buộc xác nhận mọi feature có tiền tố `llm_` và từ chối tên feature giá/kỹ thuật.

## Event eligibility và target

- Chỉ giữ event có `btc_relevance` là `direct` hoặc `systemic`.
- Chỉ giữ tám nhóm sự kiện có catalyst xác định trước: `macro_liquidity`, `regulation`, `etf_institutional_flow`, `exchange_security`, `liquidation_leverage`, `network_protocol`, `fraud_legal`, `adoption_business`.
- Loại `market_commentary` và `other` trước khi nối outcome nhằm giảm tin chỉ mô tả biến động giá đã xảy ra.
- Headline trùng normalized text chỉ được giữ lần xuất bản đầu tiên.
- Mỗi event được gán vào open UTC 4 giờ kế tiếp nghiêm ngặt sau `published_at`. Các event cùng open được gom thành một bucket để không xem nhiều bài cùng thời điểm là quan sát thị trường độc lập.
- Target chính duy nhất là `open[t+4h] / open[t] - 1`.

## Ba arm

1. `prior`: trung bình target của training fold.
2. `llm-sentiment`: direction fractions, signed direction, directional severity/confidence và mean/max severity, reported surprise, confidence.
3. `llm-event-conditioned`: toàn bộ sentiment cộng relevance fractions, event-type fractions và signed impact theo event type. Signed impact dùng trọng số relevance cố định: direct 1,0 và systemic 0,75.

Comparator chính là `llm-sentiment`; treatment duy nhất là `llm-event-conditioned`. Prior chỉ là diagnostic.

## Split và mô hình

- Năm expanding folds theo thời gian, bao phủ năm validation 2024 và tám tháng đầu 2025.
- Purge tối thiểu một bucket 4 giờ tại mỗi biên.
- Ridge `alpha=10`, chuẩn hóa mean/std chỉ trên training fold, không tuning.
- Paired moving-block bootstrap theo fold: 5.000 lần, block 42 record, seed `20260908`.

## Gate

V8 chỉ PASS nếu đồng thời:

- cận dưới CI 95% của `MSE(llm-sentiment)-MSE(llm-event-conditioned)` lớn hơn 0;
- cận dưới CI 95% Pearson event prediction với target lớn hơn 0;
- event-conditioned thắng sentiment ít nhất 3/5 fold;
- đủ số OOS record đã khóa sau data audit và prediction không hằng.

Nếu FAIL, khóa kết quả và dừng trước threshold, action mapping, trading backtest hoặc sealed holdout. Nếu PASS, chỉ được mở một predeclaration backtest LLM-only development riêng.

## Giới hạn diễn giải

Publication timestamp được xem là thời điểm thông tin công khai theo cùng giả định point-in-time đã dùng ở panel full-text v5. V8 vẫn là follow-up development sau nhiều kết quả đã xem; PASS không phải xác nhận độc lập và không tự động chứng minh khả năng chạy live.

## Kết quả v8

Data gate giữ 11.970 event đủ điều kiện, gồm 4.993 direct và 6.977 systemic, tạo 4.605 bucket 4 giờ không thiếu target. Năm expanding fold tạo 2.633 prediction OOS. Mọi predictive feature đều có tiền tố `llm_`; evaluator xác nhận `technical_or_market_features_used=false`.

MSE của prior, generic LLM sentiment và LLM event-conditioned lần lượt là 0,0001279915, 0,0001278994 và 0,0001286188. Chênh lệch `MSE(sentiment)-MSE(event)` bằng -0,0000007194, tương ứng event-conditioned làm MSE xấu hơn 0,5625%; CI 95% [-0,0000013551; 0,0000000886] không chứng minh cải thiện. Pearson event prediction với return 4 giờ bằng 0,04437, CI 95% [0,00436; 0,09642], nhưng event-conditioned chỉ thắng sentiment 1/5 fold.

Gate FAIL vì điều kiện incremental MSE và fold consistency không đạt. Tương quan dương ngắn hạn được giữ như diagnostic development, không được diễn giải thành predictive improvement hoặc trading profitability. Theo stop rule, không chọn threshold, không ánh xạ action, không chạy backtest và không xem sealed holdout.
