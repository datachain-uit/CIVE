# LLM-only multi-coin risk transfer v19

## Câu hỏi và phạm vi

V19 kiểm tra liệu semantic event đã khóa từ extractor v3.9 có bổ sung thông tin dự báo rủi ro 24 giờ cho ETH, SOL, XRP hoặc BNB hay không. ETH và SOL là primary candidates; XRP và BNB chỉ được đánh giá nếu cùng vượt outcome-free sample gate. Đây là development transfer sau khi kết quả BTC v3.2, ETH v17 và v18 đã được biết; không phải validation hoặc holdout.

## Trình tự khóa

1. Khóa alias, candidate, bar-availability check và effective-sample thresholds trước target.
2. Audit chỉ identity/timestamp/output LLM; không đọc OHLC hoặc target values.
3. Chỉ asset đạt gate mới được khóa target/evaluator rồi tạo panel.
4. Chỉ khi primary predictive gate PASS mới được viết một protocol Tech risk overlay riêng để đo drawdown và cost. Predictive FAIL không được cứu bằng threshold hoặc backtest.

## Sample gate outcome-free

Mỗi asset cần ít nhất 1.000 direct-event record, 700 event-date, 100 event-date trong từng fold daily OOS, fallback dưới 5% và có file Bybit 4h đã khóa. Không hạ ngưỡng cho SOL hoặc conditional candidates.

## Targets và arms

Target chính là raw realized volatility 24 giờ sau execution delay 4 giờ, dùng đúng công thức v3.2. Secondary diagnostic là adverse-excursion magnitude `max(0, 1-min(low_path)/entry_open)` cùng cửa sổ. Không chọn target theo kết quả.

Ba predictive layers dùng cùng asset-selected events: `metadata` chỉ dùng count/source/recency/headline length; `generic` thêm direction/severity/confidence; `event` thêm surprise/event type/expected horizon. Vì asset selection dựa trên `affected_assets` của extractor, metadata là comparator điều kiện sau LLM asset selection, không phải no-LLM arm.

## Gate

Ridge alpha 10, train-fold standardization, năm expanding folds và paired moving-block bootstrap 5.000 lần/block 7 ngày. Primary per-asset gate yêu cầu: CI 95% lower của MSE(metadata)-MSE(event) dương; CI Pearson event lower dương; event thắng metadata ít nhất 3/5 fold; prediction không hằng. Family inference hiệu chỉnh Holm trên các asset đủ điều kiện. Secondary adverse excursion chỉ là diagnostic và không thể đảo primary FAIL.

PASS chỉ cấp quyền predeclare một Tech+LLM risk overlay mới. FAIL dừng trước threshold, action mapping, drawdown/cost backtest hoặc sealed holdout.

