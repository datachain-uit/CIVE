# Ghi chú triển khai pipeline LLM

## Trạng thái kết luận

Nhánh direct-direction v1/v2 đã được khóa dưới trạng thái `frozen-negative-development-evidence`. Freeze này bảo toàn kết quả thất bại và không cấp quyền giao dịch. Không candidate nào trong nhánh này đủ điều kiện chạy live hoặc so sánh sealed với Tech-Control. Event-risk v3.9 đã PASS full extraction 39.393/39.393 với 0 lỗi, nhưng gate return v3.1.1 và volatility v3.2 đều FAIL trên 699 prediction OOS. LLM-only v3 dừng trước threshold, action mapping và backtest.

## Quy tắc nhiệt bắt buộc

- Không bắt đầu sustained compute nếu NVIDIA GPU từ 75°C trở lên.
- Trong khi chạy phải đọc sensor ít nhất mỗi 5 giây; từ 75°C phải dừng producer, giữ checkpoint nguyên tử, unload model và đưa Windows về Balanced.
- Chỉ resume khi GPU không quá 70°C.
- LLM dùng một worker, không chạy nhiều heavy job song song; ưu tiên kéo dài thời gian chạy qua đêm.
- Kết thúc phải unload model, xác nhận không còn compute process, GPU compute 0% và power plan Balanced.

## Kiểm toán dữ liệu legacy

`historical_ai_data.json` cũ có 5.000 dòng nhưng chỉ 1.113 text hash và 14 ngày xuất bản. Nó không lưu publication timestamp. Các output Llama/Qwen cũ từng thay ngày thật bằng timestamp tuần tự trong năm 2026 và từng điền lỗi timeout/parse thành 0. `historical_microstructure` cũng chứa proxy/estimated input và không phải corpus LLM. Vì vậy mọi AI/Hybrid backtest dựa trên nhóm legacy đều bị thay thế và không được dùng làm bằng chứng luận văn.

## Corpus nhân quả hiện hành

- Nguồn: CryptoVision v2, DOI `10.17632/3c3xtxtfb6.2`, CC BY 4.0.
- SHA-256 ZIP: `0c0ce86fc0a3b90378d36fbb27cd08137fd1fd9f72030cfc50a4aa967380a142`.
- Input: 188.431 dòng; sau kiểm tra và deduplicate còn 117.444 headline duy nhất.
- Coverage: 2017-08-17 đến 2025-08-27, 2.927 ngày UTC, 6 domain.
- Chỉ nhập URL, title, publication time và coin type. Loại toàn bộ sentiment label/score, OHLCV và future price movement của dataset nguồn.
- Daily information set hoàn thành lúc 00:00 UTC ngày kế tiếp. Mỗi ngày tối đa 48 headline bằng domain round-robin deterministic; 92.483 headline được chọn và 1.145 ngày chạm trần.
- Lỗi model luôn là error rõ ràng, không điền neutral score.

## Llama 3: độ tin cậy vận hành

Model `llama3:latest` 8B Q4, digest `365c0bd3c000a25d28ddbf732fe1c6add414de7275464c4e4d1c3b5fcb5d8ad1`.

| Kiểm tra | Kết quả | Kết luận |
|---|---:|---|
| Pilot 12 article × 2 | 24/24 schema; 12/12 score khớp | Qua pilot nhỏ |
| Pilot 18 daily set × 2 | 36/36 schema; 18/18 score khớp | Qua pilot nhỏ |
| Audit 108 daily set × 2 | 98/108 score khớp; MAE 0,0111; max 0,4; action 104/108 | Không deterministic |
| Hai full run | 2.927/2.927 success mỗi run | Vận hành đầy đủ |
| So sánh full run | 2.611/2.927 score khớp; MAE 0,01597; max 0,90; action 2.862/2.927 | 65 action bất đồng |

Hai-worker bị loại vì làm giảm repeatability. Full run thứ hai dùng một worker và delay 10 giây giữa request để tuân thủ nhiệt.

## Luật hành động và kết quả Llama

Luật predeclared: BTCUSDT long khi score ít nhất 0,30 và confidence ít nhất 0,70; trường hợp khác, gồm missing/error, là flat. Information set hoàn tất 00:00 UTC và fill sớm nhất ở open 04:00 UTC. Threshold không được tối ưu bằng return.

| Biến thể | Return | MDD | Fills | Hiệu chuẩn chính |
|---|---:|---:|---:|---|
| Single full run | +36,35% | 23,22% | 326 | long-flat +14,67 bps; CI [-21,46; +48,59] |
| Dual-run conservative consensus | +32,75% | 23,22% | 322 | long-flat +15,16 bps; CI [-21,74; +49,54] |

Consensus lấy score và confidence nhỏ hơn của hai run; chỉ long khi cả hai cùng vượt threshold. Nó xử lý bất đồng hành động nhưng không cải thiện bằng chứng dự báo. Pearson CI của single run `[-0,0388; 0,0857]` và consensus `[-0,0330; 0,0909]` đều cắt 0.

## Qwen 2.5 7B challenger

Model `qwen2.5:7b` Q4_K_M, digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`. Model được chọn trước kết quả do instruction following và structured JSON; không chọn theo return.

Stage 1 dùng 108 ngày stratified × 2 run, cùng prompt, seed và threshold. Kết quả: 216/216 schema; 108/108 score khớp; 108/108 action khớp; MAE và max difference đều 0. Stage 1 đạt toàn bộ cổng vận hành.

Stage 2 được phép chạy đúng một full inference 2.927 record rồi chỉ hiệu chuẩn outcome, chưa backtest. Kết quả: 2.927/2.927 success, 1.110 observation, Pearson `0,0081`, Spearman `-0,0155`, directional accuracy `48,13%`, long-flat `-10,63 bps`. Pearson CI `[-0,0669; 0,0805]` và long-flat CI `[-42,04; 21,03]` đều có cận dưới không lớn hơn 0.

Protocol yêu cầu cận dưới của cả hai CI phải dương. Vì vậy trạng thái là `stage2-fail-stop-before-repeat-or-backtest`. “Loại Qwen 2.5” chỉ có nghĩa là loại khỏi pipeline trading hiện tại; không phải kết luận model kém nói chung.

## Gemma 3 4B challenger

Model `gemma3:4b` Q4_K_M, digest `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a`. Đây là challenger direct-direction cuối cùng, được khai báo trước khi xem output vì thuộc họ model khác Llama/Qwen và đủ nhỏ để chạy một worker trên GPU 6 GB. Model không được chọn bằng return.

Stage 1 giữ nguyên corpus, prompt, seed, threshold và yêu cầu schema hoàn hảo `108/108` cho mỗi run. Sau 10 information set đầu tiên, chỉ 8 response hợp lệ và 2 response không chứa đúng ba trường `score`, `confidence`, `reason_code`. Vì hai lỗi đã xuất hiện, số schema success tối đa nếu tiếp tục hết run chỉ còn `106/108`; cổng đã không thể đạt về mặt toán học.

Runner áp dụng fail-fast, giữ checkpoint nguyên tử rồi dừng trước khi hoàn thành run 1. Không chạy run 2, calibration hay backtest; không xem market outcome để ra quyết định. Trạng thái chính thức là `stage1-fail-fast-stop-before-completing-run1`. Kết luận này chỉ bác bỏ Gemma 3 4B khỏi contract output hiện tại, không đánh giá chất lượng chung của model.

## Freeze bằng chứng direct-direction v1/v2

Snapshot `paper/input/results/frozen/llm_direct_direction_v1` chứa 86 artifact với checksum từng file và seal riêng cho manifest. Snapshot gồm artifact luận văn, kết quả/config runtime của Ministral, Nemotron và Llama 3.1, cùng các gate/calibration chính còn tồn tại trong production workspace. Trạng thái nghiên cứu là bằng chứng development âm; không phải software release, treatment thành công hoặc sealed holdout.

Không được sửa artifact trong snapshot. Mọi phân tích event/risk, multi-horizon hoặc overlay dùng experiment ID và thư mục mới, không được ghi đè hay đổi diễn giải kết luận v1/v2.

## Event-risk v3

Protocol mới nằm tại `paper/working/protocols/LLM_Event_Risk_Protocol_v3.md`. LLM chỉ trích xuất sự kiện cấp headline; downstream model mới dự báo return, realized volatility, max favorable excursion và max adverse excursion tại 4h, 12h, 24h và 72h. Output extractor không có `action`.

Target audit có đủ 1.079/1.079 ngày từ 2022-09-12 đến 2025-08-27. Input extractor có 39.393 headline và 39.393 ID duy nhất; input này không chứa market fields hoặc outcome. Schema event giữ relevance BTC, event type, affected assets, direction, severity, reported surprise, expected horizon, confidence và evidence span. Novelty/recurrence được tính deterministic từ lịch sử trước cutoff, không giao cho model nhìn một headline tự ước lượng.

Ba đối chứng predictive bắt buộc là market-only, metadata-only và event-vector. Mọi threshold tail, chuẩn hóa, feature selection và regime adaptation phải fit trong training fold. Chưa được chọn target/horizon bằng kết quả full sample và chưa được chạy `Tech+AI/LLM`.

Stage 1 extractor đã được predeclare cho Ministral 3 8B vì model này đạt strict-JSON reliability ở contract cũ, không phải vì return. Mẫu frozen có 114 headline thuộc 38 strata năm × source × Bitcoin/non-Bitcoin. Mỗi run có 29 batch, tối đa bốn headline/batch; hai run phải đạt 100% schema/count/order/ID/evidence checks và toàn bộ ngưỡng agreement đã ghi trong config. Nếu đạt, quyền duy nhất được mở là full extraction 39.393 headline không nối outcome.

V3 gốc fail ngay batch đầu vì model dùng mức severity 2 và 3 thay vì số liên tục trong `[0,1]`. V3.1 làm rõ scale nhưng fail sau 44 mẫu hợp lệ do model chép sai một ký tự trong SHA-256 dài. V3.2 chuyển transport sang `item_id` ngắn, ánh xạ deterministic về `headline_id` gốc, nhưng fail sau 88 mẫu hợp lệ vì model đổi dấu ngoặc cong thành dấu thẳng và bỏ một dấu phẩy trong evidence span. Các lần sửa này được khai báo trước lần inference kế tiếp và không xem outcome.

V3.3 khóa postprocessor chỉ chuẩn hóa quote, dash, non-breaking space và dấu câu để tìm vị trí, sau đó cắt lại evidence nguyên văn từ headline frozen. Hai run v3.3 đều đạt 114/114 schema/count/order/ID/evidence. Agreement của `btc_relevance`, `event_type`, `direction` và `expected_horizon` đều 114/114; affected-assets mean Jaccard bằng 1,0; mọi MAE và max difference của severity, reported surprise và confidence bằng 0. Gate có trạng thái `stage1-pass-full-extraction-authorized`. Kết quả này không phải predictive evidence và không cấp quyền nối outcome, backtest hoặc Tech+LLM.

Full extraction v3.3 đã dừng fail-fast tại batch 5 sau 20 record: 16 success và 4 error. Một output dùng `Headwinds... Luna Classic Pares Rally`, trong khi headline frozen có các từ ở giữa; validator vì vậy từ chối đúng contract exact-substring. Failure manifest, config, checkpoint, progress và stdout đã được khóa trong `paper/input/results/llm/v3/`; không outcome hoặc backtest nào được xem.

V3.4 chỉ bổ sung phép căn ellipsis deterministic: phải có ít nhất hai mảnh không rỗng xuất hiện nguyên văn, đúng thứ tự; output được thay bằng đúng một substring bao phủ các mảnh trong headline frozen. Mảnh thiếu hoặc đảo thứ tự vẫn fail. Hai run Stage 1 v3.4 đều đạt 114/114, mọi category agreement 114/114, affected-assets Jaccard 1,0 và mọi sai khác continuous bằng 0. Full extraction v3.4 sau đó dừng tại batch 14: 56 attempted, 52 success và 4 error. Batch lỗi chứa một headline có quote hỏng encoding và một record `btc_relevance=none` đưa evidence `Bitcoin` dù headline không có token này.

V3.5 giữ strict alignment làm đường chính. Khi alignment thất bại, postprocessor thay `evidence_span` bằng toàn bộ headline frozen và gắn `evidence_fallback=true`; mọi headline dài tối đa 198 ký tự, dưới giới hạn 240. Không field phân loại nào được sửa. Hai run Stage 1 v3.5 đều đạt 114/114 với 0 fallback, agreement tuyệt đối và mọi sai khác continuous bằng 0. Full extraction sau đó dừng tại batch 108: 432 attempted, 428 success, 4 error và 8 fallback; nguyên nhân là alias `Bitcoin (BTC)` không khớp allowlist canonical cũ.

V3.6 canonicalize đúng một allowlist đóng của các alias BTC tương đương trước khi áp dụng toàn bộ validator v3.5. `Wrapped Bitcoin (WBTC)` và mọi giá trị ngoài danh sách không được sửa. Regression test và replay nguyên batch lỗi v3.5 đều đạt. Hai run Stage 1 v3.6 đạt 114/114 với 0 fallback, agreement tuyệt đối và mọi sai khác continuous bằng 0. Full extraction v3.6 dừng fail-fast tại batch 312 sau 1.248 record: 1.244 success, 4 error và 37 fallback; batch lỗi dùng `Wrapped BTC` trong affected_assets của một item direct-BTC. V3.7 chỉ bổ sung allowlist đóng cho `Wrapped BTC/WBTC/Wrapped Bitcoin`; Stage 1 đạt 114/114 ở cả hai run, 0 fallback và agreement tuyệt đối. Full extraction v3.7 dừng fail-fast tại batch 193 sau 772 record: 768 success, 4 error và 18 fallback; canonicalization biến `wrapped BTC` thành `BTC`, trùng với `BTC` đã có trong cùng danh sách.

V3.8 canonicalize alias theo đúng allowlist v3.7 rồi dedupe deterministic, giữ lần xuất hiện đầu tiên và thứ tự của danh sách. Direct-BTC chỉ yêu cầu còn ít nhất một `BTC` hoặc `Bitcoin` sau bước này; mọi giá trị ngoài allowlist vẫn đi qua validator v3.5 không đổi. Bốn regression test, gồm replay nguyên batch lỗi v3.7 và kiểm tra alias ngoài danh sách vẫn fail, đều đạt. Hai run Stage 1 v3.8 đều đạt 114/114, 0 fallback, agreement tuyệt đối và mọi sai khác continuous bằng 0; gate chỉ cấp quyền một full extraction mới từ record 0, chưa nối outcome.

Full extraction v3.8 dừng fail-fast tại batch 313 sau 1.252 record: 1.248 success, 4 error và 32 fallback. Item gây lỗi được model gắn `btc_relevance=direct` nhưng affected_assets chỉ gồm `NYDIG`; mọi field còn lại hợp lệ. V3.9 bỏ duy nhất cross-field requirement giữa hai field này, giữ nguyên giá trị model và toàn bộ canonicalization, dedupe, schema/value/evidence validation khác. Bốn regression test, gồm replay nguyên batch lỗi v3.8 và kiểm tra asset rỗng vẫn fail, đều đạt trước predeclaration Stage 1; chưa xem outcome.

Hai run Stage 1 v3.9 đều đạt 114/114 schema/count/order/ID/evidence, 0 fallback, agreement categorical 114/114, affected-assets Jaccard 1,0 và mọi sai khác continuous bằng 0. Gate có trạng thái `stage1-pass-full-extraction-authorized`; quyền duy nhất được mở là một full extraction mới từ record 0, chưa nối outcome.

Full extraction v3.9 đạt 39.393/39.393 schema success, 0 error, 39.393/39.393 count, ID/order và evidence exact-substring, với 997 evidence fallback. Completion audit không xem outcome hoặc backtest và trả trạng thái `full-extraction-pass-downstream-design-authorized`. Kết quả này chỉ chứng minh artifact trích xuất đã hoàn tất theo contract; chưa chứng minh giá trị dự báo hoặc hiệu quả giao dịch.

## External market-impact v4

V4 kiểm tra một thay đổi representation thực chất thay vì sửa event-vector v3. Nguồn ngoài tại commit `2915946457bcf0604563b63d933d63313e71aeb2` dùng Cryptonews text và nhãn BTCUSDT daily `close[t+7] > close[t]`. Audit phát hiện 180.345 row chỉ tương ứng 480 URL trên 171 ngày, với bốn URL xuyên split nguồn; pipeline vì vậy regroup theo URL, giữ title cộng tối đa bảy paragraph đầu và split OOS theo ngày.

Frozen MiniLM encode 3.718 chunk. Linear Ridge head tạo 97 article prediction OOS nhưng Stage A FAIL: AUC 0,41731, CI 95% [0,30409; 0,53459], score separation -0,17456, CI 95% [-0,39492; 0,04003], và fold AUC lần lượt 0,64516/0,37647. Stop gate dừng trước scoring 39.393 project headline, nên không có Stage B hoặc project-target outcome cho v4.

## Full-text market-impact v5

V5 dùng corpus title/body 229.172 row, gần 229 nghìn article identity và 79 source. Sau điều kiện body tối thiểu 50 từ, dedupe và source-diverse selection, panel có 36.828 article từ 58 source trên 5.187 bucket 4 giờ. Mỗi bucket dùng tối đa tám article đã xuất bản trước open kế tiếp; target duy nhất là Bybit BTCUSDT open-to-open return 24 giờ.

Frozen MiniLM 256-token representation ghép mean và max pooling thành 768 chiều. Ba expanding fold tạo 2.177 prediction OOS. Fusion FAIL rõ ràng: MSE 0,0008577842 so với market-only 0,0007197286; paired delta MSE -0,0001380557, CI 95% [-0,0001653829; -0,0001109871]; Pearson -0,03617, CI 95% [-0,08295; 0,01007]; fold wins 0/3. Stop gate dừng trước threshold/action/backtest.

## Supervised contrastive market-impact v6

V6 giữ nguyên panel, target, folds và comparator v5. Trong mỗi training fold, raw return được chia thành ba lớp quantile cân bằng; MLP 768→128→32 được học bằng supervised contrastive loss rồi projection được nối với market features. Loss giảm ở cả ba fold và mỗi lớp có lần lượt 933, 1.175 và 1.421 training record, nên không có lỗi collapse lớp hoặc non-finite training.

Trên 2.177 prediction OOS, contrastive-only có MSE 0,0009715776 và Pearson -0,03223; fusion có MSE 0,0009791649 và Pearson -0,03446, so với market-only MSE 0,0007197286. Delta MSE market-fusion là -0,0002594363, CI 95% [-0,0002956143; -0,0002238377], tương ứng relative MSE reduction -36,0464%; Pearson CI 95% [-0,07670; 0,00718], fold wins 0/3. Gate FAIL và dừng trước threshold/action/backtest.

## Trạng thái Tech+LLM treatment

- Chưa có phương pháp LLM nào vượt predictive gate đã đăng ký trước.
- Direct-direction v1/v2 đã kết thúc; không được tiếp tục thử hàng loạt model rồi chọn model có backtest đẹp.
- Full extraction v3.9 đã PASS; predictive gate v3.1.1 đã được predeclare rồi FAIL trên target `h24_return`. Kết quả này bác bỏ standalone event-vector claim và không cho phép lấy v3.1.1 để chọn threshold/action hậu nghiệm.
- Risk gate v3.2 giữ nguyên features/model/folds và dùng raw `h24_realized_volatility`; Pearson event dương nhưng MSE xấu hơn metadata-only với CI hoàn toàn âm và chỉ thắng 1/5 fold. Gate FAIL và kết thúc LLM-only v3.
- Folds, target/horizon chính, predictive metric và stop gate downstream vẫn phải đăng ký trước khi xem prediction outcome.
- Tech+LLM không phụ thuộc vào LLM-only predictive PASS. HYB-001 đã khóa feature contract event-risk v3.9, polarity negative cho Tech long-only, policy `1/0,5/0` tại threshold 0,68/0,76, 24 opportunity, cluster-bootstrap quý 10.000 draw và bốn placebo trước evaluation.
- HYB-001 đã chạy đúng một exploratory paired evaluation rồi FAIL: paired net mean -2,15208 điểm phần trăm với CI 95% [-4,82034; -0,18626], paired gross mean âm, 0/3 fold dương và primary kém cả bốn placebo. Không được đổi threshold trên cùng outcome; sealed holdout chưa mở.
- HYB-002 đã materialize runner, replay inputs và exact assignment: 23 can thiệp trên 13 shadow trade. Tech giữ toàn bộ entry và shadow lifecycle; LLM chỉ giảm exposure xuống 0,5 trong một bar 4 giờ khi shock âm đúng asset/systemic được ít nhất hai source domain xác nhận.
- Exploratory development FAIL: mean paired net difference `-0,0021577` (tức `-0,2158%`) mỗi cửa sổ, cluster-bootstrap CI 95% `[-0,0037874; -0,0006255]`, paired gross mean `-0,0010282`, chỉ 1/3 fold dương. Primary vượt bốn placebo nhưng dấu hiệu ứng âm đã bác bỏ policy. Intrabar MDD chưa materialize; closed-trade MDD chỉ là proxy và không thể hỗ trợ PASS. Nguồn: `paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_development.json`.
