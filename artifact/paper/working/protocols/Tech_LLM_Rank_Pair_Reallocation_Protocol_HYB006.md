# HYB-006 persistent rank-pair reallocation

## Vai trò nghiên cứu

HYB-006 là thiết kế mới sau khi HYB-005 dừng vì baseline entry-gated chỉ có 57 ngày giữ hai vị thế. HYB-006 không hạ gate và không tái sử dụng kết quả hiệu năng của HYB-005. Thay vào đó, thiết kế định nghĩa một estimand khác: Tech tạo cặp hai tài sản liên tục bằng rank momentum 20 ngày; LLM chỉ kiểm tra khả năng phân bổ tương đối bên trong cặp đó. Đây là exploratory transfer diagnostic, không phải Tech-Control canonical, validation, holdout hoặc bằng chứng live.

## Policy khóa trước audit

Universe cố định gồm BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT và BNBUSDT. Tại close ngày `t`, Tech xếp hạng `close_t / close_{t-20} - 1`, chọn hai asset cao nhất và phá hòa theo ticker tăng dần. Tech-only giữ mỗi asset 0,5. Signed event score theo asset dùng nguyên extractor v3.9 và công thức `max positive strength - max negative strength`, trong đó strength bằng `severity × confidence × (0,5 + 0,5 × reported_surprise)`.

Với cặp sắp theo ticker, LLM đặt `w_1 = clip(0,5 + 0,25 × (score_1-score_2), 0,25, 0,75)` và `w_2 = 1-w_1`. LLM không đổi selected set và gross exposure bằng một. Gate trước target yêu cầu ít nhất 1.000 pair-day, 600 active day, 150 active day trong mỗi chronological third và mỗi asset được chọn ít nhất 50 ngày.

## Evaluation khóa trước khi đọc target

Nếu gate mẫu PASS, target là simple return từ close ngày `t` tới close ngày `t+1`. Turnover ngày đầu bằng tổng trị tuyệt đối trọng số; các ngày sau bằng một nửa L1 giữa hai vector target-weight liên tiếp. Chi phí là 10 bps trên mỗi đơn vị turnover. Primary contrast là daily net return của LLM trừ Tech equal-weight.

Bootstrap moving-block 7 ngày, 5.000 lần với seed 20260912 tạo CI 95% cho paired mean. Năm chronological fold kiểm tra ổn định. Ba placebo đã khóa là đảo dấu score, trễ một ngày và hoán vị tilt bằng seed cố định. HYB-006 chỉ PASS nếu cận dưới CI của mean net delta lớn hơn 0, ít nhất 3/5 fold có delta dương, mean net return primary vượt cả ba placebo và MDD của LLM không xấu hơn Tech quá 5 điểm phần trăm.

Không thay threshold, feature, cost, placebo hoặc pass rule sau khi audit/evaluation. Nếu gate mẫu FAIL thì dừng trước target. Nếu performance gate FAIL thì giữ kết quả âm và không retune trên cùng outcome.
