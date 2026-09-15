# HYB-004 Bennett-style adaptive-MSFE ETH transfer

> Trạng thái: EXPLORATORY TRANSFER FAIL. Không cấp quyền holdout.

HYB-004 chuyển giao riêng nguyên tắc adaptive combination theo recent mean squared forecast error từ Bennett et al. (2024). Đây không phải replication: nghiên cứu không có dữ liệu MarketPsych thương mại, dynamic universe và toàn bộ model set gốc. Comparator dùng cùng panel ETH 699 ngày OOS: Tech arm là Ridge trên feature ETH/cross-asset causal; LLM arm là Ridge trên event-conditioned feature v17; fusion dùng trọng số inverse-MSFE của 30 forecast error gần nhất đã trưởng thành.

V1 dùng fitted residual trong train để khởi tạo trọng số. Cách này không tương đương forecast MSFE nên artifact v1 được giữ làm lịch sử nhưng bị thay thế. V1.1 là remediation hậu kiểm: mỗi fold bắt đầu 50/50 và chỉ chuyển sang inverse-MSFE sau khi đủ 30 outcome OOS đã đến hạn. Vì v1.1 được xác định sau khi đã xem kết quả v1, nó chỉ là benchmark development tái lập, không phải predeclared validation.

V1.1 cho MSE Tech 0,00135069 và fusion 0,00136746. Delta MSE `Tech-Fusion` bằng -0,00001678, CI 95% [-0,00003974; 0,00001031]; fusion thắng 2/5 fold. Với daily sign policy, phí một chiều 11 bps và funding thật, compounded net return của Tech là -41,30% còn fusion là -90,24%; mean daily net delta bằng -0,25463 điểm phần trăm, CI 95% [-0,50735; 0,12142]. Không gate nào cho phép claim incremental value.
