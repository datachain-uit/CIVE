# Giao thức predictive LLM-only trên CFTC RSS archive v15

> Trạng thái: DATA GATE FAIL; STOPPED BEFORE TARGET JOIN. Protocol này độc lập với v3--v14 và không dùng kết quả, target panel, prediction, threshold hay backtest của các candidate trước.

## Câu hỏi và information set

Câu hỏi duy nhất là: event-vector do LLM tạo từ thông cáo CFTC đã có trong snapshot Internet Archive có dự báo BTCUSDT spot return 24 giờ tốt hơn representation sentiment LLM tổng quát hay không?

Đơn vị quan sát là một `archive_capture_at`. Các item có cùng thời điểm này được aggregate thành một information set. `archive_capture_at` là information time duy nhất; `publisher_pubdate` chỉ là provenance và không dùng để đặt lệnh, chia fold hay tạo target.

Corpus bắt buộc là `cftc-rss-internet-archive-v15`: 1.892 record, 124 information set, từ 2010-04-23T08:11:29+00:00 đến 2025-02-21T20:30:50+00:00. Corpus gate `OUTCOME_BLIND_CORPUS_GATE_PASS_EXTRACTION_AUTHORIZED` chỉ cho phép extraction; chưa cho phép đọc giá. Có 724 item bị loại vì thiếu trường bắt buộc và một snapshot tải đủ byte nhưng không parse được XML; không được phục hồi các item này sau khi xem outcome.

## Extractor và data gate

Mỗi record được score bằng local `ministral-3:8b`, một worker, batch 4, temperature 0, seed `20260908`, cùng response schema và validator đã dùng cho v14. Input duy nhất của model là `record_id` và `text`. Output bắt buộc gồm `btc_relevance`, `event_type`, `affected_assets`, `direction`, `severity`, `reported_surprise`, `expected_horizon`, `confidence`, và `evidence_span`. Trước run phải đóng băng hash model, prompt, schema, corpus, corpus gate, predeclaration và runner.

Extraction gate PASS chỉ khi đủ 1.892 record đúng thứ tự, không lỗi, mọi trường schema-valid và `evidence_span` là substring chính xác của text. Eligibility khóa trước model là `btc_relevance` trong `{direct, systemic}` và `event_type` trong `{macro_liquidity, regulation, etf_institutional_flow, exchange_security, liquidation_leverage, network_protocol, fraud_legal, adoption_business}`. Không keyword filter, lọc thủ công hay sửa eligibility sau outcome. Target join chỉ mở khi có ít nhất 96 information set eligible.

## Target và candle artifact

Chỉ sau data gate PASS mới được tải và audit Binance Vision BTCUSDT spot 4h. Target duy nhất là simple return 24 giờ: execution open là open 4h đầu tiên có `open_time > archive_capture_at`, target là `open[t+24h] / open[t] - 1`. Candle chỉ dùng làm target và chấm điểm; không được vào prompt, eligibility, feature hay fold. Artifact candle là post-hoc versioned evaluation data, không tự chứng minh dữ liệu đã sẵn có theo thời gian thực tại information time.

## Arms, model và split

`prior` là mean target trong training fold và chỉ dùng diagnostic. Comparator chính `llm-sentiment` gồm direction fractions, signed direction, severity/confidence có dấu, và mean/max của severity, reported_surprise, confidence. Treatment `llm-event-conditioned` thêm relevance fractions, event-type fractions, expected-horizon fractions và signed impact theo event type/relevance; trọng số relevance cố định direct 1.0, systemic 0.75.

Mọi feature dự báo phải có tiền tố `llm_` và truy trực tiếp tới output extractor. Cấm OHLCV, return, volatility, volume, funding, regime, technical indicator, source identity, archive metadata, article count, text length, recency, calendar và deterministic metadata.

Dùng Ridge `alpha=10`, standardization chỉ fit trên training fold, không tuning. Sắp theo `archive_capture_at`; ba expanding fold, mỗi fold 24 information set OOS liên tiếp, purge 24 giờ. Phải có đúng 72 OOS prediction và event prediction không hằng.

Uncertainty dùng paired moving-block bootstrap trong từng fold, 5.000 draw, block 4 information set, seed `20260908`, CI 95%. Predictive gate PASS khi đồng thời: cận dưới CI 95% của `MSE(sentiment)-MSE(event)` > 0; cận dưới CI 95% Pearson event > 0; event thắng sentiment theo MSE ở ít nhất 2/3 fold; và đủ 72 OOS prediction không hằng.

Nếu bất kỳ gate nào fail, khóa artifact âm và dừng trước threshold, action mapping, backtest, Tech+LLM và sealed holdout. Predictive PASS cũng chỉ cho phép viết một predeclaration backtest development riêng; không chứng minh lợi nhuận hay khả năng live.

## Kết quả data gate đã khóa

Corpus gate outcome-blind đạt với 1.892 record trên 124 information set. Extraction hoàn tất 1.892/1.892 record, không có lỗi; count, order, schema và `evidence_span` đều đạt. Eligibility đã predeclare giữ lại 431 record nhưng chỉ tạo 64 information set duy nhất theo `archive_capture_at`, thấp hơn ngưỡng 96 và thiếu 32 set. Artifact `paper/input/results/llm/v15/cftc_rss_archive_predictive_v15/extraction_gate.json` vì vậy có trạng thái `DATA_GATE_FAIL_STOP_BEFORE_TARGET_JOIN`. Không target nào được tạo, không metric predictive nào được tính và không backtest nào được mở.