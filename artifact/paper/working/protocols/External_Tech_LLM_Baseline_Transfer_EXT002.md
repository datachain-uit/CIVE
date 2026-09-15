# EXT-002 — Chuyển giao baseline Tech+LLM bên ngoài

> Khóa phạm vi ngày 2026-09-12 sau khi các outcome development của dự án đã được xem. Vì vậy EXT-002 là audit và evidence synthesis hậu nghiệm; nó không tạo validation hoặc sealed-holdout evidence mới.

## Mục tiêu

Xác định phương pháp Tech+LLM bên ngoài nào có thể chuyển giao hợp lệ lên dữ liệu dự án, tổng hợp kết quả của baseline được chấp nhận với Tech và các HYB nội bộ, đồng thời tách ưu thế protocol khỏi ưu thế hiệu năng.

## Quy tắc admission

Một external method được đưa vào performance comparison khi:

1. Có nguồn đã xác minh trong `paper/input/references/`.
2. Có thành phần kết hợp Tech và text/LLM được mô tả đủ để cài đặt mà không sáng tác thuật toán mới.
3. Có thể chạy với dữ liệu point-in-time hiện có hoặc được ghi rõ là proxy transfer.
4. Comparator, split, execution delay và cost được giữ nhất quán trong cùng testbed.
5. Nếu thiếu dữ liệu/mã/credential gốc, kết quả phải được gọi là transfer hoặc feasibility, không gọi là replication.

## Audit candidate

| Candidate | Phân loại | Admission | Lý do |
|---|---|---:|---|
| Bennett et al. (2024) adaptive recent-MSFE | External Tech+sentiment fusion component | Có | Quy tắc normalized inverse recent-MSFE chuyển được lên cùng ETH OOS panel; HYB-004 v1.1 là remediation hợp lệ để mô tả development transfer |
| FinMem | Memory-agent end-to-end | Không | Thiếu input `.pkl` và embedding credential; Stage 0 feasibility đã dừng |
| FinAgent | Multimodal agent end-to-end | Không | Dự án chỉ mượn nguyên tắc fusion/ablation; không có đủ implementation/data để tái lập cùng testbed |
| Jung & Lee (2026) | Multi-agent zero-shot trading | Không | Backtest gốc chỉ ba ngày và contract không tương thích với 699 ngày ETH OOS |
| Kirtac & Germano (2024) | LLM-only sentiment trading | Không cho bảng Tech+LLM | Là baseline LLM-only, không định nghĩa Tech+LLM fusion tương đương |

## Baseline được admission

EXT-002 không tạo thêm một external algorithm bằng suy diễn. Baseline duy nhất đủ điều kiện hiện tại là HYB-004 v1.1, chuyển giao thành phần adaptive recent-MSFE của Bennett et al. (2024). Kết quả canonical lấy trực tiếp từ artifact đã khóa.

Primary comparator là Tech ridge trên cùng 699 ngày ETH OOS. Fusion và Tech dùng cùng target 24 giờ, five-fold expanding OOS, delay 4 giờ, fee/adverse execution 11 bps một chiều và signed funding.

## Ba bảng đầu ra

1. `admissibility`: candidate, nguồn, lý do admission/exclusion và loại claim được phép.
2. `same_context_performance`: predictive loss, paired net delta, uncertainty, fold stability và risk metric khi có cùng comparator.
3. `protocol_and_regime_coverage`: causal timestamp, delay, walk-forward, cost/funding, sample gate, placebos, sealed status và việc có hay chưa có regime analysis predeclared.

Các HYB khác được trình bày như evidence map, không xếp hạng trực tiếp khi khác asset, population, horizon hoặc comparator. Ô thiếu được giữ là `null`, không nội suy.

## Quy tắc diễn giải

- Ưu thế protocol không được diễn giải thành ưu thế lợi nhuận.
- Kết quả dương về worst-bar/ES không đủ chứng minh incremental value nếu economic non-inferiority thất bại.
- Fold là kiểm tra ổn định theo thời gian, không đồng nghĩa với bull/bear/high-vol regime.
- Hiện chưa có regime comparison đã predeclare chung cho Bennett và các HYB. Phần này được đánh dấu `[THIẾU]`; không chọn hậu nghiệm các giai đoạn thắng.
- Kết luận EXT-002 hiện tại chỉ áp dụng cho development transfer đã chạy.

