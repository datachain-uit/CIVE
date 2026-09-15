# Bản sao quy tắc vận hành production

## An toàn nhiệt — bắt buộc

- Xem 75°C trên cảm biến NVIDIA GPU là ngưỡng cứng cho công việc tính toán nặng.
- Không bắt đầu inference LLM, backtest, render hoặc tác vụ tính toán kéo dài khi GPU từ 75°C trở lên.
- Khi tác vụ kéo dài đang chạy, đọc nhiệt độ ít nhất mỗi 5 giây. Từ 75°C phải dừng producer, giữ checkpoint nguyên tử, unload model khỏi GPU và đưa Windows về Balanced. Nếu không đọc được cảm biến thì phải dừng an toàn.
- Chỉ tiếp tục khi GPU không quá 70°C; ưu tiên chạy chậm hoặc qua đêm thay vì vượt ngưỡng.
- Inference LLM chỉ dùng một worker. Không chạy nhiều tác vụ nặng song song; kiểm tra nhẹ và logging được phép.
- Tác vụ dài dùng Windows Balanced và profile Silent/Windows của hãng. Không bật High performance/Turbo hoặc đổi giới hạn công suất/xung GPU nếu chưa có chấp thuận mới, rõ ràng.
- Kết thúc tác vụ dài phải unload model, xác nhận không còn compute process, GPU compute utilization bằng 0 và khôi phục Balanced.
