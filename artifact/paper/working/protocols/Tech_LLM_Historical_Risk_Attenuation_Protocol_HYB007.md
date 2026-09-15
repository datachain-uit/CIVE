# HYB-007 historical event-risk attenuation

> Trạng thái: frozen historical development transfer. Thiết kế được khóa trước khi tính outcome riêng của HYB-007, nhưng dữ liệu 2022--2025 và kết quả các thí nghiệm trước đã được xem; do đó đây không phải prospective, validation, holdout hoặc live evidence.

## 1. Câu hỏi và comparator

HYB-007 kiểm tra **conditional incremental value**: trong những thời điểm một baseline kỹ thuật đang nắm exposure, thông tin sự kiện do LLM cấu trúc có giảm rủi ro với chi phí chấp nhận được hay cải thiện return sau chi phí hay không. Kết quả LLM-only v20 âm không quyết định câu hỏi này vì v20 kiểm tra dự báo return 4 giờ trên toàn bộ event bucket, còn HYB-007 kiểm tra một quyền hạn hẹp bên trong trạng thái Tech.

- `T0`: predecessor Tech rank-pair của HYB-006, chọn top-2 theo momentum 20 ngày và phân bổ 0,5/0,5.
- `T1`: giữ nguyên asset selection của T0. Khi asset đang được T0 chọn và có cảnh báo đủ điều kiện, trọng số asset đó giảm từ 0,5 xuống 0,25; 0,25 còn lại chuyển sang cash trong ba nến 4 giờ.
- LLM không chọn coin, không tạo exposure, không đảo chiều và không tăng exposure. Nếu Tech bỏ chọn asset thì cả T0 và T1 đều đưa trọng số asset đó về 0.

Đây là transfer trên historical data, không thay thế Tech-Control canonical của luận văn.

## 2. Dữ liệu và timing

- Asset có event panel 4 giờ đủ sample theo v20: ETHUSDT và SOLUSDT.
- Event feature lấy từ frozen Ministral v3.9 qua panel v20. Trường `target_h4_return` của v20 bị cấm trong sample audit HYB-007.
- Tech selection lấy từ assignment HYB-006 đã materialize. Selection của information date `d` chỉ có hiệu lực từ UTC day `d+1`.
- Return dùng open-to-open 4 giờ: action tại `decision_at=t` áp dụng cho `open(t+4h)/open(t)-1`.

Cảnh báo primary thỏa đồng thời: negative fraction `>=0,5`, maximum severity `>=0,7`, maximum confidence `>=0,8`, và có ít nhất một event thuộc `exchange_security`, `fraud_legal`, `network_protocol`, `liquidation_leverage`. Các trigger cùng asset cách nhau không quá 24 giờ thuộc một cluster.

## 3. Effective-sample gate trước evaluation

Audit không được đọc `target_h4_return`, giá sau decision time hoặc PnL. Gate yêu cầu:

- ít nhất 120 qualifying selected-asset bucket;
- ít nhất 60 independent cluster;
- ít nhất 15 cluster trong mỗi chronological third;
- ETH và SOL mỗi asset có ít nhất 20 cluster;
- độ phủ từ cluster đầu tới cuối ít nhất 720 ngày;
- toàn bộ decision time khớp causal Tech selection.

Nếu gate FAIL, dừng trước evaluation; không hạ ngưỡng.

## 4. Estimand và hai dạng incremental value

Mỗi cluster được đánh giá từ trigger đầu đến 12 giờ sau trigger cuối. `T0` giữ trọng số 0,5 khi asset còn được Tech chọn; `T1` dùng 0,25 trong ba bar sau mỗi trigger. Cost là 10 bps trên one-way turnover, gồm cả chuyển sang/về cash.

Hai kết luận được tách riêng:

1. **Economic increment**: mean cluster net delta `T1-T0` có cận dưới bootstrap CI 95% lớn hơn 0, dương ở ít nhất 3/5 chronological fold và vượt ba placebo.
2. **Risk-control increment**: cận dưới CI 95% của cải thiện worst-bar contribution lớn hơn 0; ES10% cluster của T1 tốt hơn T0; cận dưới CI mean net delta không thấp hơn `-0,0005` (mức dung sai bằng một round-trip attenuation 5 bps); và cải thiện worst-bar trung bình vượt ba placebo.

Như vậy LLM có thể đem lại incremental value bằng giảm tail/adverse loss với chi phí giới hạn, ngay cả khi không làm mean return cao hơn. Hai claim phải báo riêng, không được gọi risk-control PASS là alpha.

Bootstrap resample 10.000 cluster với seed 20260913. Ba placebo là cảnh báo trễ 24 giờ, cảnh báo positive cùng threshold và deterministic hash-matched trigger. Kết quả chỉ là exploratory historical transfer trên comparator này.
