# Giao thức thực thi của nhánh kỹ thuật

> Trạng thái: hợp đồng chuẩn cho `Tech-Control v1`, semantics `open_funding_intrabar_v2`.

## Thời điểm dữ liệu, tín hiệu và lệnh

- Tín hiệu chỉ được dùng nến đã đóng tại thời điểm cutoff.
- Mục tiêu của ngày `t` chỉ có hiệu lực ở open 4H hợp lệ tiếp theo của ngày `t+1`.
- Giá entry/rebalance là open đó cộng chi phí thực thi bất lợi theo cấu hình.
- Không được mở vị thế rồi dùng chuyển động giá xảy ra trước thời điểm fill để kích hoạt stop.
- Không được tái vào tại open của chính bar mà vị thế vừa bị stop sau open đó.

## Thứ tự sự kiện bắt buộc trên mỗi bar 4H

1. Đóng hợp đồng bị delist tại close 4H cuối cùng quan sát được nếu không còn bar tiếp theo.
2. Áp dụng target mới và fill entry/rebalance tại open hiện tại.
3. Thanh toán funding lịch sử cho vị thế đang được giữ tại đúng timestamp funding.
4. Kiểm tra stop trong bar bằng open và low.
5. Định giá các vị thế còn lại tại close.

## Stop và trailing stop

- Stop đang hoạt động là mức lớn hơn giữa fixed stop và trailing level tính từ đỉnh đã quan sát đến hết bar trước.
- Nếu open của bar thấp hơn stop long, fill tại open bất lợi, không fill lạc quan tại stop.
- Nếu open chưa gap qua stop nhưng low chạm stop, fill tại stop.
- High của bar hiện tại chỉ được cập nhật trailing peak cho bar kế tiếp; không siết stop hồi tố trong cùng bar.
- Không suy diễn đường đi TP-trước-SL từ OHLC khi dữ liệu không cho biết thứ tự intrabar.

## Hợp đồng tái lập

Mỗi kết quả lifecycle chuẩn phải có manifest anh em chứa:

- toàn bộ cấu hình CLI và phiên bản semantics;
- thứ tự sự kiện;
- Git revision và trạng thái dirty;
- SHA-256, kích thước byte và đường dẫn tuyệt đối của kết quả;
- SHA-256 của universe, daily, 4H và funding input;
- SHA-256 của các module nguồn quyết định kết quả.

Manifest chứng minh provenance, không biến development sample đã xem thành untouched holdout.

## Phạm vi và giới hạn

- Giao thức hiện chỉ được duyệt cho control 1x không vay.
- Chưa có lịch sử đầy đủ về maintenance-margin tier và liquidation của sàn cho claim leverage.
- OHLC không cho biết đường đi thật trong bar; quy ước trên là deterministic và bảo thủ.
- Muốn đánh giá live phải có sealed holdout mới sau khi cả Tech-only, LLM-only và Tech+LLM đều được khóa.
