# MSA-001 — Kiểm toán lựa chọn model LLM đã đóng băng

> Chốt ngày 2026-09-12. Đây là kiểm toán lựa chọn model từ artifact hiện có, không phải một predictive experiment mới và không chạy lại inference.

## Câu hỏi kiểm toán

Việc giữ Ministral 3 8B v3.9 làm extractor tham chiếu có được biện minh bởi bằng chứng hiện có không, và phạm vi của quyết định này là gì?

## Quyết định

Ministral 3 8B v3.9 được giữ làm **operational reference extractor** cho structured-event pipeline. Quyết định này dựa trên khả năng hoàn tất extraction, tuân thủ schema và tái lập. Quyết định không dựa trên predictive superiority hoặc economic superiority.

Không model nào trong nhánh đã khóa được công nhận là standalone alpha hoặc là model dự báo tốt nhất. Vì các nhóm model đã được đánh giá dưới những output contract khác nhau, dự án không lập một leaderboard chung giữa sentiment classifier, direct-direction generator và structured-event extractor.

## Chuỗi quyết định model

| Nhóm | Model/phiên bản | Bằng chứng chính | Quyết định |
|---|---|---|---|
| Direct direction | Llama 3 | Full development backtest có kết quả dương nhưng calibration CI cắt 0; không phải freeze evidence | Không dùng làm alpha |
| Direct direction | Qwen 2.5 7B | Reliability 108/108 hai run; Pearson 0,0081 và long-flat -10,63 bps, predictive lower bounds âm | Dừng trước backtest |
| Direct direction | Qwen 3 8B | Reliability 108/108; Pearson và long-flat CI cắt 0 | Dừng trước backtest |
| Direct direction | Nemotron 3 Nano 4B | Schema đạt nhưng score agreement 102/108 và mean absolute difference 0,01204 | Reliability FAIL |
| Direct direction | Llama 3.1 8B | 48/49 request thành công; fail-fast | Operational FAIL |
| Direct direction | Gemma 3 4B | 8/10 schema thành công; fail-fast | Operational FAIL |
| Financial model | FinGPT ChatGLM2 | Stage 1 reliability thất bại | Operational FAIL |
| Sentiment classifier | FinBERT | Predictive CI không xác nhận edge | Predictive FAIL |
| Sentiment classifier | CryptoBERT | Point estimate thuận lợi nhưng CI chứa 0 | Chưa xác nhận predictive value |
| Structured event | Ministral 3 8B v3.9 | 39.393/39.393 record hoàn tất, 0 schema error; đủ điều kiện xây panel | Operational reference PASS |
| Structured event | GLM-4 9B Q3_K_M v21 | 4/8 record đầu lỗi vì severity ngoài [0,1] | Exact-contract operational FAIL |
| Direct direction | GLM-4 9B Q3_K_M daily challenger | Independent frozen daily-information-set contract fail-fast ngay record đầu vì JSON không parse được | Operational FAIL; dừng trước full inference/outcome/HYB |

## Vì sao không chạy lại toàn bộ model

1. Câu hỏi trung tâm của luận văn là incremental decision value của Tech+LLM so với Tech, không phải model leaderboard.
2. FinBERT/CryptoBERT không tạo cùng event schema nên không phải drop-in replacement cho extractor v3.9. HYB-009 chỉ dùng chúng trong controlled daily-score representation ablation với cùng causal percentile-to-exposure rule; ablation này không biến chúng thành structured-event extractor.
3. Chạy thêm model sau khi đã xem outcome tạo nguy cơ model shopping. Một vòng mới chỉ hợp lệ khi predeclare family, contract, compute budget, multiplicity và stop rule.
4. GLM-4 thất bại ở cả exact frozen event schema v21 và một independent frozen daily JSON contract. Hai thất bại operational không phải bằng chứng predictive/economic và không cho phép nối model vào HYB.

## Phạm vi claim

Được phép viết: Ministral v3.9 là extractor tham chiếu ổn định nhất đã hoàn tất exact structured-event contract trong các model được thử.

Không được viết: Ministral là model dự báo tốt nhất, tạo lợi nhuận tốt nhất, hoặc tốt hơn mọi model tài chính/LLM khác.

## Liên kết với đóng nhánh LLM-only

MSA-001 không thay đổi kết luận tại `LLM_Only_Closure_v21.md`: semantic increment chưa cải thiện comparator trong các predictive test đủ điều kiện. Giá trị đã xác nhận của LLM-only nằm ở vận hành, biểu diễn và chẩn đoán; predictive/economic incremental value chưa được xác nhận.

## Nguồn sự thật

- `paper/working/audits/LLM_Version_Register_v1_v16.md`
- `paper/working/audits/LLM_Only_Closure_v21.md`
- `paper/working/03_claims.md`
- Artifact tương ứng dưới `paper/input/results/llm/` và `runtime/glm4_9b_challenger/results/`
