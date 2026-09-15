# LLM-only multi-coin short-horizon transfer v20

## Câu hỏi và phạm vi

V20 chuyển thiết kế event-response v8 sang ETH, SOL, XRP và BNB. ETH/SOL là primary candidates; XRP/BNB chỉ được nối target nếu vượt cùng sample gate. Target duy nhất là open-to-open return 4 giờ tại open UTC kế tiếp nghiêm ngặt sau `published_at`. Đây là development transfer, không phải validation hoặc holdout.

## Outcome-free bucket screen

Chỉ event gắn trực tiếp với alias asset và thuộc tám catalyst type đã khóa; loại `market_commentary` và `other`; dedupe normalized headline theo lần xuất bản đầu tiên. Mỗi asset cần ít nhất 800 eligible event, 500 unique 4h bucket, 75 bucket trong từng validation fold và file bar 4h hiện hữu. Audit bucket không đọc giá hoặc target.

## Ba tầng thông tin

`metadata` dùng count/source/recency/headline length của event trong bucket. `generic LLM` thêm direction/severity/confidence. `event-conditioned LLM` thêm surprise/event type/expected horizon. Metadata vẫn điều kiện trên asset/event selection do LLM tạo, vì vậy estimand là giá trị tăng thêm của semantic fields sau selection.

## Evaluation và gate

Năm expanding fold calendar kế thừa v8, Ridge alpha 10, train-only standardization, paired moving-block bootstrap 5.000 lần/block 42 record. Event-conditioned chỉ PASS per asset khi đồng thời cải thiện cả metadata và generic LLM với CI lower của hai delta-MSE dương, CI Pearson lower dương, thắng cả hai comparator ít nhất 3/5 fold và prediction không hằng. Family p-value hiệu chỉnh Holm trên asset đủ điều kiện.

FAIL dừng trước threshold, action mapping, trading backtest hoặc sealed holdout. PASS chỉ cấp quyền thiết kế overlay development riêng.
