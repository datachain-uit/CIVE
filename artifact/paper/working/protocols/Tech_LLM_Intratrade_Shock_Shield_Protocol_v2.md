# Giao thức Tech+LLM intratrade shock shield v2

> Trạng thái: EXPLORATORY DEVELOPMENT FAIL. Exact assignment đã khóa 23 intervention trên 13 shadow trade trước evaluation. Thiết kế này được hình thành sau khi đã xem kết quả HYB-001, nên kết quả trên vùng dữ liệu cũ không phải validation, sealed holdout hoặc live evidence.

## 1. Câu hỏi và failure mode cần sửa

HYB-002 kiểm tra liệu representation sự kiện v3.9 có giúp giảm exposure trong đúng cửa sổ shock ngắn hạn khi một vị thế Tech-Control đang mở hay không. Đây là giả thuyết interaction theo trạng thái vị thế, không phải giả thuyết LLM dự báo lợi nhuận vô điều kiện.

HYB-001 dùng headline xấu nhất của một ngày để veto hoặc downsize ngay tại entry rồi giữ quyết định đến hết trade. Cơ chế này có ba điểm yếu đã quan sát được: một headline đơn lẻ có quyền chi phối; relevance chưa gắn chặt với asset đang giữ; và opportunity cost kéo dài đến exit. HYB-002 thay đổi cả đơn vị quyết định lẫn quyền hạn của LLM, không điều chỉnh threshold HYB-001.

## 2. Kiến trúc và quyền hạn

Frozen Tech-Control giữ toàn quyền tạo entry, chọn symbol, hướng long, stop, trailing stop và exit. LLM không được veto, trì hoãn hoặc giảm entry; không tạo trade mới; không đảo chiều; không thay đổi đường đi của shadow Tech-Control.

Khi shadow Tech-Control đang giữ vị thế, HYB-002 kiểm tra trạng thái shock ở mỗi mốc 4 giờ hợp lệ. Nếu có một confirmed semantic shock mới, exposure của treatment giảm từ `1,0` xuống `0,5` trong đúng một bar 4 giờ. Ở mốc kế tiếp, exposure trở lại `1,0` nếu shadow trade vẫn còn mở. Nếu shadow Tech-Control thoát trong bar, treatment thoát cùng thời điểm và không tái nhập. Nhiều shock trong cùng trade-day chỉ tạo một lần can thiệp.

Việc giảm rồi phục hồi exposure phải chịu đầy đủ fee, slippage và funding theo cùng execution contract. Mọi lỗi, thiếu dữ liệu hoặc ambiguity dùng fallback `w=1` và được ghi audit.

## 3. Confirmed semantic shock

Một event cluster đủ điều kiện khi đồng thời thỏa mãn:

- `direction = negative`;
- `event_type` thuộc allowlist cố định `{exchange_security, network_protocol, fraud_legal, liquidation_leverage}`;
- `severity >= 0,7` và `confidence >= 0,7`;
- liên quan trực tiếp tới asset đang giữ qua allowlist alias cố định, hoặc có `btc_relevance = systemic`;
- có ít nhất hai `source_domain` độc lập trong cùng `information_date` và cùng `event_type`;
- tại decision timestamp chỉ dùng record có `available_at <= t`.

Alias tối thiểu của bốn asset xuất hiện trong vùng chồng lấp là `BTC ↔ {BTC, Bitcoin}`, `ETH ↔ {ETH, Ethereum}`, `SOL ↔ {SOL, Solana}` và `XRP ↔ {XRP}`. Không được thêm alias sau khi đọc outcome.

`expected_horizon` không tham gia gate vì phần lớn output v3.9 mang giá trị `unknown`; action duration được khóa độc lập ở một bar 4 giờ. Event score lớn nhất và polarity thuận lợi không tham gia policy.

## 4. Đơn vị quyết định và chống pseudoreplication

Đơn vị can thiệp là `trade_id × information_date`, không phải headline và không phải từng bar lặp lại. Nếu nhiều category cùng đạt điều kiện trong một trade-day, chúng được hợp nhất thành một action. Nếu shock đã available đúng lúc mở trade, entry vẫn giữ `w=1`; lần giảm exposure sớm nhất là mốc 4 giờ kế tiếp.

Audit feature-only theo timestamp chính xác, không đọc trade PnL, tìm thấy 23 trade-day đủ điều kiện trên 13 shadow trade trong vùng chồng lấp 2022-09-13 đến 2025-08-28. Hai slot của audit sơ bộ 25/14 bị loại vì `available_at` không nằm nghiêm ngặt bên trong lifecycle của shadow trade. Runner đã tái tạo và băm toàn bộ assignment trước evaluation.

## 5. Comparator, placebo và estimand

Comparator chính là frozen Tech-only replay với cùng shadow lifecycle. Treatment và comparator phải dùng cùng market bar, stop timestamp, funding, fee, slippage và risk budget.

Primary estimand là mean paired net PnL difference trên các intervention window 4 giờ. Resampling cluster theo `trade_id`; nếu số trade cluster dưới 10 hoặc số intervention dưới 20 thì kết quả là `insufficient-sample`, không phải FAIL hay PASS.

Các chỉ tiêu phụ gồm compounded net return toàn chiến lược, intrabar MDD, expected shortfall 10%, turnover, tổng chi phí overlay và opportunity cost. Chỉ tiêu phụ không được đảo kết luận primary.

Các đối chứng bắt buộc:

1. metadata-only với cùng mật độ action, xếp theo số domain rồi số headline nhưng bỏ direction/event type/severity/confidence;
2. shuffled trade-day, giữ nguyên mật độ action;
3. delayed-24h semantic shock;
4. single-source ablation để kiểm tra giá trị của điều kiện xác nhận đa nguồn;
5. frozen Tech-only.

Gate PASS đồng thời yêu cầu: đủ sample; cận dưới cluster-bootstrap CI 95% của paired net difference lớn hơn 0; paired gross mean lớn hơn 0; treatment dương ở ít nhất 2/3 fold thời gian; treatment vượt mọi placebo; và intrabar MDD không cao hơn Tech-only. Bootstrap dùng 10.000 draw, seed `20260909`.

## 6. Biên dữ liệu và quyền chạy

Trước khi evaluation phải khóa: runner hash; hash Tech-Control, market bars, funding, event output và extraction input; alias map; event allowlist; assignment; cost semantics; folds; placebo; bootstrap và gate. Freeze chỉ được đọc trade lifecycle/timestamp, event fields, source metadata và market timestamp; không được đọc PnL hoặc forward return.

Do outcome 2022–2025 đã được dự án xem, lần chạy đầu trên vùng này chỉ là exploratory development. Không mở sealed holdout cho HYB-002 trừ khi development PASS và có một vùng thời gian mới chưa dùng để thiết kế. Không được sửa allowlist, ngưỡng, action duration hoặc comparator sau evaluation rồi gọi kết quả mới là xác nhận.

## 7. Logic kết luận

PASS chỉ cho phép kết luận confirmed semantic shock shield đã đăng ký có incremental intratrade decision value so với Tech-only và placebo trong evaluation protocol. FAIL bác bỏ riêng kiến trúc HYB-002. `Insufficient-sample` chỉ cho biết thiết kế chưa có đủ effective sample. Không trạng thái nào chứng minh standalone LLM alpha hoặc hiệu quả live.

## 8. Kết quả exploratory development

Runner đã khóa 23 intervention trên 13 shadow trade. Mean paired net difference là `-0,0021577` (`-0,2158%`) mỗi cửa sổ, với cluster-bootstrap CI 95% `[-0,0037874; -0,0006255]`. Paired gross mean là `-0,0010282`; chỉ 1/3 fold có mean dương. Treatment vượt cả bốn placebo theo mean paired net, nhưng hiệu ứng primary mang dấu âm và CI hoàn toàn dưới 0. Compounded return trên overlap là `+223,68%`, thấp hơn `+239,00%` của Tech-only.

Do CI, gross và fold đều không đạt, HYB-002 nhận trạng thái FAIL mà không phụ thuộc vào gate MDD. [THIẾU] Runner chưa materialize intrabar MDD đúng protocol; closed-trade MDD được lưu trong artifact chỉ là proxy và không được dùng để hỗ trợ PASS. Không retune allowlist, threshold hoặc action duration trên cùng outcome.