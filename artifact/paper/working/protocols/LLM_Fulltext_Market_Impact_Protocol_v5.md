# Giao thức LLM full-text market-impact v5

> Trạng thái: thiết kế development đã chọn sau data audit, chưa encode hoặc xem kết quả predictive v5. Kết quả v3/v4 đã biết nên v5 không phải sealed confirmation.

## Câu hỏi nghiên cứu

V5 kiểm tra liệu representation từ nội dung bài viết dài, học trực tiếp với BTC return 24 giờ ở cùng nhịp quyết định 4 giờ, có tạo giá trị tăng thêm so với market-only hay không. V5 không sửa threshold hoặc thử lại representation v4 trên cùng 480 article.

## Dữ liệu và đơn vị mẫu

Corpus cố định tại revision Hugging Face `d7bbdb7360291a81328d121080102f86258139b9`, SHA-256 file `d17b24d672c6e343ce43e267c2ab5c37438edbb88004d8548e626ba28bd2339c`. Audit ghi nhận 229.172 row, 228.995 article identity, 79 source và 11.278 bucket 4 giờ từ 29-10-2019 đến 01-02-2025.

Chỉ giữ article có body ít nhất 50 từ và identity URL/guid/id chưa xuất hiện. Publication timestamp được làm tròn lên **strictly** tới UTC 4h open kế tiếp. Trong mỗi bucket, chọn tối đa tám article theo thứ tự: BTC category/keyword relevance giảm dần, ưu tiên source chưa được chọn, sau đó publication time và article ID. Không dùng upvote, downvote, `last_update`, market outcome hoặc LLM annotation để chọn bài.

BTC market data là file Bybit 4h đã dùng trong Tech-Control. Sau selection và yêu cầu đủ 30 ngày lịch sử causal, panel có 5.187 bucket, 36.828 article được chọn từ 58 source, phủ `2022-09-12T00:00:00Z` đến `2025-02-02T00:00:00Z`.

Target duy nhất là raw `h24_return = open[t+24h] / open[t] - 1`, trong đó mọi article của bucket đã xuất bản trước `t`. Market-only dùng bảy đặc trưng causal tại `t`: return 4h/24h/72h/168h, realized volatility 24h/168h và z-score volume bar đã hoàn tất trên 30 ngày.

## Representation

Encoder cố định `sentence-transformers/all-MiniLM-L6-v2` revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`; không fine-tune encoder. Input là `title + body`, tối đa 256 token. Mỗi article dùng attention-mask mean pooling rồi L2 normalize. Bucket vector nối hai vector 384 chiều: L2-normalized mean pooling và L2-normalized elementwise max pooling trên article đã chọn. Không đổi encoder, token limit, article limit hoặc pooling sau khi xem outcome.

## Mô hình và folds

Ba arm dùng Ridge `alpha=100`, chuẩn hóa chỉ trên training fold, không tune hyperparameter:

1. `market-only`: bảy market feature.
2. `text-only`: 768 chiều full-text bucket embedding.
3. `market+text`: nối market-only với text-only.

Ba expanding fold, purge ít nhất 24 giờ:

| Fold | Train đến | Validation | Train | Validation |
|---|---|---|---:|---:|
| 1 | 31-12-2023 20:00 UTC | 02-01-2024 00:00 đến 30-04-2024 20:00 | 2.799 | 720 |
| 2 | 30-04-2024 20:00 UTC | 02-05-2024 00:00 đến 31-08-2024 20:00 | 3.525 | 732 |
| 3 | 31-08-2024 20:00 UTC | 02-09-2024 00:00 đến 31-12-2024 20:00 | 4.263 | 725 |

Tổng cộng phải có đúng 2.177 prediction OOS. Moving-block bootstrap dùng block 42 record, 5.000 lần, seed `20260905`.

## Stop gate

`market+text` chỉ PASS khi đồng thời:

- cận dưới CI 95% của `MSE(market-only)-MSE(market+text)` lớn hơn 0;
- cận dưới CI 95% Pearson giữa prediction `market+text` và target lớn hơn 0;
- `market+text` có MSE thấp hơn `market-only` trên ít nhất 2/3 fold;
- đủ 2.177 OOS record và prediction không hằng.

`text-only` là diagnostic đã đăng ký, không thay thế comparator chính. Nếu gate FAIL, khóa kết quả âm và dừng trước threshold, action mapping, backtest, `Tech+LLM` hoặc sealed holdout. Nếu PASS, quyền duy nhất được mở là thiết kế overlay development mới có predeclaration riêng.

## Cấm thay đổi

- Không chọn lại minimum word count, article cap, source, date, target, horizon, pooling, alpha, folds hoặc gate sau kết quả.
- Không thử encoder, fine-tuning, target hay horizon khác trong v5 nếu gate FAIL.
- Không gọi dữ liệu 2024 là sealed holdout; đây là OOS nội bộ của một nhánh development mới.
