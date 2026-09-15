# LLM-only multi-coin transfer v18

## Phạm vi

V18 áp dụng nguyên thiết kế LLM-only ETH v17 cho BTCUSDT, XRPUSDT, SOLUSDT và BNBUSDT. ETH v17 là kết quả development đã xem và chỉ đóng vai trò mô tả; không được tính như một test mới trong family. Bốn experiment lần lượt là LLM-073, LLM-074, LLM-075 và LLM-076. Đây là development transfer dùng lại frozen extractor v3.9, không phải validation, holdout hoặc đánh giá model local mới.

## Screen outcome-free

Alias được khóa trước audit: BTC là Bitcoin/BTC; XRP là XRP/Ripple; SOL là SOL/Solana; BNB là BNB/Binance Coin. Mỗi coin phải có ít nhất 1.000 direct-event record, 700 event-date, 100 event-date trong từng fold OOS và evidence fallback dưới 5%. Audit chỉ đọc identity, timestamp và output extractor; không đọc giá hoặc target. Coin fail dừng trước target. Không hạ ngưỡng theo từng coin.

## Evaluation family

Coin pass screen dùng target open-to-open 24 giờ, entry sau cutoff 4 giờ, cùng năm expanding fold của v17. Ba arm là train-mean prior, generic LLM-only và event-conditioned LLM-only. Ridge alpha 10, chuẩn hóa trong train và không tuning. Bootstrap theo từng fold dùng 5.000 lần, block 7 ngày và seed cố định theo coin.

Per-coin gate giữ nguyên v17: cận dưới CI 95% của MSE(generic)-MSE(event) dương, cận dưới CI Pearson event dương, event thắng ít nhất 3/5 fold và prediction không hằng. Family inference dùng one-sided bootstrap p-value có hiệu chỉnh Holm riêng cho delta-MSE và Pearson trên toàn bộ coin đủ điều kiện. Family chỉ xác nhận transfer nếu ít nhất một coin đồng thời có hai Holm-adjusted p-value dưới 0,05 và đạt fold/nonconstant gate.

Không chạy action mapping hoặc backtest cho coin fail. Không chọn riêng coin thắng để bỏ qua family correction. Kết quả không trả lời trực tiếp LLM có cải thiện Tech; nó chỉ kiểm tra predictive information của representation LLM trên từng coin.
