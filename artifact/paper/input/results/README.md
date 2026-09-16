# Kết quả dùng để viết luận văn

## Thành phần

- `experiment_ledger/`: sổ cái tổng hợp Tech, LLM và Tech+LLM, là điểm tra cứu đầu tiên cho con người. Audit hiện có chuỗi `LLM-001`–`LLM-086` và kết quả `HYB-001`–`HYB-010`; HYB-007 có tail-risk attenuation nhưng formal gate FAIL, HYB-008 conditional downside information FAIL trước policy, HYB-009 model substitution FAIL economic gate, còn HYB-010 là development hậu outcome và FAIL strong risk-budget-conversion gate vì cận dưới CI 95% không dương. V13 chưa từng được gán nên không tạo experiment giả để lấp số.
- `snapshots/`: bản sao nhỏ của cấu hình và kết luận trạng thái tại thời điểm kiểm toán.
- `provenance/`: snapshot quy tắc vận hành hoặc metadata cần để giải thích cách kết quả được tạo ra.
- `frozen/`: snapshot artifact bất biến kèm manifest và SHA-256; trạng thái thành công/âm phải đọc từ manifest, không suy ra chỉ từ tên thư mục.
- `llm/v3/`: lịch sử event-risk extractor v3.3–v3.9. Full extraction v3.9 đạt 39.393/39.393 record, nhưng predictive return v3.1.1 và predictive risk v3.2 đều không tạo incremental value đã đăng ký trước; không có standalone-alpha claim.
- `llm/v4/`–`llm/v12_4*`: các candidate external representation, full-text, contrastive, event-conditioned, social/FOMC/official-source và dataset-screen; trạng thái canonical và artifact đại diện được lập chỉ mục tại `paper/working/audits/LLM_Version_Register_v1_v16.md`.
- `llm/v14/`: corpus SEC RSS Internet Archive, candle-artifact audit, predeclaration, extraction và data-gate outcome-blind. Extraction đạt 1.120/1.120 với 0 lỗi, nhưng chỉ có 64/96 information set eligible; data gate FAIL và dừng trước target join/predictive evaluation/backtest.
- `llm/v15/`: corpus CFTC RSS Internet Archive và predictive predeclaration outcome-blind. Corpus gate đạt với 1.892 record/124 information set; extraction đạt 1.892/1.892 với 0 lỗi, nhưng chỉ có 64/96 information set eligible; data gate FAIL và dừng trước target join/predictive evaluation/backtest.
- `llm/v16/`: corpus title-only ECB RSS Internet Archive và predictive predeclaration outcome-blind. Corpus gate đạt với 2.249 record/400 information set; extraction đạt 2.249/2.249 với 0 lỗi; 245 record eligible tạo 135/96 information set nên data gate PASS. Target-coverage feasibility sau đó FAIL: Binance Vision BTCUSDT spot 4h bắt đầu 2017-08, 94/135 set nằm trước mốc và trần targetable chỉ 41, thấp hơn 72 OOS bắt buộc. Dừng trước target/predictive evaluation/backtest.
- `llm/v17/`: ETH LLM-only transfer. Outcome-free feasibility PASS với 5.341 direct-ETH event trên 1.000 ngày; predictive gate có 699 OOS prediction nhưng event-conditioned arm thua generic ở cả 5 fold, nên FAIL và dừng trước LLM-only backtest.
- `llm/v18/`: LLM-only multi-coin transfer dùng cùng thiết kế v17 cho BTC/XRP/SOL/BNB. Outcome-free screen chỉ cho phép BTC nối target; XRP, SOL và BNB dừng vì thiếu effective sample theo ngưỡng khóa. BTC có 699 prediction OOS nhưng event-conditioned arm thua generic về MSE, CI 95% của chênh lệch nằm hoàn toàn dưới 0 và chỉ thắng 1/5 fold; family gate FAIL, dừng trước threshold/action/backtest.
- `llm/v19/`: multi-coin risk transfer cho ETH/SOL primary và XRP/BNB conditional. Chỉ ETH qua sample gate; volatility 24 giờ và adverse-excursion semantic increment đều FAIL trên 699 OOS. Dừng trước Tech risk overlay, nên không có drawdown/cost result.
- `llm/v20/`: short-horizon event-response transfer ở 4 giờ. ETH và SOL qua sample gate nhưng event-conditioned arm không hơn metadata/generic; XRP và BNB dừng outcome-free trước target. Metadata comparator còn phụ thuộc affected_assets do LLM sinh.
- `llm/v21/` và `results/llm_*glm4*`: bản sao kiểm toán tối thiểu của predeclaration, partial run và gate cho LLM-085/LLM-086. Exact GLM-4 9B Q3_K_M fail event-extractor contract ở v21; independent daily-information-set challenger cũng fail-fast ngay record đầu vì JSON không hợp lệ. Không nhánh nào được nối outcome hoặc HYB.
- `hybrid/`: predeclaration và kết quả HYB-001/HYB-002 cùng audit HYB-003, external transfer HYB-004, feasibility HYB-005, rank-pair transfer HYB-006, historical risk attenuation HYB-007, conditional downside gate HYB-008, model-substitution HYB-009 và risk-budget reallocation HYB-010. HYB-009 giữ cùng canonical Tech-Control/policy cho FinBERT, CryptoBERT và Ministral; cả ba economic gate FAIL. HYB-010 dùng tín hiệu CryptoBERT đã được chọn sau khi xem HYB-009, cải thiện một số chỉ số trong đúng mẫu historical nhưng không đạt điều kiện CI của strong gate. Bản HYB-007 prospective tạo sai phạm vi được giữ dưới tên `WITHDRAWN_SCOPE_ERROR`. Không gọi các kết quả này là replication/validation/holdout/live evidence.

Artifact JSON đầy đủ trong `results/` ở gốc repository và freeze manifest vẫn là nguồn sự thật cao nhất. Snapshot tại đây không được sửa để làm thay đổi kết luận của artifact gốc.

Sau mỗi thí nghiệm, cập nhật sổ cái với phương pháp, dữ liệu, protocol, cấu hình, kết quả, trạng thái, giới hạn, đường dẫn artifact và SHA-256. Tách riêng “kết quả trong bài báo gốc” và “kết quả phương pháp đó trên dữ liệu dự án”.

# Cập nhật MSA-001 và EXT-002 (2026-09-12)

- `paper/working/audits/Model_Selection_Audit_MSA001.md` đóng kiểm toán lựa chọn model: Ministral v3.9 là operational reference, không phải predictive winner.
- `hybrid/ext002_external_tech_llm_baseline_comparison.json` tổng hợp admission và same-context evidence cho external Tech+LLM baseline. Chỉ Bennett recent-MSFE được admission; baseline này không vượt incremental-value gate.
- Sổ cái giữ thứ tự LLM-only trước Tech+LLM. Diagnostic task-compatibility LLM-086 nằm sau LLM-085; MSA-001 nằm sau LLM-086 và trước HYB-001; HYB-010 là mục hybrid đăng ký mới nhất trong gói hiện tại.
