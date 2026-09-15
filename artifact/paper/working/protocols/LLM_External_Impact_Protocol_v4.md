# Giao thức LLM external market-impact v4

> Trạng thái: Stage A external market-impact đã FAIL trên 97 article OOS. Stop rule đã kích hoạt trước project corpus scoring; Stage B, threshold/action, backtest và sealed holdout không được phép.

## Phạm vi và động cơ

Event-vector v3.9 đã fail incremental predictive gate cho `h24_return` và raw `h24_realized_volatility`. V4 là nhánh representation mới, không sửa hậu kiểm event-vector: dùng dense embedding giữ nhiều thông tin ngữ nghĩa hơn và supervision market-impact từ một corpus ngoài. Kết quả v3 đã được biết khi thiết kế v4; v4 chỉ là development transfer test và không khôi phục tính sealed của development panel.

Nguồn ngoài là repository `SahandNZ/cryptonews-articles-with-price-momentum-labels` tại commit `2915946457bcf0604563b63d933d63313e71aeb2`. Code nguồn tạo nhãn nhị phân bằng `close[t+7 ngày] > close[t]` trên BTCUSDT daily. Dataset public đã tách title và paragraph thành 180.345 dòng nhưng chỉ có 480 URL và bốn URL xuyên split; do đó không dùng split hoặc row-level metric của nguồn.

## Representation và chống leakage

- Regroup toàn bộ dòng theo normalized URL. Mỗi URL phải có đúng một ngày và một label.
- Giữ tối đa tám text chunk duy nhất theo thứ tự xuất hiện: title và tối đa bảy đoạn tiếp theo.
- Encoder duy nhất là frozen `sentence-transformers/all-MiniLM-L6-v2`, revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, local-files-only, `max_length=128`.
- Mỗi chunk dùng attention-mask mean pooling rồi L2 normalization. Article embedding là trung bình các chunk embedding rồi L2 normalization.
- Không fine-tune encoder, không xem target dự án trong Stage A và không dùng row-level split của nguồn.
- External corpus kết thúc 2023-05-31; label cuối hoàn tất sau bảy ngày, trước validation OOS đầu tiên của dự án ngày 2023-09-15. URL audit phải xác nhận không trùng corpus dự án.

## Stage A: external supervision gate

Linear Ridge head dự báo binary 7-day BTC direction từ 384 chiều embedding, `alpha=10`, chuẩn hóa bằng mean/std của training fold.

Hai expanding folds ở cấp ngày/article:

1. Train 2022-10-14 đến 2023-03-13, 383 article; validation 2023-03-15 đến 2023-04-21, 43 article.
2. Train đến 2023-04-21, 426 article; validation 2023-04-24 đến 2023-05-31, 54 article.

Uncertainty dùng paired date-cluster bootstrap trong từng fold, 5.000 lần, seed `20260904`. Stage A PASS chỉ khi đủ 97 OOS article, AUC tổng thể có cận dưới CI 95% lớn hơn 0,5, chênh lệch mean score giữa label 1 và 0 có cận dưới CI 95% lớn hơn 0, cả hai fold có AUC lớn hơn 0,5 và prediction không hằng.

Nếu Stage A FAIL, dừng v4 trước khi score corpus dự án. Nếu PASS, refit cùng Ridge head trên toàn bộ 480 article; không tuning.

## Stage B: transfer gate trên dự án

Head đã refit tạo đúng một impact score cho mỗi trong 39.393 headline frozen. Daily impact vector gồm mean, max, min, standard deviation và mean absolute score trên các headline còn lại sau quy tắc normalized-headline dedupe v3.

Ba nhánh dùng cùng folds và model downstream:

1. `market-only`: 11 market/funding/breadth features v3.
2. `metadata-only`: market-only cộng 28 deterministic metadata features v3.
3. `external-impact`: metadata-only cộng năm daily impact-score features.

Target chính duy nhất vẫn là raw `h24_return`; không đổi horizon sau kết quả v3. Downstream dùng năm expanding folds, purge 72 giờ, Ridge `alpha=10`, 699 prediction OOS và paired moving-block bootstrap 7 ngày, 5.000 lần, seed `20260904`.

Stage B PASS chỉ khi cận dưới CI 95% của `MSE(metadata-only)-MSE(external-impact)` lớn hơn 0, cận dưới CI 95% Pearson của impact prediction lớn hơn 0, external-impact thắng metadata-only ít nhất 3/5 fold, đủ 699 OOS record và prediction không hằng.

Nếu Stage B FAIL, khóa kết quả âm và dừng trước threshold/action/backtest. Nếu PASS, quyền duy nhất được mở là predeclare overlay trên development data; chưa được xem sealed holdout hoặc claim hiệu quả giao dịch.

## Cấm thay đổi sau predeclaration

- Không đổi encoder, số chunk, pooling, label, target, horizon, folds, alpha, feature aggregation hoặc gate threshold.
- Không dùng external validation/test để tuning.
- Không thử encoder hoặc target khác nếu một stage fail.
- Không chạy threshold, action mapping, backtest, `Tech+LLM` hoặc sealed holdout trước khi cả hai stage PASS.

## Kết quả Stage A

MiniLM đã encode 3.718 chunk được chọn từ 480 URL. Hai fold tạo 97 prediction OOS ở cấp article. Fold 1 có AUC 0,64516 nhưng fold 2 giảm còn 0,37647; AUC gộp bằng 0,41731 với CI 95% [0,30409; 0,53459]. Score separation giữa label 1 và 0 bằng -0,17456 với CI 95% [-0,39492; 0,04003].

Stage A chỉ đạt điều kiện đủ record và prediction không hằng; ba điều kiện về AUC, separation và tính nhất quán giữa fold đều fail. Không project headline nào được score, evaluator không đọc target panel của dự án và Stage B không chạy.
