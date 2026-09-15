# HYB-010 — kết quả tái phân bổ risk budget bằng CryptoBERT

## Kết quả chính

HYB-010 hoàn tất trên 24 opportunity và tái chạy tất định cho kết quả trùng khớp. Primary có exposure trung bình 1,04496×, nằm trong `[0,80220; 1,22802]`. Net return gộp tăng từ `+239,0022%` của Tech lên `+274,2859%`; mean paired net delta bằng `+0,4829` điểm phần trăm mỗi opportunity với CI 95% `[-0,2139; +1,4393]` điểm phần trăm. Hai trong ba fold có delta dương.

Primary thắng shuffled và constant matched-budget về mean net delta và closed-trade MDD. So với Tech, closed-trade MDD thay đổi từ `5,2883%` xuống `5,2838%`, ES10 từ `-4,1509%` lên `-3,7561%`, và worst trade từ `-4,7886%` lên `-4,4071%`. Mức cải thiện MDD là rất nhỏ.

Theo định nghĩa của đề cương, HYB-010 tạo incremental value trên cả chiều return và risk trong đúng mẫu historical này. Strong risk-budget-conversion gate FAIL duy nhất ở điều kiện cận dưới CI 95% phải dương; các điều kiện allocation-selectivity, compounded return, 2/3 fold và ba điều kiện bảo toàn rủi ro đều đạt. Kết quả là post-outcome exploratory development vì CryptoBERT được chọn từ audit HYB-009; không phải validation, sealed holdout hoặc bằng chứng live.

## Truy vết

- Predeclaration: `paper/input/results/hybrid/hyb010_risk_budget_reallocation_predeclared.json`, SHA-256 `21894a4d027af09de812d99459b46ce872408831bb8d5dcffb89c70f22854fe9`.
- Evaluation: `paper/input/results/hybrid/hyb010_risk_budget_reallocation_evaluation.json`, SHA-256 `a98f0384e0a0e77cccd6e601e5616f5ea24f314605b3171c4e4e22719809375b`.
- Protocol: `paper/working/protocols/Tech_LLM_Risk_Budget_Reallocation_Protocol_HYB010.md`.
- Evaluator: `tools/llm/evaluate_hyb010_risk_budget_reallocation.py`.
