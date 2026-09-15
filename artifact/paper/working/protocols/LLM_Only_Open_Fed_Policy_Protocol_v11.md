# Protocol LLM-only Open Fed Policy v11

## Phạm vi bằng chứng

Đây là nhánh development sau các kết quả v3-v8. Corpus đầu vào gồm 110 sự kiện từ 113 thông cáo Federal Reserve có ngày `Last Update` trùng ngày công bố; 49 thông cáo cập nhật muộn bị cách ly trước khi đọc outcome. Điều kiện cùng ngày không chứng minh phiên bản intraday đầu tiên, nên thí nghiệm không được gọi là point-in-time nghiêm ngặt hoặc sealed confirmation.

## Input và model

- Predictive input chỉ gồm văn bản thông cáo và output của LLM. Không dùng OHLCV, return trễ, volume, volatility, funding, breadth, regime, technical indicator hoặc metadata thời gian làm feature.
- Model duy nhất: `ministral-3:8b`, khóa digest cài đặt, temperature 0, seed 20260905, `think=false`, một worker và batch size 1.
- Output gồm generic direction/intensity và event-conditioned policy direction/intensity, event type, explicit surprise language, systemic scope và confidence. Evidence phải là substring nguyên văn.
- Không sweep model, prompt, schema, seed hoặc decoding sau khi đọc outcome. Lỗi schema dừng run; chỉ được sửa lỗi contract trong phiên bản mới và phải chạy lại từ đầu.

## Target và đánh giá

- Target duy nhất kế thừa v8: `BTCUSDT open[t+4h] / open[t] - 1`, trong đó `t` là open UTC 4 giờ đầu tiên nằm nghiêm ngặt sau thời điểm công bố được ghi nhận.
- Giá chỉ dùng để tạo nhãn và đánh giá; không đi vào feature.
- Ba arm bắt buộc: prior là mean target trên train fold; generic sentiment ridge; event-conditioned ridge. Alpha ridge cố định 10, chuẩn hóa chỉ trên train fold.
- Split expanding time-OOS được khóa theo năm/quý sau khi chỉ đếm timestamp, không xem phân phối target. Dữ liệu giá bắt đầu tháng 8/2022 nên sự kiện trước coverage có thể bị loại chỉ vì thiếu nhãn.
- Gate yêu cầu event arm có CI 95% dưới của paired MSE improvement lớn hơn 0 so với cả prior và generic sentiment, CI 95% dưới của Pearson lớn hơn 0, và thắng cả hai comparator ở đa số fold. Bootstrap moving-block được khóa trước evaluation.

Nếu fail, đóng băng kết quả âm và dừng trước threshold, action mapping, trading backtest hoặc sealed holdout. Nếu pass, chỉ cho phép thiết kế một development backtest LLM-only riêng; không tự động chứng minh khả năng chạy live.

## An toàn vận hành

Inference chạy qua wrapper nhiệt: Windows Balanced, đọc cảm biến NVIDIA mỗi 5 giây, dừng và unload từ 75°C, chỉ resume khi không quá 70°C. Nếu power plan bị đổi, wrapper đặt lại Balanced và tiếp tục khi nhiệt độ an toàn. Không đọc được cảm biến thì dừng đóng.
