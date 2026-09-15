# Giao thức khóa ba nhánh và sealed forward holdout

> Trạng thái: Tech đã khóa; lịch sử LLM-only v1–v16 được giữ như negative evidence/operational stops; HYB-001 và HYB-002 đều FAIL trong exploratory development; HYB-003 mới hoàn tất Stage A và kiểm tra extractor Stage 1, chưa có kết quả hiệu năng; chưa đăng ký hoặc thu thập sealed holdout mới.

## Tech-Control đã khóa

`tech-control-v1` cố định universe top-5 thanh khoản point-in-time trên toàn bộ vòng đời Bybit USDT perpetual, sự kiện compressed-channel, xếp hạng momentum 20 ngày, top-1, stop 3 ATR, trailing 4 ATR, gross exposure 1x và semantics `open_funding_intrabar_v2`.

Development evidence kết thúc tại 2026-08-11 UTC. Toàn bộ 54 cấu hình và hai fold cuối đã được xem; vì vậy không fold nào là untouched holdout. Freeze manifest khóa hash cấu hình, mã nguồn và artifact. Đây là khóa nghiên cứu ở mức artifact trong một worktree dirty, không phải software release sạch.

## Hợp đồng ba nhánh

Ba nhánh bắt buộc:

1. `Tech-only`: control đã khóa.
2. `LLM-only`: diagnostic để kiểm tra thông tin độc lập của LLM.
3. `Tech+LLM`: treatment chính để đo phần gia tăng so với Tech-only.

LLM-only trả lời câu hỏi về predictive value vô điều kiện; Tech+LLM trả lời câu hỏi về incremental decision value có điều kiện sau tín hiệu Tech. Vì hai estimand khác nhau, LLM-only FAIL bác bỏ standalone-alpha claim nhưng không tự động cấm một protocol Tech+LLM độc lập. Freeze âm ngăn sửa hoặc lựa chọn lại kết quả cũ và vẫn là negative control bắt buộc phải báo cáo.

Tech+LLM giữ Tech-Control làm shadow control và không cho LLM tạo hoặc đảo chiều giao dịch. HYB-001 dùng entry permission/weight và đã FAIL. HYB-002 không tác động entry; nó chỉ giảm exposure một bar 4 giờ trong shadow trade khi semantic shock đúng asset/systemic được xác nhận đa nguồn và cũng đã FAIL. HYB-003 kiểm tra conditional state fusion bằng bốn arm `T0/T1/T2/T3`, với estimand chính `T3-T1`; candidate này mới hoàn tất các cổng khả thi và vận hành ban đầu, chưa được đánh giá performance. Hợp đồng tương ứng nằm tại `Tech_LLM_Conditional_Overlay_Protocol_v1.md`, `Tech_LLM_Intratrade_Shock_Shield_Protocol_v2.md` và `Tech_LLM_Conditional_State_Fusion_Protocol_v3.md`.

Mọi nhánh phải dùng cùng universe snapshot, cutoff, next-4H-open fill, vốn, 1x exposure, stop, chi phí, funding và semantics. Decision phải có hash của source snapshot và pipeline. Earliest fill phải muộn hơn decision timestamp. Lỗi LLM phải được ghi và chuyển về hành động đã khai báo trước; không được âm thầm loại khỏi mẫu.

Estimand chính là chênh lệch paired net performance `Tech+LLM - Tech-only` trên cùng timestamp.

## Cửa sổ cũ không được kích hoạt

Cửa sổ từng được đăng ký từ `2026-08-14 00:00 UTC` đến `2027-02-10 00:00 UTC` mang trạng thái `scheduled-blocked-not-collecting`. Đến ngày bắt đầu, LLM-only và Tech+LLM chưa được khóa nên dữ liệu không được thu dưới nhãn sealed holdout.

Khoảng thời gian đã bỏ lỡ không được backfill rồi gọi là holdout. Chỉ sau khi một hybrid candidate mới vượt development gate và đủ các freeze cho Tech-Control, negative-control/version register của LLM, policy hybrid và thiết kế ba nhánh thì mới được đăng ký một ngày bắt đầu trong tương lai, embargo tối thiểu ba ngày và thời lượng tối thiểu 180 ngày. Freeze LLM ở đây yêu cầu giữ nguyên feature/provenance được dùng bởi hybrid và lịch sử negative control; không yêu cầu LLM-only predictive PASS. Các freeze thất bại của HYB-001/HYB-002 không được tái sử dụng như một candidate holdout.

## Chính sách mở holdout mới

- Không đọc hiệu suất tạm thời.
- Không đổi model, prompt, threshold, fusion rule hoặc tham số Tech sau khi bắt đầu.
- Được theo dõi chất lượng dữ liệu nếu không tính hoặc xem performance.
- Chỉ mở một lần sau ngày kết thúc và khi đủ dữ liệu của cả ba nhánh.
- Bất kỳ protocol deviation nào cũng phải ghi vào sổ cái thí nghiệm.
