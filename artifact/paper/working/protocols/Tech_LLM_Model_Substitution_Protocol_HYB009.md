# HYB-009 — controlled model-substitution trong Tech+LLM

## Câu hỏi và vai trò

HYB-009 kiểm tra câu hỏi phụ: khi giữ nguyên frozen Tech-Control, information timing, cost semantics và phép ánh xạ score thành exposure, representation LLM nào tạo ra tín hiệu điều chỉnh rủi ro hữu ích hơn. Đây là ablation model/representation, không phải đối chứng paper hybrid chính và không nhằm chứng minh Ministral, FinBERT hay CryptoBERT là mô hình tốt nhất nói chung.

Comparator paper hybrid vẫn là HYB-004, nơi thành phần adaptive recent-MSFE của Bennett et al. (2024) được chuyển giao lên cùng ETH panel. HYB-009 không thay thế EXT-002.

## Dữ liệu và thiết kế khóa

- Comparator: frozen long-only Tech-Control, 24 trade-entry opportunity từ 13-09-2022 đến 28-08-2025.
- Model có full daily artifact: FinBERT, CryptoBERT và Ministral-direct.
- Với mỗi entry, score hiện tại được chuẩn hóa thành empirical bearish percentile từ tối thiểu 180 quan sát causal trong 365 ngày trước đó.
- Thiết kế ngưỡng ban đầu (`confirm <0,70`, `downsize [0,70;0,85)`, `veto >=0,85`) FAIL outcome-free vì FinBERT và Ministral có 0 active opportunity, CryptoBERT chỉ có 4. Không PnL nào được mở ở bước này.
- Remediation v1.1 được định nghĩa từ phân bố feature trước khi xem PnL: `weight = 1 - 0,5 × bearish percentile`. Gate yêu cầu phủ đủ 24 opportunity và ít nhất 20 non-unit weight/model. FinBERT đạt 24/24, CryptoBERT 24/24, Ministral 23/24.
- Placebo: hoán vị weight theo timestamp bằng seed khóa và constant exposure 0,75.
- Economic gate family: paired net CI95 lower > 0; gross mean > 0; ít nhất 2/3 fold dương; Holm-adjusted one-sided quarter-cluster sign-flip p < 0,05; primary vượt shuffled và constant-0,75.

Mã evaluator và các input đã được hash trong predeclaration trước khi mở Tech PnL. Nghiên cứu này là post-outcome exploratory development, không phải validation, sealed holdout hoặc bằng chứng live.

## Kết quả kinh tế

Cả ba model FAIL economic incremental-value gate. Mean paired net/gross đều âm, CI95 net hoàn toàn dưới 0 và 0/3 fold dương:

| Representation | Mean paired net / opportunity | CI95 | Compounded net | Closed-trade MDD |
|---|---:|---:|---:|---:|
| Tech-Control | — | — | +239,0022% | 5,2883% |
| FinBERT | -0,5074 điểm % | [-0,7296; -0,3152] điểm % | +204,8577% | 3,9560% |
| CryptoBERT | -0,8884 điểm % | [-1,3635; -0,3445] điểm % | +181,3470% | 3,9734% |
| Ministral-direct | -0,4172 điểm % | [-0,6623; -0,2092] điểm % | +210,1557% | 4,7755% |

## Giá trị rủi ro mô tả

Giảm MDD so với Tech chưa đủ chứng minh giá trị của thông tin LLM vì mọi arm đều giảm exposure. Audit hậu đánh giá vì vậy còn so với shuffled weight và constant-0,75. CryptoBERT primary tốt hơn cả hai placebo trên closed-trade MDD, ES10 theo trade và worst trade; FinBERT chỉ tốt hơn cả hai trên MDD; Ministral không tốt hơn constant sizing trên ba metric này.

Tín hiệu CryptoBERT là bằng chứng mô tả rằng representation có thể định vị một phần downside tốt hơn giảm exposure mù trong đúng 24 opportunity này. Tuy nhiên, đây không phải risk gate được predeclare, chỉ có ba trade trong ES10, và lợi nhuận kinh tế giảm mạnh; vì vậy không được gọi là formal incremental value. Nó tạo giả thuyết risk-aware HYB tiếp theo, không cứu kết luận âm của HYB-009.

## GLM-4 9B Q3_K_M

GLM không được đưa vào bảng PnL. Event-extractor v21 đã fail contract. Một challenger độc lập trên frozen daily-information-set contract tiếp tục fail-fast ngay record đầu vì JSON không parse được (0/1 success), trước run 2, full 2.927-day inference, calibration và HYB. Đây là thất bại operational của exact local artifact/task contract, không phải kết luận về GLM nói chung.

## Artifact

- `paper/input/results/hybrid/hyb009_model_substitution_sample_audit.json`
- `paper/input/results/hybrid/hyb009_model_substitution_sample_audit_v1_1.json`
- `paper/input/results/hybrid/hyb009_model_substitution_v1_1_predeclared.json`
- `paper/input/results/hybrid/hyb009_model_substitution_v1_1_evaluation.json`
- `paper/input/results/hybrid/hyb009_model_substitution_v1_1_risk_audit.json`
- `runtime/glm4_9b_challenger/results/llm_glm4_9b_q3km_challenger_gate_v1.json`
