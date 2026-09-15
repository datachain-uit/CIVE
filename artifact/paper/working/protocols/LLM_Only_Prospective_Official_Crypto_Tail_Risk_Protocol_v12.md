# Protocol LLM-only prospective official crypto tail-risk v12

> Trạng thái: DỪNG trước corpus admission. Collector prospective đã khởi tạo lúc 2026-09-05T17:36:59.128472+00:00 nhưng automation đã pause vì hướng crawl không đáp ứng mục tiêu dataset lịch sử có thể tái lập độc lập bởi reviewer. Có 0 record admitted, không có market outcome, LLM inference, predictive result, action mapping, backtest hoặc quyền mở Tech+LLM. Artifact v12 chỉ là nhật ký quyết định thiết kế, không dùng cho thực nghiệm tiếp theo.

## 1. Quyết định nghiên cứu

V12 kiểm tra một câu hỏi khác v3--v11: liệu văn bản của thông cáo quản lý chính thức, được thu thập **prospective** tại thời điểm xuất hiện và có nội dung crypto-specific, có dự báo được rủi ro tổn thất đuôi BTCUSDT trong bốn giờ kế tiếp hay không. Đây là bài toán nhận diện rủi ro, không phải dự báo chiều return hay tối ưu lợi nhuận.

Lý do chọn hướng này là hai ràng buộc còn bỏ ngỏ trong các nhánh trước: provenance lịch sử của corpus tin không chứng minh strict PIT, và nhãn return hướng có thể không phù hợp với thông tin quản lý bất lợi. V12 khắc phục ràng buộc thứ nhất bằng thu thập prospective; giả thuyết thứ hai chỉ được kiểm tra qua gate đã định dưới đây, không được mặc định đúng.

Nguồn được phép trước khi có amendment là:

- SEC Press Releases RSS, từ trang newsroom chính thức của SEC.
- CFTC General Press Releases RSS và Enforcement Press Releases RSS, từ trang RSS chính thức của CFTC.

Danh mục nguồn này được chọn vì hai cơ quan cung cấp feed chính thức về thông cáo và enforcement. Không thêm DOJ, nguồn báo chí, mạng xã hội, trang tổng hợp hoặc API bên thứ ba trong v12. Mọi thay đổi nguồn, từ khóa, target, horizon, model, fold hay điều kiện gate tạo ra phiên bản protocol mới; không sửa v12 sau khi collector bắt đầu.

## 2. Tách biệt hoàn toàn với v11

V12 không được dùng bất kỳ dữ liệu hay kết quả v11 nào làm input, nhãn, feature, bộ lọc, định nghĩa source, từ khóa, cửa sổ, fold, hyperparameter, ngưỡng hay điều kiện mở treatment. Điều cấm này bao gồm corpus Federal Reserve, event ID, LLM output, panel, prediction, metric, bootstrap draw và failure artifact của v11.

Kết quả v11 chỉ được nêu trong lịch sử nghiên cứu như một development result âm. Nó không phải bằng chứng pass, không phải calibration set và không cấp quyền cho Tech+LLM. V12 cũng không được xem là sealed confirmation của các nhánh trước.

## 3. Thu thập prospective và admission corpus

Collector bắt đầu từ thời điểm protocol được đóng băng. Mỗi lần poll, collector lưu nguyên XML/HTTP body, URL feed, thời điểm bắt đầu/kết thúc truy xuất UTC, HTTP status, header nhận được và SHA-256 của body. Với mỗi item mới, collector tải trang thông cáo ngay trong cùng lượt, lưu raw response, URL chuẩn hóa, thời điểm capture, SHA-256 và text chuẩn hóa. `available_at` bằng thời điểm capture thành công đầu tiên, không suy ra từ ngày hiển thị trên trang.

Không backfill bất kỳ thông cáo nào xuất hiện trước khi collector bắt đầu. Một record bị loại khi thiếu text, thiếu URL, không có body hợp lệ, không có capture timestamp, trùng URL chuẩn hóa, hoặc không có thời điểm công bố với độ chính xác phút/giây trong raw item hay raw release page. Record giữ `published_at` nếu có, nhưng chỉ `available_at` được dùng để căn chỉnh nhãn.

Một record chỉ được gọi là crypto-specific khi title hoặc body raw có ít nhất một cụm trong allowlist đóng sau, không phân biệt hoa thường: `crypto asset`, `crypto-asset`, `cryptocurrency`, `digital asset`, `digital-asset`, `virtual currency`, `bitcoin`, `ether`, `stablecoin`, `blockchain`, `token`, `decentralized finance`, `DeFi`, `exchange token`, `custody of crypto`. Việc match được ghi theo từng cụm; LLM không được quyết định admission. Các thông cáo có cùng canonical URL là một record; các thông cáo khác URL được giữ riêng, kể cả khi cùng ngày.

Trước inference, corpus admission gate phải xác nhận: toàn bộ record có raw feed và raw release SHA-256; `available_at` có timezone UTC; text có thể tái tạo từ raw release; không record nào được backfill; và manifest có hash của mã collector, allowlist, môi trường chạy và corpus. Nếu một điều kiện không đạt, dừng ở corpus audit; không sửa record thủ công và không chạy LLM.

## 4. Input LLM và extraction gate

Input dự báo chỉ là text của thông cáo đã admitted. Không dùng giá, return trễ, OHLCV, funding, open interest, volume, volatility, thời điểm trong ngày, nguồn, cơ quan, độ trễ thu thập hoặc metadata khác làm feature. Các metadata chỉ dùng cho audit, grouping và căn chỉnh target.

Mỗi output bắt buộc có `event_id`, `generic_direction` trong [-1, 1], `generic_intensity` trong [0, 1], `tail_risk_pressure` trong [0, 1], `containment` trong [0, 1], `crypto_market_scope` thuộc {direct, systemic, indirect}, `event_type` thuộc {enforcement, rule_or_guidance, litigation, market_structure, operational, other}, `confidence` trong [0, 1] và một `evidence_span` liên tục là substring nguyên văn. `tail_risk_pressure` nghĩa là mức độ văn bản mô tả một cú sốc có thể làm tăng xác suất tổn thất lớn trong horizon đã định; nó không là forecast giá hoặc action.

Model, digest, prompt, schema, temperature bằng 0, seed, context limit, một worker và postprocessor deterministic phải được predeclare trước Stage 1. Stage 1 lấy mẫu 60 record đã admitted, phân tầng theo cơ quan và loại sự kiện do rule-based title match. Hai run phải đạt đủ schema/count/order/ID/evidence exact-substring ở 60/60 record. Các trường phân loại phải khớp tuyệt đối; mọi trường liên tục phải khớp tuyệt đối. Một lỗi không thể xác minh kích hoạt fail-fast và chỉ cho phép một protocol/extraction version mới chạy lại từ đầu.

## 5. Nhãn, arm và time-OOS gate

Target chỉ được tạo sau khi một record đã admitted. Với mỗi event, $r_{4h}$ là log return BTCUSDT từ open của nến UTC bốn giờ đầu tiên nằm nghiêm ngặt sau `available_at` đến open của nến bốn giờ kế tiếp. Mỗi event tạo một nhãn riêng; các event có cùng nến target không được coi là độc lập. Khi có nhiều event cùng target bucket, evaluation phải aggregate prediction và label theo bucket trước bootstrap.

Tail label trong mỗi train fold là $1$ khi $r_{4h}$ không lớn hơn phân vị 10% của $r_{4h}$ trong chính train fold; các quantile chỉ dùng target train. Không có ngưỡng loss tuyệt đối, thông tin market contemporaneous hay feature kỹ thuật đi vào arm dự báo.

Ba arm khóa trước:

- Prior: tần suất tail trong train fold.
- Generic: logistic ridge chỉ trên `generic_direction`, `generic_intensity` và `confidence`.
- Tail-conditioned: logistic ridge trên `tail_risk_pressure`, `containment`, `crypto_market_scope`, `event_type` và `confidence`.

Mọi chuẩn hóa, one-hot encoding và regularization được fit chỉ trên train fold. Giá trị regularization là 1.0; không có hyperparameter sweep. Split là năm fold expanding theo thứ tự `available_at`; boundary được lập chỉ từ timestamp trước khi bất kỳ target, output LLM hoặc metric nào được đọc. Bootstrap moving-block theo target bucket được khóa trước evaluation.

Predictive gate không được chạy cho đến khi có tối thiểu 100 bucket OOS và tối thiểu 20 tail bucket OOS; mỗi test fold phải có ít nhất ba tail bucket. Nếu chưa đủ, collector tiếp tục và không báo cáo metric predictive. Khi đủ điều kiện, Tail-conditioned chỉ PASS nếu đồng thời:

1. cận dưới CI 95% của Brier-score improvement so với Prior lớn hơn 0;
2. cận dưới CI 95% của Brier-score improvement so với Generic lớn hơn 0;
3. cận dưới CI 95% của AUROC lớn hơn 0,5; và
4. Tail-conditioned thắng cả Prior lẫn Generic về Brier score ở ít nhất ba trong năm fold.

PASS là bằng chứng development time-OOS cho một score rủi ro; không là alpha, causal claim hay bằng chứng live.

## 6. Quy tắc dừng và đường đi sang Tech+LLM

Nếu corpus admission hoặc extraction gate FAIL, dừng trước prediction. Nếu predictive gate FAIL, đóng băng artifact âm và dừng trước selection threshold, risk overlay, backtest hoặc sealed holdout. Không đổi quantile, horizon, source, lexicon, schema hay arm sau khi đọc outcome.

Nếu predictive gate PASS, chỉ được viết một amendment riêng cho **development risk overlay**. Amendment đó phải khóa cách `Tech+LLM` giảm exposure hoặc đứng ngoài thị trường khi tail score cao, giữ nguyên Tech-Control ở universe, calendar, execution, cost và risk khác, rồi đánh giá paired `Tech+LLM - Tech-Control`. Không có quy tắc action hay backtest nào được suy ra trực tiếp từ protocol v12. Sealed holdout vẫn cần một freeze protocol độc lập sau development.

## 7. Artifact bắt buộc

Mỗi stage phải ghi manifest và SHA-256 cho raw feed, raw release, normalized corpus, allowlist, source registry, collector code, model digest, prompt/schema, sample Stage 1, output, target panel, fold map, predictions, bootstrap draws và gate result. Artifact phải ghi rõ trạng thái `prospective`, khoảng thời gian capture, số record bị loại theo lý do và mọi gián đoạn collector. Thiếu artifact là FAIL, không được thay bằng mô tả trong hội thoại hoặc bản thảo.
