# HYB-008 conditional downside information gate

> Trạng thái ban đầu: historical post-outcome development. Thiết kế được khóa trước khi tính outcome HYB-008, nhưng kết quả HYB-001--007 và v20 đã được xem; không phải validation, holdout hoặc live evidence.

## 1. Câu hỏi

HYB-008 không bắt đầu bằng một luật giao dịch. Stage A hỏi: **khi Tech rank-pair đang chọn ETH hoặc SOL, event semantics của LLM có dự báo tail loss 4 giờ tốt hơn Tech-state-only, Tech+metadata và Tech+generic LLM hay không?** Thiết kế này phân biệt semantic risk recognition với hiệu ứng cơ học “giảm exposure thì giảm loss” đã thấy ở HYB-007.

Nếu Stage A FAIL, HYB-008 dừng trước policy/backtest. Nếu PASS, một Stage B riêng mới được phép freeze cost-aware intervention; Stage A PASS vẫn chưa phải economic incremental value.

## 2. Population và timing

- Population: event bucket v20 của ETHUSDT/SOLUSDT tại `decision_at` mà predecessor Tech rank-pair của HYB-006 đã chọn đúng asset.
- Tech selection của information date `d` chỉ có hiệu lực trong UTC day `d+1`.
- Market feature chỉ dùng open tại `decision_at` và open quá khứ; không dùng high/low/close của bar đang hình thành.
- Target là indicator `next_4h_return <= q10_asset(training fold)`. Tail threshold được ước lượng riêng theo asset chỉ từ training của từng fold.

## 3. Bốn arm

- `T0 tech`: asset dummy, thứ hạng trong cặp Tech, open momentum 1/6/18 bar, realized volatility 6/18 bar và drawdown 18 bar.
- `Tm tech_metadata`: T0 + event count, recency, headline length và source fractions.
- `Tg tech_generic`: T0 + toàn bộ generic LLM direction/severity/confidence, đồng thời giữ metadata.
- `Te tech_event`: Tg + reported surprise, event-type fractions và expected-horizon fractions.

Mỗi arm là logistic regression L2, `C=1`, solver `lbfgs`, tối đa 2.000 iteration. StandardScaler chỉ fit trên training fold. Không tuning hyperparameter.

Negative control `event_permuted` dịch vòng toàn bộ semantic-only vector 17 hàng theo thứ tự thời gian trong từng train/test fold; Tech, metadata, generic, target và timestamp giữ nguyên.

## 4. Sample gate không outcome

Trước target, audit yêu cầu ít nhất 900 selected event row, ETH >=500, SOL >=300, mỗi chronological third >=250, ít nhất 400 UTC date và ít nhất 95% hàng có đủ 18 bar lịch sử. Nếu FAIL thì dừng, không hạ gate.

## 5. Expanding evaluation và gate

Sắp theo UTC date. 30% date đầu là initial train; 70% còn lại chia năm test block liên tiếp. Mỗi fold chỉ train trên date trước test block. Resampling dùng UTC date cluster, 10.000 bootstrap draw, seed 20260914.

Stage A chỉ PASS nếu đồng thời:

1. cận dưới CI95 của paired Brier improvement `Tg - Te` lớn hơn 0;
2. Brier OOS của Te thấp hơn T0, Tm, Tg và event_permuted;
3. Te có Brier tốt hơn Tg ở ít nhất 3/5 fold;
4. ROC-AUC Te lớn hơn ROC-AUC Tg;
5. prediction Te không hằng và mọi fold có cả hai lớp.

FAIL chỉ bác bỏ incremental downside information dưới representation/model/population này. PASS chỉ cấp quyền thiết kế Stage B; không tự động chứng minh return, risk-adjusted performance hay live value.
