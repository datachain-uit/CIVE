# Giao thức phát triển AI/LLM event-risk v3

> Trạng thái: event extractor v3.9 đã PASS full extraction, nhưng predictive gate `h24_return` v3.1.1 và raw `h24_realized_volatility` v3.2 đều FAIL trên development OOS. LLM-only v3 dừng trước threshold/action mapping, backtest, `Tech+AI/LLM` và sealed holdout.

## Mục tiêu và vai trò của LLM

LLM v3 không phát lệnh giao dịch trực tiếp. LLM chỉ chuyển từng headline thành một bản ghi sự kiện có cấu trúc. Mô hình thống kê downstream dùng các đặc trưng sự kiện, thị trường và regime để ước lượng nhiều outcome. Chỉ một treatment vượt predictive gate ngoài mẫu mới được phép thiết kế overlay cho Tech-Control.

Estimand ở giai đoạn này là thông tin dự báo ngoài mẫu của vector sự kiện so với hai đối chứng: market-only và market-plus-deterministic-text-metadata. Return hoặc Sharpe của `Tech+LLM` chưa phải estimand và không được xem.

## Sáu sửa đổi bắt buộc

1. **Target phù hợp thông tin.** Giữ target thô cho return, realized volatility, max favorable excursion và max adverse excursion. Nhãn tail/risk chỉ được tạo bằng threshold ước lượng trong training fold.
2. **Không pha loãng tin.** Trích xuất ở cấp headline, giữ entity, quan hệ với BTC, loại sự kiện, novelty, severity, surprise, direction, source và thời gian. Bản ghi `none` vẫn được giữ để đo precision và coverage.
3. **Nhiều horizon.** Khai báo trước 4h, 12h, 24h và 72h tính từ BTCUSDT open sau cutoff 4 giờ. Không chọn horizon bằng full-sample outcome.
4. **Không nén sớm.** Output LLM là vector sự kiện, không có trường `action`. Aggregation bảo toàn event type, relevance, direction, severity, novelty, source và horizon expectation.
5. **Thích nghi regime có kiểm soát.** Regime chỉ dùng dữ liệu có trước cutoff. Downstream dùng expanding/rolling walk-forward; trọng số nguồn hoặc model chỉ được cập nhật từ sai số OOS đã biết tại thời điểm đó.
6. **Mật độ action là cổng sau cùng.** Không dùng threshold tuyệt đối 0,30/0,70. Sau khi predictive gate đạt, policy overlay phải được khai báo trên development folds và chứng minh đủ effective sample ở từng fold trước backtest treatment.

## Hợp đồng trích xuất sự kiện

Mỗi headline tạo đúng một event object với các trường bắt buộc. Transport được phép gom tối đa bốn headline vào một request để giảm thời gian/nhiệt. Model phải giữ thứ tự và echo `item_id` ngắn trong batch; postprocessor ánh xạ deterministic về `headline_id` frozen và có đúng một event object cho mỗi input:

- `headline_id`, `published_at`, `source_domain` và `coin_type` được sao hoặc ánh xạ từ input bằng code, không cho model sửa.
- `btc_relevance`: `direct`, `systemic`, `indirect` hoặc `none`.
- `event_type`: `macro_liquidity`, `regulation`, `etf_institutional_flow`, `exchange_security`, `liquidation_leverage`, `network_protocol`, `fraud_legal`, `adoption_business`, `market_commentary` hoặc `other`.
- `affected_assets`: danh sách entity/ticker đã canonicalize alias đóng và dedupe giữ thứ tự. Trường này được kiểm tra độc lập với `btc_relevance`; postprocessor không thêm BTC hoặc đổi relevance để tạo nhất quán giả.
- `direction`: `positive`, `negative`, `mixed` hoặc `unclear`.
- `severity` và `reported_surprise` nằm trong `[0,1]`; `reported_surprise` chỉ phản ánh dấu hiệu bất ngờ được nêu trong headline, không phải market surprise đã quan sát.
- `expected_horizon`: `4h`, `12h`, `24h`, `72h` hoặc `unknown`.
- `confidence` nằm trong `[0,1]`; `evidence_span` là đoạn ngắn có trong headline. Postprocessor chỉ được chuẩn hóa quote, dash, khoảng trắng không ngắt và dấu câu để tìm vị trí, rồi phải cắt lại nguyên văn từ headline frozen.

Schema không chứa realized outcome, future return, action hoặc position size. Article deduplication, recurrence, novelty và source counts được tính deterministic ngoài LLM chỉ từ headline đã xuất bản trước cutoff. Novelty không được yêu cầu từ model khi model chỉ thấy một headline.

## Split và chống leakage

- Observation time là `available_at`; fill giả định sớm nhất là open 4H kế tiếp.
- Split theo thời gian, có purge ít nhất bằng horizon dài nhất 72h giữa train và validation.
- Chuẩn hóa, event prevalence, threshold tail, feature selection, calibration và hyperparameter đều fit trong training fold.
- Một headline hoặc content hash không được xuất hiện ở cả train và validation.
- Memory chỉ truy xuất event có outcome hoàn tất trước cutoff hiện tại. Outcome của case không được đưa vào prompt extractor; chỉ dùng downstream sau khi extraction đã khóa.
- Development window và validation đã xem phải được ghi riêng. Không được gọi lại là sealed holdout.

## Đối chứng và ablation

Ba predictive baseline bắt buộc dùng cùng folds và target:

1. `market-only`: market, funding, breadth và regime.
2. `metadata-only`: market-only cộng source, coin type, article count, recency và deterministic recurrence; không dùng semantic output LLM.
3. `event-vector`: metadata-only cộng output event extractor.

Ablation tối thiểu: bỏ relevance filter, bỏ event type, bỏ deterministic novelty/recurrence, bỏ reported surprise, bỏ regime adaptation, bỏ memory và bỏ từng nhóm nguồn. Lợi ích của LLM là chênh lệch paired OOS giữa `event-vector` và `metadata-only`, không phải hiệu suất tuyệt đối của toàn pipeline.

## Cổng tuần tự

1. **Data gate:** schema 100%, timestamp hợp lệ, không trùng hash xuyên fold, không leakage, coverage từng horizon được báo cáo.
2. **Extractor gate:** hai run deterministic trên mẫu 114 headline, 38 strata năm × source × Bitcoin/non-Bitcoin, tối đa bốn headline/request; schema, count, order, ID và evidence-substring đạt 100%. Agreement được báo cáo riêng cho category và continuous fields; ngưỡng chính xác nằm trong config predeclaration trước inference.
3. **Predictive gate:** so sánh paired OOS với baseline, CI 95%, calibration và effective sample theo fold. Metric chính và ngưỡng pass phải đăng ký sau target audit nhưng trước khi xem prediction outcome.
4. **Overlay design gate:** chỉ mở nếu một target/horizon đã đăng ký vượt predictive gate. Policy chỉ được `veto`, `downsize` hoặc `confirm` tín hiệu Tech; chưa được tự tạo trade mới ở phiên bản đầu.
5. **Tech+LLM backtest gate:** chỉ mở sau khi code, model digest, prompt, feature contract, folds, target, policy và chi phí đều được freeze.

## Trình tự thực hiện

1. Khóa bằng chứng direct-direction v1/v2.
2. Tạo target panel thô và audit coverage, tuyệt đối chưa chọn target thắng.
3. Khóa schema/prompt extractor và chạy reliability nhỏ.
4. Extract toàn corpus một lần bằng model đã qua reliability.
5. Chạy baseline và ablation walk-forward.
6. Đăng ký và kiểm định đúng một treatment chính.
7. Chỉ khi đạt mới thiết kế rồi freeze `Tech+AI/LLM`.

## Kết quả extractor Stage 1

V3, v3.1 và v3.2 lần lượt dừng do scale severity, sao chép hash dài và khác biệt dấu câu trong evidence. Không lần nào xem market outcome. V3.3 giữ nguyên model, mẫu, batch size, seed, event fields và ngưỡng gate; chỉ khóa transport `item_id` và căn chỉnh evidence deterministic.

Hai run v3.3 đều đạt 114/114 schema/count/order/ID/evidence. Agreement category đạt 114/114 cho mọi trường, affected-assets mean Jaccard bằng 1,0 và mọi sai khác continuous bằng 0. Stage 1 chỉ mở bước 4: full extraction 39.393 headline không nối outcome.

Full extraction v3.3 dừng tại batch 5 vì model dùng ellipsis để bỏ các từ nằm giữa một evidence span. V3.4 mở rộng ellipsis thành đúng substring bao phủ các mảnh nguồn chỉ khi ít nhất hai mảnh xuất hiện nguyên văn và đúng thứ tự; các trường hợp còn lại vẫn bị từ chối. Hai run Stage 1 v3.4 tiếp tục đạt 114/114 ở mọi kiểm tra, nhưng full extraction dừng tại batch 14 do source quote hỏng encoding và một evidence token không có trong headline.

V3.5 predeclare fallback toàn headline frozen khi strict alignment thất bại và gắn `evidence_fallback=true`; event classification giữ nguyên. Hai run Stage 1 đều đạt 114/114 schema/count/order/ID/evidence, không dùng fallback, agreement category đạt 114/114, affected-assets mean Jaccard bằng 1,0 và mọi sai khác continuous bằng 0. Full extraction v3.5 dừng tại batch 108 sau 428 success và 4 error vì model trả alias `Bitcoin (BTC)` cho một item direct-BTC, trong khi validator chỉ nhận đúng `BTC` hoặc `Bitcoin`.

V3.6 chỉ canonicalize allowlist đóng gồm `BTC`, `Bitcoin`, `Bitcoin (BTC)`, `BTC (Bitcoin)`, `Bitcoin/BTC` và `BTC/Bitcoin`; v3.7 bổ sung wrapped-BTC aliases; v3.8 dedupe deterministic sau canonicalization. V3.9 bỏ cross-field coupling giữa `btc_relevance=direct` và BTC asset label nhưng giữ mọi validation khác. Hai run Stage 1 v3.9 đều đạt 114/114, 0 fallback và agreement tuyệt đối. Full extraction v3.9 đạt 39.393/39.393 success, 0 lỗi và completion gate PASS; chưa có predictive claim.

## Predeclaration predictive gate sau extractor v3.9

- Treatment chính duy nhất là `event-vector`; đối chứng trực tiếp là `metadata-only`, và `market-only` được báo cáo như baseline nền.
- Target chính duy nhất là BTC `h24_return`, tính từ open 4H sau execution delay 4 giờ. Lựa chọn này kế thừa horizon 24h của pipeline causal trước và không dựa trên so sánh outcome giữa các horizon.
- Mô hình cho cả ba nhánh là linear Ridge với `alpha=10`, chuẩn hóa mean/std chỉ trên training fold; không tuning hyperparameter.
- Năm expanding folds dùng 72 giờ purge. Kích thước train lần lượt là 365, 507, 649, 791 và 933; validation lần lượt là 139, 139, 139, 139 và 143, tổng 699 prediction OOS.
- Metadata gồm article count, source/coin-type fractions, recency, headline length và exact-recurrence/token-novelty 30 ngày chỉ dùng lịch sử trước cutoff. Headline trùng normalized text chỉ đóng góp semantic event ở lần xuất hiện đầu tiên; recurrence vẫn được đo nhân quả trên luồng quá khứ.
- Event-vector thêm fixed fractions của relevance, event type, direction và expected horizon; mean/max severity, surprise, confidence; asset count, fallback fraction, high-severity fraction và directional severity. Không dùng free-text asset identity làm vocabulary.
- Uncertainty dùng paired moving-block bootstrap theo fold, block 7 ngày, 5.000 lần, seed `20260903`.
- Gate PASS chỉ khi đủ 699 OOS record, cận dưới CI 95% của `MSE(metadata-only) - MSE(event-vector)` lớn hơn 0, cận dưới CI 95% Pearson giữa event prediction và target lớn hơn 0, event-vector thắng metadata-only về MSE ở ít nhất 3/5 fold và prediction không hằng.
- Nếu một check fail, dừng trước threshold, action mapping, ablation mở rộng, backtest hoặc `Tech+LLM`. Nếu toàn bộ PASS, quyền duy nhất được mở là thiết kế ablation và overlay trên development data.

## Kết quả predictive gate

Lần gọi v3.1 đầu tiên dừng ở phép kiểm tra hash đầu tiên do config ghi SHA-256 chữ hoa còn evaluator so sánh chuỗi chữ thường; chưa artifact dữ liệu nào, kể cả target panel, được load. Protocol-deviation đã khóa sự cố này. Revision v3.1.1 chỉ đổi biểu diễn hash sang chữ thường, giữ nguyên target, features, folds, model, bootstrap và ngưỡng gate.

V3.1.1 tạo đủ 699 prediction OOS. Event-vector có MSE 0,0007232553 so với 0,0006923442 của metadata-only; chênh lệch `MSE(metadata)-MSE(event)` bằng -0,0000309111 với CI 95% [-0,0000618160; 0,0000038424]. Pearson của event prediction với `h24_return` bằng -0,04173 với CI 95% [-0,11629; 0,03363], và event-vector chỉ thắng metadata-only ở 1/5 fold. Ba điều kiện chính đều fail; pipeline dừng trước threshold, action mapping, ablation mở rộng, backtest và `Tech+LLM`.

## Predeclaration predictive gate cho rủi ro 24h

Đây là một estimand mới về magnitude/risk, không phải thay đổi hậu kiểm của gate return. Kết quả `h24_return` v3.1.1 đã được biết trước khi đăng ký thí nghiệm này; giá trị, phân phối và prediction outcome của các target risk chưa được xem.

- Target chính duy nhất là raw `h24_realized_volatility`, được tính bằng căn bậc hai tổng bình phương log-return của các close 4H từ entry sau execution delay 4 giờ trong cửa sổ 24 giờ.
- Lý do chọn target không dựa trên outcome: event severity/surprise được giả thuyết liên hệ với độ lớn biến động, còn mục tiêu downstream là `veto/downsize` rủi ro thay vì dự báo dấu return.
- Ba nhánh, toàn bộ feature contract, quy tắc dedupe, năm expanding folds với purge 72 giờ, Ridge `alpha=10`, chuẩn hóa train-only và 5.000 paired moving-block bootstrap seed `20260903` được giữ nguyên từ v3.1.1.
- Gate PASS yêu cầu đồng thời đủ 699 OOS record, cận dưới CI 95% của `MSE(metadata-only)-MSE(event-vector)` lớn hơn 0, cận dưới CI 95% Pearson của event prediction với realized volatility lớn hơn 0, event-vector thắng metadata-only ít nhất 3/5 fold và prediction không hằng.
- Không được thử target risk khác, horizon khác, transform khác, feature selection hoặc hyperparameter khác trong gate này.
- Nếu FAIL, khóa kết quả âm và dừng LLM-only v3 trước threshold/action/backtest. Nếu PASS, quyền duy nhất được mở là predeclare một risk-overlay `veto/downsize` trên development data; chưa được xem sealed holdout hoặc claim hiệu quả giao dịch.

## Kết quả predictive gate rủi ro 24h

V3.2 tạo đủ 699 prediction OOS. Event-vector có Pearson 0,20710 với raw `h24_realized_volatility`, CI 95% [0,12968; 0,27476], nhưng MSE bằng 0,0001749815 so với 0,0001651943 của metadata-only. Chênh lệch `MSE(metadata)-MSE(event)` bằng -0,0000097873 với CI 95% [-0,0000175203; -0,0000011651], và event-vector chỉ thắng 1/5 fold.

Do mục tiêu là giá trị gia tăng của semantic event so với metadata-only, tương quan dương tuyệt đối không đủ để PASS khi sai số tăng có CI hoàn toàn âm. Gate v3.2 FAIL; không thử target risk, horizon, transform, feature selection hoặc model khác, và không mở risk overlay hay backtest.
