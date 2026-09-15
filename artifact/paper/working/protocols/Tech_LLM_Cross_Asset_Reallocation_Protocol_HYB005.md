# HYB-005 capital-neutral cross-asset reallocation

## Vai trò nghiên cứu

HYB-005 kiểm tra liệu text-state theo từng tài sản có giúp phân bổ tương đối giữa hai tài sản đã được một baseline Tech chọn hay không. Thiết kế không dùng Tech-Control canonical làm comparator vì control này khóa `top_n=1`, nên không có cặp tài sản đồng thời để tái phân bổ. Comparator của HYB-005 là predecessor daily `technical_cross_asset_4y_top2.json`; kết quả, nếu có, chỉ là exploratory transfer diagnostic và không thay thế Tech-Control canonical.

## Policy outcome-free đã đăng ký

Baseline giữ nguyên universe BTC/ETH/XRP/SOL/BNB, compressed-channel 10 ngày, regime BTC, rank momentum 20 ngày, tối đa hai tài sản, daily close-to-close và chi phí 10 bps trên mỗi đơn vị turnover. Khi có đúng hai vị thế, mỗi tài sản nhận signed event score bằng maximum positive strength trừ maximum negative strength trên event v3.9 trực tiếp gắn với asset. Strength bằng `severity × confidence × (0,5 + 0,5 × reported_surprise)`.

Với hai asset được sắp theo ticker, trọng số asset thứ nhất là `clip(0,5 + 0,25 × (score_1 - score_2), 0,25, 0,75)`; trọng số còn lại bằng một trừ trọng số này. Tổng exposure luôn bằng baseline. Ngày có zero/one position giữ nguyên trọng số Tech. LLM không tạo tài sản mới, không đổi gross exposure và không đọc forward return khi tạo assignment.

## Effective-sample gate

Trước target/evaluation, audit khóa bốn ngưỡng: ít nhất 1.000 ngày trong coverage, 100 ngày có hai vị thế, 60 ngày tái phân bổ thực sự và 15 ngày active trong từng chronological third. Audit dùng selection, event field, timestamp và weight; không đọc `i+1` return hoặc PnL.

Audit ngày 2026-09-11 có 1.081 ngày coverage nhưng chỉ 57 ngày có hai vị thế, 52 ngày active và phân bố active theo ba phần thời gian là 7/27/18. Ba sample gate tương ứng không đạt. Trạng thái canonical là `FAIL_STOP_BEFORE_TARGET_EVALUATION`; không tạo target, không tính return, không chạy placebo và không hạ ngưỡng hậu nghiệm.

Nguồn sự thật: `paper/input/results/hybrid/hyb005_cross_asset_reallocation_feasibility.json`, SHA-256 `e57b1fcc3653bd5771a31d4a2cdf99a4c99a8aab33f12efff1db08d570bb3a95`.
