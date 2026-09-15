# WITHDRAWN — bản prospective tạo sai phạm vi yêu cầu

> Trạng thái: `WITHDRAWN_SCOPE_ERROR` trước khi chạy model hoặc đọc outcome. Người dùng yêu cầu dữ liệu lịch sử; bản này được giữ nguyên bên dưới chỉ để bảo toàn audit trail. Thiết kế có hiệu lực là `Tech_LLM_Historical_Risk_Attenuation_Protocol_HYB007.md`.

## 1. Vị trí trong chuỗi thí nghiệm

HYB-007 chỉ bắt đầu sau khi nhánh LLM-only đã đóng. Trong LLM-072, audit ETH outcome-free đã đạt 5.341 direct event trên 1.000 information date; chỉ sau PASS đó target ETH mới được tạo và transfer diagnostic mới chạy. Diagnostic có 699 dự báo OOS nhưng event-conditioned arm thua generic và thắng 0/5 fold, nên nhánh LLM-only không được mở action/backtest. Kết quả âm này không được dùng để chọn threshold cho HYB-007.

HYB-007 kiểm tra một estimand khác: **khi Tech-Control đã có exposure, liệu một cảnh báo rủi ro semantic được tạo từ tin mới theo thời gian thực có cải thiện kết quả sau chi phí bằng cách giảm tạm thời độ lớn exposure hay không**. Đây là conditional incremental value của LLM đối với Tech, không phải standalone alpha, transfer validation hay bằng chứng live.

## 2. Đối chứng và quyền hạn của LLM

- `T0`: Tech-Control canonical đã freeze, giữ nguyên universe, signal, execution, fee, funding và risk contract.
- `T1`: cùng quyết định Tech như T0; LLM chỉ được nhân độ lớn exposure hiện hành với 0,5 trong cửa sổ cảnh báo. LLM không chọn tài sản mới, không đảo dấu, không mở vị thế, không đổi stop và không kéo dài vị thế quá lịch của T0.
- Khi cảnh báo hết hạn, T1 trở về đúng exposure T0 nếu T0 vẫn còn vị thế. Các cửa sổ chồng lấn chỉ hợp nhất; exposure không giảm dưới 0,5 lần T0.

Một cảnh báo bắt đầu ở open nến UTC 4 giờ đầu tiên nằm nghiêm ngặt sau `available_at` và kéo dài ba nến 4 giờ. Cảnh báo chỉ hợp lệ khi output LLM đồng thời thỏa:

1. `direction = negative`;
2. `severity >= 0,70`;
3. `confidence >= 0,80`;
4. `expected_horizon` là `4h`, `24h` hoặc giá trị ngắn hạn tương đương trong schema đã khóa;
5. sự kiện trực tiếp nhắc tài sản T0 đang giữ, hoặc có scope systemic;
6. `event_type` thuộc nhóm đóng `exchange_security`, `fraud_legal`, `network_protocol`, `liquidation_leverage`.

Các hằng số này là policy thiết kế trước outcome, không phải threshold được hiệu chỉnh từ HYB-001--006 hoặc từ return của corpus prospective.

## 3. Nguồn và provenance prospective

Nguồn v1 chỉ gồm Cointelegraph RSS tại `https://cointelegraph.com/rss`, đã xác minh trả XML trước khi freeze. Collector khởi tạo một baseline URL và loại toàn bộ item đã tồn tại; không backfill. Chỉ item xuất hiện ở poll sau baseline mới được xét. Mỗi poll lưu raw XML, thời điểm tải UTC, HTTP status, header provenance, SHA-256 và mã collector. Với item mới, collector lưu raw HTML, URL chuẩn hóa, `published_at`, `available_at` là thời điểm capture thành công đầu tiên, text chuẩn hóa và SHA-256.

Admission không do LLM quyết định. Record phải có URL, timestamp có timezone, title/text, không thuộc đường dẫn press release/commissioned, và có ít nhất một alias đóng của BTC, ETH, SOL, XRP, BNB hoặc một cụm systemic crypto. Thêm nguồn, alias hoặc rule admission tạo phiên bản protocol mới và không được nhập chung vào HYB-007 v1.

Extractor là `ministral-3:8b`, digest `1922accd5827ebe6829e536369195db25eaf664528dc66206d646ea3bb386b71`, quantization Q4_K_M, prompt/schema/postprocessor v3.9 đã PASS reliability và full extraction. Inference phải dùng temperature 0, seed 20260823, batch 4 và một worker. Trước mỗi đợt inference phải tuân thủ ngưỡng nhiệt GPU của workspace.

## 4. Audit effective sample trước outcome

Không được tạo forward return, PnL, MDD, adverse excursion hoặc metric hiệu năng trước khi audit này PASS. Audit chỉ dùng provenance, LLM output, timestamp, rule cảnh báo và trạng thái Tech tại hoặc trước action time.

Một cluster độc lập là hợp của các cảnh báo cùng asset và cùng event type có action time cách nhau không quá 24 giờ. Gate mẫu yêu cầu đồng thời:

- ít nhất 30 cluster cảnh báo đủ điều kiện;
- ít nhất 90 ngày lịch từ cluster đầu đến cluster cuối;
- mỗi chronological third có ít nhất 8 cluster;
- ít nhất 15 cluster direct-asset, không chỉ systemic;
- ít nhất hai asset khác nhau có từ 5 cluster trở lên;
- 100% record có raw feed/page hash, `available_at` UTC, exact model digest và schema-valid output;
- không có gap collector dài hơn 48 giờ mà không được ghi rõ trong audit.

Nếu chưa đạt, trạng thái duy nhất là `COLLECTING_INSUFFICIENT_EFFECTIVE_SAMPLE`; không hạ ngưỡng và không xem outcome.

## 5. Evaluation chỉ sau sample PASS

Primary estimand là paired mean net return `T1 - T0` trên union các intervention window, đã gồm fee, slippage và funding theo contract Tech-Control. Cluster bootstrap 10.000 lần theo cluster sự kiện tạo CI 95%. Secondary risk endpoints là paired worst 4h return, 12h adverse excursion, expected shortfall 10% và full-period intrabar MDD. Secondary endpoint không thể cứu một primary FAIL.

Ba placebo được khóa trước outcome:

- `delayed_24h`: dời action đúng 24 giờ;
- `supportive_sign`: áp cùng policy cho event positive thay vì negative;
- `metadata_hash`: chọn deterministic bằng SHA-256 event ID trong tập event admitted để khớp số cluster primary nhưng không dùng semantic field.

HYB-007 chỉ PASS khi cận dưới CI 95% của primary lớn hơn 0, primary dương ở ít nhất 2/3 chronological third, T1 vượt cả ba placebo về paired mean net return, expected shortfall 10% không xấu hơn T0 và full-period intrabar MDD không xấu hơn T0. Nếu một điều kiện không đạt, kết luận là FAIL trong phạm vi policy prospective này; không retune cùng outcome.

## 6. Ranh giới claim

Trước sample PASS chỉ được claim rằng protocol và collector đã freeze hoặc đang thu thập. Sau evaluation, nếu có, kết quả vẫn là prospective shadow evidence, không tự động là live execution. Không dùng dữ liệu trước freeze, không nhập record v12 đã dừng, không dùng HYB-001--006 để chọn action rule và không kích hoạt sealed holdout cũ.
