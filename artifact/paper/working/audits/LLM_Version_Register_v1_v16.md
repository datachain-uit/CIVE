# Sổ đăng ký version LLM v1–v21

> Kiểm toán đến ngày 2026-09-11. Nguồn sự thật là artifact JSON/manifest và sổ cái thí nghiệm; file này chỉ lập chỉ mục trạng thái. Không có version nào dưới đây được diễn giải lại thành standalone alpha.

## Kết quả đối chiếu

Sổ cái trước kiểm toán có LLM-001–LLM-041 nhưng chưa ghi đủ các version mới: thiếu v3.5–v3.9, predictive v3.1.1/v3.2 và toàn bộ v4–v12.4. V14–v16 đã có ở LLM-039–LLM-041. Không có artifact hoặc protocol v13 trong workspace; số v13 chưa từng được gán, nên đây là khoảng đánh số chứ không phải kết quả bị thiếu.

## Version và trạng thái canonical

| Version | Nội dung | Trạng thái canonical | Artifact đại diện | Dòng ledger |
|---|---|---|---|---|
| v1–v2 | Direct-direction, challenger và freeze âm | Frozen negative development evidence; không standalone alpha | `paper/input/results/frozen/llm_direct_direction_v1/manifest.json` | LLM-001–LLM-028 |
| v3, v3.1, v3.2 extractor | Sửa contract ban đầu | Fail-fast trước full extraction | `paper/input/results/llm/v3/llm_event_extractor_v3_stage1_gate.json` | LLM-032–LLM-034 |
| v3.3–v3.8 extractor | Stage 1 đạt rồi full extraction lần lượt fail-fast | Operational development failures được giữ nguyên | `paper/input/results/llm/v3/llm_event_extractor_v3_8_full_failure.json` | LLM-035–LLM-038; LLM-042–LLM-045 |
| v3.9 extractor | Full extraction hoàn tất | Extraction PASS; chưa phải predictive evidence | `paper/input/results/llm/v3/llm_event_extractor_v3_9_full_gate.json` | LLM-046 |
| predictive v3.1.1 | Return 24 giờ | Predictive gate FAIL | `paper/input/results/llm/v3/llm_event_predictive_gate_v3_1_1_development.json` | LLM-047 |
| predictive v3.2 | Realized volatility 24 giờ | Predictive gate FAIL | `paper/input/results/llm/v3/llm_event_risk_predictive_gate_v3_2_development.json` | LLM-048 |
| v4 | External MiniLM impact | External gate FAIL trước project-corpus scoring | `paper/input/results/llm/v4/llm_minilm_external_gate_v4.json` | LLM-049 |
| v5 | Full-text impact | Predictive gate FAIL | `paper/input/results/llm/v5/llm_fulltext_market_impact_gate_v5.json` | LLM-050 |
| v6 | Supervised contrastive impact | Predictive gate FAIL | `paper/input/results/llm/v6/llm_contrastive_market_impact_gate_v6.json` | LLM-051 |
| v7/v7.0.1 | LLM-only event-conditioned | Protocol v7 aborted; corrected v7.0.1 predictive gate FAIL | `paper/input/results/llm/v7/llm_only_event_conditioned_gate_v7_0_1.json` | LLM-052 |
| v8 | Short-horizon event response | Predictive gate FAIL | `paper/input/results/llm/v8/llm_only_event_response_gate_v8.json` | LLM-053 |
| v9/v9.1/v9.2 | Social source, Arctic pilot và access review | Không corpus nào được admitted | `paper/input/results/llm/v9/social_access_review_v9_2.json` | LLM-054–LLM-056 |
| v10/v10.1/v10.2 | Open FOMC pilot và archive provenance | Reproducible text pilot; không đủ predictive admission | `paper/input/results/llm/v10/fomc_provenance_summary_v10.json` | LLM-057–LLM-059 |
| v11.0.1 | Expanded Fed policy corpus | Reproducible corpus; chưa predictive freeze | `paper/input/results/llm/v11/open_fed_policy_corpus_v11_0_1/manifest.json` | LLM-060 |
| v11/v11.1/v11.1.1/v11.1.2 | Extraction corrections | Các failure vận hành được archive | `paper/input/results/llm/v11/archive_operational_failures/` | LLM-061–LLM-064 |
| v11.1.3 | Final extraction | 110/110 success; development only | `paper/input/results/llm/v11/open_fed_policy_extraction_v11_1_3.json` | LLM-065 |
| v11 predictive | Open Fed policy evaluation | Development predictive gate FAIL | `paper/input/results/llm/v11/open_fed_policy_gate_v11.json` | LLM-066 |
| v12 | Prospective official crypto tail-risk | Dừng trước corpus admission | `paper/input/results/llm/v12/prospective_official_crypto_tail_risk/latest_audit.json` | LLM-067 |
| v12.1–v12.4 | Dataset rights/PIT/leakage screens | Không dataset nào được admitted | `paper/input/results/llm/v12_4_dataset_screen_registry.json` | LLM-068–LLM-071 |
| v13 | Chưa từng gán | Không có experiment/artifact; không tạo kết quả giả để lấp số | — | — |
| v14 | SEC RSS archive | Data gate FAIL | `paper/input/results/llm/v14/sec_rss_archive_predictive_v14/extraction_gate.json` | LLM-039 |
| v15 | CFTC RSS archive | Data gate FAIL | `paper/input/results/llm/v15/cftc_rss_archive_predictive_v15/extraction_gate.json` | LLM-040 |
| v16 | ECB RSS archive | Target-coverage feasibility FAIL trước candle download | `paper/input/results/llm/v16/ecb_rss_archive_predictive_v16/target_coverage_feasibility_gate.json` | LLM-041 |
| v17 | ETH LLM-only transfer từ frozen v3.9 | Outcome-free sample audit PASS; predictive transfer FAIL trên 699 OOS, dừng trước LLM-only backtest | `paper/input/results/llm/v17/llm_only_eth_transfer_gate_v17.json` | LLM-072 |
| v18 | Multi-coin return transfer | Chỉ BTC qua sample gate rồi predictive FAIL; XRP/SOL/BNB dừng trước target | `paper/input/results/llm/v18/llm_only_multicoin_family_gate_v18.json` | LLM-073–LLM-076 |
| v19 | Multi-coin risk transfer | Chỉ ETH qua sample gate; volatility và adverse-excursion semantic increment đều FAIL; dừng trước Tech risk overlay | `paper/input/results/llm/v19/llm_only_multicoin_risk_gate_v19.json` | LLM-077–LLM-080 |
| v20 | Multi-coin 4h event-response transfer | ETH/SOL qua sample gate nhưng semantic increment FAIL; XRP/BNB dừng trước target | `paper/input/results/llm/v20/llm_only_multicoin_short_gate_v20.json` | LLM-081–LLM-084 |
| v21 | GLM-4 9B Q3_K_M event-extractor challenger | Stage 1 fail-fast: 4/8 record lỗi vì severity ngoài [0,1]; dừng trước run 2/full extraction/outcome | `runtime/glm4_9b_challenger/results/llm_event_extractor_glm4_9b_v21_stage1_gate.json` | LLM-085 |

## Trật tự lập luận canonical

1. LLM-LEG-1/2 chỉ chứng minh pipeline cũ không đủ điều kiện làm evidence.
2. LLM-001–028 kiểm tra model family, reliability, calibration và đóng băng negative direct-direction evidence.
3. LLM-029–048 xây event representation, sửa contract đến v3.9 rồi kiểm tra return/risk trên BTC.
4. LLM-049–071 kiểm tra external representation, full text, contrastive learning, source/provenance và official corpus.
5. LLM-072–084 kiểm tra transfer theo asset/horizon/risk sau outcome-free sample audit.
6. LLM-085 là local architecture challenger cuối. Nhánh LLM-only được chốt sau fail-fast này.

Chi tiết rationale chọn model, coin, comparator và phạm vi incremental value nằm tại `paper/working/audits/LLM_Only_Closure_v21.md`.

## Diễn giải đối với Tech+LLM

Các câu “dừng trước Tech+LLM” trong protocol lịch sử là stop rule của chính candidate LLM-only đó: không được dùng output/gate thất bại để chọn threshold hoặc tự mở overlay. Chúng không phải bằng chứng rằng mọi conditional hybrid overlay đều bất khả thi. Kể từ amendment này, Tech+LLM dùng protocol độc lập tại `paper/working/protocols/Tech_LLM_Conditional_Overlay_Protocol_v1.md`; LLM-only là negative control, không phải vé vào cửa.
