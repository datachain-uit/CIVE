# Giao thức predictive LLM-only trên ECB RSS archive v16

> Trạng thái: TARGET COVERAGE FEASIBILITY FAIL; STOPPED BEFORE CANDLE DOWNLOAD. Protocol này độc lập với v3--v15 và không dùng kết quả, target panel, prediction, threshold hay backtest của các candidate trước.

## Câu hỏi và information set

Câu hỏi duy nhất là: event-vector do LLM tạo từ tiêu đề bản tin ECB đã có trong snapshot Internet Archive có dự báo BTCUSDT spot return 24 giờ tốt hơn representation sentiment LLM tổng quát hay không?

Đơn vị quan sát là một `archive_capture_at`. Các item có cùng thời điểm này được aggregate thành một information set. `archive_capture_at` là information time duy nhất; `publisher_pubdate` chỉ là provenance và không dùng để đặt lệnh, chia fold hay tạo target.

Corpus bắt buộc là `ecb-rss-internet-archive-v16`: 2.249 record, 400 information set, từ 2010-03-11T18:50:00+00:00 đến 2026-08-31T02:15:20+00:00. Model chỉ nhận tiêu đề đã chuẩn hóa theo mẫu `TITLE: ...`; description và nội dung trang liên kết không được dùng. Corpus gate `OUTCOME_BLIND_CORPUS_GATE_PASS_EXTRACTION_AUTHORIZED` chỉ cho phép extraction; chưa cho phép đọc giá. Có 442 item hoặc snapshot-record bị loại theo quy tắc đã khóa, trong đó 405 item có `pubDate` không chứa UTC offset rõ ràng; không được phục hồi sau khi xem outcome.

## Extractor và data gate

Mỗi record được score bằng local `ministral-3:8b`, một worker, batch 4, temperature 0, seed `20260909`, cùng response schema và validator đã dùng cho v15. Input duy nhất của model là `record_id` và `text`. Output bắt buộc gồm `btc_relevance`, `event_type`, `affected_assets`, `direction`, `severity`, `reported_surprise`, `expected_horizon`, `confidence`, và `evidence_span`. Trước run phải đóng băng hash model, prompt, schema, corpus, corpus gate, predeclaration và runner.

Extraction gate PASS chỉ khi đủ 2.249 record đúng thứ tự, không lỗi, mọi trường schema-valid và `evidence_span` là substring chính xác của text. Eligibility khóa trước model là `btc_relevance` trong `{direct, systemic}` và `event_type` trong `{macro_liquidity, regulation, etf_institutional_flow, exchange_security, liquidation_leverage, network_protocol, fraud_legal, adoption_business}`. Không keyword filter, lọc thủ công hay sửa eligibility sau outcome. Target join chỉ mở khi có ít nhất 96 information set eligible.

## Target, model và predictive gate

Chỉ sau data gate PASS mới được tải và audit Binance Vision BTCUSDT spot 4h. Target duy nhất là simple return 24 giờ: execution open là open 4h đầu tiên có `open_time > archive_capture_at`, target là `open[t+24h] / open[t] - 1`. Candle chỉ dùng làm target và chấm điểm; không được vào prompt, eligibility, feature hay fold.

Comparator `llm-sentiment` và treatment `llm-event-conditioned` dùng cùng feature contract của v15. Mọi feature dự báo phải có tiền tố `llm_` và truy trực tiếp tới output extractor; cấm OHLCV, return, volatility, volume, funding, regime, technical indicator, source identity, archive metadata, article count, text length, recency, calendar và deterministic metadata.

Dùng Ridge `alpha=10`, standardization chỉ fit trên training fold, không tuning. Sắp theo `archive_capture_at`; ba expanding fold, mỗi fold 24 information set OOS liên tiếp, purge 24 giờ. Uncertainty dùng paired moving-block bootstrap trong từng fold, 5.000 draw, block 4 information set, seed `20260909`, CI 95%.

Predictive gate PASS khi đồng thời: cận dưới CI 95% của `MSE(sentiment)-MSE(event)` > 0; cận dưới CI 95% Pearson event > 0; event thắng sentiment theo MSE ở ít nhất 2/3 fold; và đủ 72 OOS prediction không hằng. Nếu bất kỳ gate nào fail, khóa artifact âm và dừng trước threshold, action mapping, backtest, Tech+LLM và sealed holdout.

## Kết quả extraction và data gate đã khóa

Extraction hoàn tất 2.249/2.249 record, không có lỗi. Kiểm toán xác nhận count, thứ tự, schema và `evidence_span` exact-substring đều đạt. Eligibility đã predeclare giữ lại 245 record trên 135 information set duy nhất theo `archive_capture_at`, vượt ngưỡng 96 với phần dư 39 set. Artifact `paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/extraction_gate.json` có trạng thái `DATA_GATE_PASS_TARGET_JOIN_AUTHORIZED`.

Kết quả này chỉ cấp quyền kiểm tra khả năng tạo target panel theo protocol. Chưa có target, metric predictive, threshold, action mapping, backtest, Tech+LLM hoặc sealed-holdout claim.

## Target coverage feasibility gate đã khóa

Sau data gate PASS, một source-start screen outcome-free chỉ gửi yêu cầu `HEAD` tới kho Binance Vision; không tải nội dung candle. Screen xác nhận tháng đầu năm 2017 có đồng thời tệp BTCUSDT spot 4h và checksum là 2017-08. Mốc dưới bảo thủ cho khả năng ghép target vì vậy là `2017-08-01T00:00:00+00:00`.

Trong 135 information set eligible, 94 set nằm trước mốc này. Ngay cả dưới giả định lạc quan rằng toàn bộ set còn lại đều ghép target thành công, trần chỉ là 41 set. Trần này thiếu 55 set so với mức tối thiểu 96 và thiếu 31 set so với yêu cầu đúng 72 dự báo OOS. Vì 41 < 72, cấu hình ba fold × 24 OOS đã predeclare không thể thực hiện; tải candle không thể khắc phục thất bại cấu trúc này.

Artifact `paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/target_coverage_feasibility_gate.json` có trạng thái `TARGET_COVERAGE_FEASIBILITY_FAIL_STOP_BEFORE_CANDLE_DOWNLOAD`. Theo stop rule, v16 dừng trước candle download, target construction, predictive evaluation, threshold, action mapping, backtest, Tech+LLM và sealed holdout. Không có outcome hoặc giá thị trường nào được đọc để đưa ra quyết định này.
