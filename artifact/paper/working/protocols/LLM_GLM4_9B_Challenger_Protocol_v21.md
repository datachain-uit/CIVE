# Protocol v21 — GLM-4 9B Q3_K_M local challenger

## Câu hỏi nghiên cứu

GLM-4 9B Q3_K_M có đủ độ tin cậy vận hành để tạo bản ghi sự kiện có cấu trúc bằng đúng hợp đồng extractor v3 đã khóa hay không? Đây là kiểm tra reliability của extractor, không phải kiểm tra dự báo lợi suất và không phải backtest.

## Lý do chọn model trước khi xem kết quả

- GLM-4 là một họ model chưa được thử trong chuỗi challenger hiện tại, nên bổ sung bằng chứng về khả năng chuyển giao qua kiến trúc thay vì lặp lại một biến thể cùng họ.
- Artifact glm4:9b-chat-q3_K_M có kích thước cài đặt 5,1 GB, phù hợp với GPU 6 GB của máy. Q3_K_M được chọn vì ràng buộc bộ nhớ, không vì kết quả dự báo.
- Model được chạy local nên không phát sinh chi phí API theo token và có thể cố định digest.
- Không chạy GLM-5.2, MiniMax-M3 hay Kimi-K3 trong vòng này vì chưa có artifact local phù hợp đã được kiểm chứng trên phần cứng hiện tại. Việc thay bằng API/cloud sẽ thay đổi cả chi phí, khả năng tái lập và điều kiện triển khai.
- Không mở rộng thêm model sau khi thấy kết quả GLM-4. Quyết định dừng chuỗi LLM-only được áp dụng bất kể PASS hay FAIL của v21.

## Hợp đồng khóa trước inference

- Experiment ID: LLM-085.
- Model: glm4:9b-chat-q3_K_M; digest được lấy từ Ollama và ghi vào JSON predeclaration trước output đầu tiên.
- Sample: 114 bài, 38 strata, cùng artifact frozen của Stage 1 v3.
- Prompt, JSON schema, batch size 4, temperature 0, seed, hai lần chạy độc lập và toàn bộ ngưỡng gate giữ nguyên so với challenger Ministral.
- Một worker; request delay 10 giây; checkpoint nguyên tử.
- Không join outcome, không xem return, không điều chỉnh prompt/schema/gate sau khi bắt đầu.

## Quy tắc quyết định

Stage 1 chỉ PASS khi cả hai lần chạy có đủ 114/114 bản ghi hợp lệ, đúng ID/thứ tự/evidence, đồng thời đạt tất cả ngưỡng agreement đã predeclare. Nếu một lần chạy tạo lỗi, tiến trình fail-fast và không chạy full corpus. Nếu Stage 1 PASS, full-corpus extraction chỉ được xem là một bước vận hành riêng; PASS không tự chứng minh predictive hay economic incremental value.

## An toàn nhiệt

Chạy Windows Balanced, một inference worker và đọc nhiệt độ NVIDIA mỗi 5 giây. Dừng producer, giữ checkpoint, unload model khi nhiệt độ từ 75°C; chỉ tiếp tục khi không quá 70°C. Kết thúc phải unload model, xác nhận Balanced và GPU compute bằng 0.
