# Công cụ hỗ trợ pipeline LLM

Thư mục này lưu các công cụ phục vụ đọc mã, kiểm toán và regression test. Snapshot nguồn nghiên cứu, cấu hình và artifact đầy đủ nằm trong `executor/`, `configs/`, `data/` và `results/` ở gốc repository.

- `build_*`, `score_*`, `llm_*`: xử lý corpus, chấm điểm và adapter/backtest.
- `audit_*`: kiểm toán độ lặp và hiệu chuẩn theo outcome.
- `evaluate_llm_challenger_fail_fast.py`: kết luận Stage 1 sớm chỉ khi số schema success tối đa đã thấp hơn ngưỡng khai báo trước.
- `test_*`: regression test nhẹ.
- `*.ps1`: runner Windows có cổng nhiệt và checkpoint; log được ghi vào `runtime/logs/llm/`. `run_llm_challenger_gate_thermal_safe.ps1` nhận model, mã ứng viên, stem artifact và config để mọi challenger dùng cùng một quy trình Stage 1.

Không chạy đồng thời nhiều runner. Các runner tính toán dài phải tuân thủ ngưỡng nhiệt trong `AGENTS.md`.

`score_llm_daily_information_sets.py` phụ thuộc `score_llm_causal_corpus.py` ở production, nên bản sao KLTN không phải một gói triển khai độc lập hoàn chỉnh.
