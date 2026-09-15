# Giao thức LLM contrastive market-impact v6

> Trạng thái: thiết kế development đã chọn sau khi v5 FAIL; chưa huấn luyện hoặc xem prediction v6. Đây không phải replication độc lập hoặc sealed confirmation.

## Câu hỏi nghiên cứu

V6 kiểm tra liệu supervised contrastive learning trên bucket representation full-text đã khóa ở v5 có tạo representation phù hợp hơn với BTC return 24 giờ hay không. V6 không đổi corpus, article selection, target, market features, folds hoặc comparator của v5.

## Input đã khóa

- Panel v5: 5.187 bucket 4 giờ, 36.828 article từ 58 source.
- Frozen MiniLM representation: mỗi bucket có vector 768 chiều từ mean và max pooling; encoder không chạy lại.
- Target duy nhất: raw Bybit BTCUSDT `open[t+24h] / open[t] - 1`.
- Market-only: bảy causal market feature của v5.
- OOS folds: ba expanding fold của v5, tổng cộng 2.177 validation bucket và purge ít nhất 24 giờ.

Kết quả v5 đã được xem trước khi thiết kế v6. Vì vậy mọi kết quả v6 chỉ mang trạng thái development evidence và không được dùng như sealed holdout.

## Supervised contrastive projection

Trong mỗi fold, hai ngưỡng 1/3 và 2/3 quantile của raw 24h return được tính chỉ từ training records. Mỗi training bucket nhận một trong ba lớp `down`, `middle`, `up`. Validation target không tham gia xây ngưỡng hoặc huấn luyện.

Projection MLP cố định:

1. Linear `768 → 128`.
2. GELU.
3. Linear `128 → 32`.
4. L2 normalization.

Loss là supervised contrastive loss: các bucket cùng lớp return là positive, bucket khác lớp là negative. Temperature `0,1`; AdamW learning rate `0,001`, weight decay `0,0001`; batch size 256; 20 epoch; không dropout, scheduler, early stopping hoặc hyperparameter search. Input embedding được chuẩn hóa theo mean/std của training fold. CPU deterministic seed `20260906 + fold`.

Sau huấn luyện projection, Ridge `alpha=100` học raw return trên vector 32 chiều. Ba arm:

1. `market-only`: bảy market feature, Ridge `alpha=100`.
2. `contrastive-only`: 32 chiều projection, Ridge `alpha=100`.
3. `market+contrastive`: nối bảy market feature với 32 chiều projection, Ridge `alpha=100`.

Mọi standardization và model fit chỉ dùng training fold.

## Gate

Moving-block bootstrap dùng block 42 record, 5.000 lần, seed `20260906`. `market+contrastive` chỉ PASS nếu đồng thời:

- cận dưới CI 95% của `MSE(market-only)-MSE(market+contrastive)` lớn hơn 0;
- cận dưới CI 95% Pearson của prediction `market+contrastive` lớn hơn 0;
- `market+contrastive` thắng market-only ít nhất 2/3 fold;
- có đúng 2.177 OOS prediction và prediction không hằng.

`contrastive-only` là diagnostic, không thay thế comparator chính.

## Stop rule

Nếu FAIL, khóa kết quả âm và dừng v6 trước threshold, action mapping, backtest, `Tech+LLM` hoặc sealed holdout. Không đổi classes, architecture, temperature, optimizer, epoch, Ridge alpha, target hoặc folds để chạy lại v6.

Nếu PASS, quyền duy nhất được mở là viết một overlay development predeclaration riêng. PASS không tự động chứng minh hiệu quả giao dịch hoặc khả năng chạy live.
