# Phương pháp thực nghiệm và truy vết backtest

> Cập nhật đến 2026-09-10. Tech-Control đã khóa; lịch sử LLM-only là negative evidence; HYB-001 và HYB-002 đều FAIL trong exploratory development; HYB-003 mới hoàn tất Stage A và kiểm tra extractor Stage 1, chưa có kết quả hiệu năng; sealed holdout chưa bắt đầu.

## 1. Câu hỏi nghiên cứu

Đánh giá thị trường đa nguồn do AI tạo ra có cung cấp giá trị giao dịch gia tăng có ý nghĩa thống kê so với mô hình định lượng truyền thống trong các chế độ thị trường tiền mã hóa khác nhau hay không?

Đại lượng cần đo không phải “bot nào kiếm nhiều tiền hơn”, mà là phần thay đổi khi chỉ thêm thành phần AI trong khi giữ các thành phần khác cố định:

`Giá trị gia tăng = Hiệu suất(Tech + LLM) - Hiệu suất(Tech-only)`

Tech+LLM so với Tech-only là so sánh chính. LLM-only là ablation chẩn đoán xem LLM có thông tin độc lập hay chỉ bổ trợ Tech.

Hai giả thuyết được kiểm định độc lập. LLM-only FAIL bác bỏ standalone-alpha claim trong phạm vi candidate đó nhưng không tự động cấm Tech+LLM. Tech+LLM chỉ được chạy theo một predeclaration riêng, trong đó LLM không tạo/đảo chiều giao dịch và comparator chính là frozen Tech-only.

## 2. Ba nhánh và các biến phải giữ nguyên

| Nhánh | Vai trò | Trạng thái |
|---|---|---|
| Tech-only | Control | Đã khóa `tech-control-v1`, chưa live |
| LLM-only | Diagnostic | Development; chưa vượt predictive gate |
| Tech+LLM | Treatment chính | HYB-001/002/004/006/009 FAIL; HYB-003 thiếu OOS cluster; HYB-005 thiếu effective sample; HYB-007 có tail-risk attenuation nhưng formal gate FAIL; HYB-008 conditional downside information FAIL trước policy |

Các nhánh phải dùng cùng universe point-in-time, calendar, cutoff, next-4H-open fill, vốn, gross exposure 1x, stop/trailing, fee, spread, slippage, impact, funding, delisting và failure policy. Tổng chi phí có thể khác vì turnover khác, nhưng mô hình chi phí phải giống nhau.

## 3. Nền tảng phương pháp

| Thành phần | Nguồn nền tảng | Phần dự án giữ lại | Mức độ tương đương |
|---|---|---|---|
| Technical-rule search | Hudson & Urquhart (2021) | Họ rule, OOS, cost và kỷ luật multiple testing | Paper-inspired, không replication |
| Momentum và universe | Liu et al. (2022); Fieberg et al. (2025) | Cross-section point-in-time và xếp hạng trend/momentum | Transfer hẹp |
| Stop/risk | Sadaqat & Butt (2023) | Stop là ablation riêng | Không sao chép threshold paper |
| Liquidity shock | Tang & Wang (2022) | Proxy Amihud causal | Transfer thất bại, gate tắt |
| Futures basis | Chi et al. (2023) | Bybit/OKX perpetual premium | Transfer thất bại; dated futures khác perpetual |
| Order flow | Anastasopoulos et al. (2026) | Binance taker-flow một sàn | Transfer thất bại; không phải world flow |
| LLM sentiment | Kirtac & Germano (2024) | Text → score → subsequent return, có cost | Development, CI cắt 0 |
| Multi-source sentiment | Bennett et al. (2024) | OOS và source ablation | Không replication dữ liệu MarketPsych |
| Memory/multimodal | FinMem, FinAgent | Temporal split, repeat, fusion/ablation | Chưa triển khai đầy đủ |
| Multi-agent BTC | Jung & Lee (2026) | Multi-source và rationale audit | Backtest paper chỉ 3 ngày, không làm benchmark hiệu quả |

Một transfer thất bại không phủ định bài báo gốc; nó chỉ cho thấy kết quả không chuyển sang contract, universe, frequency, thời kỳ hoặc execution của dự án.

## 4. Nguồn dữ liệu và provenance

| Lớp dữ liệu | Nguồn hiện hành | Quy tắc sử dụng |
|---|---|---|
| OHLCV/turnover | Bybit V5 Kline | Lưu cache, retrieval time, schema và hash |
| Vòng đời hợp đồng | Bybit Instruments Info | Dùng cả `Trading` và `Closed`, launch/delivery time |
| Funding | Bybit Funding History | Dùng settled timestamp thật; không backfill bằng giá trị tương lai |
| Open interest/premium | Bybit/OKX official endpoints | Chỉ làm transfer test khi coverage hợp lệ |
| Taker-flow proxy | Binance USD-M kline | Gắn nhãn proxy một sàn, không replication world flow |
| Tin tức LLM | CryptoVision v2 | Giữ publication/availability time, URL, hash và raw output |
| Official text archives | Snapshot RSS/tài liệu cơ quan chính thức dùng trong v14--v16 | Outcome-blind; dừng trước target khi coverage hoặc targetability không đạt |
| On-chain/liquidation | Chưa khóa nguồn lịch sử | Không tái tạo từ dashboard hiện tại hoặc OHLCV |

Nguồn chính thức của sàn chỉ là điều kiện cần. Sử dụng ở mức nghiên cứu còn cần snapshot bất biến, causal availability timestamp, checksum, missing-data policy và quy trình tải có thể tái lập.

## 5. Kết quả development đang được phép sử dụng

### Tech-Control

Artifact freeze hiện trỏ tới cấu hình lifecycle hardened: universe top-5 thanh khoản point-in-time, top-1 momentum 20 ngày, stop 3 ATR, trailing 4 ATR, 1x, semantics `open_funding_intrabar_v2`.

| Kịch bản | Return | MDD | Fills | Fold dương |
|---|---:|---:|---:|---:|
| Base | +217,48% | 10,56% | 62 | 6/8 |
| Stress | +204,37% | 11,46% | 62 | 6/8 |
| Harsh | +186,69% | 12,71% | 62 | 6/8 |

Hai fold cuối vẫn âm `-0,33%` và `-3,33%`. Kết quả v1 `+168,62% / 66 fills` được giữ cho audit nhưng đã bị semantics v2 thay thế.

### LLM-only

Llama 3 single run trả `+36,35%`, MDD `23,22%`; consensus hai run trả `+32,75%`, cùng MDD. Tuy nhiên CI 95% của Pearson và long-minus-flat đều cắt 0. Các challenger Qwen/Ministral qua reliability nhưng không qua predictive calibration; các model fail reliability được dừng trước outcome. Event extractor Ministral v3.9 hoàn tất 39.393/39.393 record, nhưng các predictive return/risk/4h transfer đủ sample trên BTC, ETH và SOL không xác nhận semantic increment. GLM-4 9B Q3_K_M là challenger cuối và fail-fast ở Stage 1 do severity ngoài [0,1].

Chuỗi predictive LLM-only dừng tại v21. Diagnostic task-compatibility LLM-086 dùng exact GLM artifact trên daily JSON contract đã fail trước outcome và không mở lại chuỗi predictive. Được phép claim giá trị vận hành/chẩn đoán và negative evidence trong đúng phạm vi; không được dùng return Llama làm alpha, không nói LLM vô dụng và không nói v19 đã kiểm tra Tech drawdown/cost vì protocol dừng trước overlay.

### Tech+LLM

HYB-001 và HYB-002 đều là exploratory development và đều FAIL theo primary gate đã đăng ký. HYB-001 làm giảm paired net return trên 24 trade-entry opportunity. HYB-002 materialize 23 intervention trên 13 shadow trade nhưng có paired net CI hoàn toàn âm, gross mean âm và chỉ 1/3 fold dương. Hai kết quả này bác bỏ đúng representation-policy đã kiểm tra, không bác bỏ mọi hybrid architecture.

HYB-003 chuyển câu hỏi sang conditional state fusion với bốn arm `T0/T1/T2/T3`; estimand chính là `T3-T1`. Full extraction v3.1 đạt 2.534/2.534 record và Stage B power gate PASS. Tuy nhiên evaluator Stage D v3.1 lệch frozen contract nên performance claim bị rút; remediation v3.2 chỉ có 8 OOS trade cluster dưới minimum 12 và dừng với `INSUFFICIENT_OOS_CLUSTERS`.

HYB-004 Bennett adaptive transfer FAIL và chỉ là post-outcome remediation. HYB-005 dừng outcome-free vì thiếu two-position/active day. HYB-006 đủ 974 active pair-day nhưng paired net delta CI cắt 0 và chỉ 2/5 fold dương. HYB-007 historical đạt sample gate 186 bucket/113 cluster rồi mới evaluation. LLM attenuation cải thiện worst-bar và ES10, nhưng mean cluster net delta âm, CI cắt 0, 1/5 fold dương và non-inferiority FAIL; do đó chỉ claim tác dụng giảm tail risk cục bộ, không claim formal incremental value.

HYB-008 kiểm tra trực tiếp liệu event semantics có nhận biết downside tốt hơn Tech state hay không trước khi cho phép policy. Sample gate PASS 1.008 row; trên 692 row expanding OOS, event Brier 0,09331 xấu hơn Tech 0,08829 và generic LLM 0,09119, AUC event 0,50097, paired improvement CI cắt 0 và event thắng generic 0/5 fold. Stage A FAIL; không mở Stage B hoặc backtest.

HYB-009 là controlled model-substitution ablation trên canonical Tech-Control, không phải external hybrid-paper comparator. Threshold v1 dừng outcome-free vì thiếu active sample; continuous v1.1 được khóa trước PnL và đủ 24 opportunity cho FinBERT, CryptoBERT, Ministral. Cả ba làm mean paired net/gross âm, CI95 net hoàn toàn âm và 0/3 fold, nên economic incremental value FAIL. CryptoBERT có risk attenuation mô tả vượt shuffled/constant sizing trên MDD, ES10 và worst trade nhưng audit này hậu outcome và lợi nhuận giảm; chỉ được dùng để tạo giả thuyết risk-aware tiếp theo. GLM daily challenger fail reliability trước full inference và không vào HYB.

## 6. Endpoint và suy luận cho thí nghiệm cuối

Endpoint chính: chênh lệch paired net return hoặc utility của Tech+LLM so với Tech-only trên cùng timestamp, kèm effect size và CI.

Báo cáo tối thiểu:

- net/annualized return, Sharpe, Sortino và MDD;
- turnover, fee, execution cost, funding và capacity proxy;
- đóng góp theo bull/bear/sideway đã khai báo trước;
- paired moving-block bootstrap trên chuỗi return difference;
- DM chỉ khi so sánh loss series dự báo được định nghĩa rõ;
- SPA/Reality Check hoặc DSR khi đã thử nhiều prompt/model/source;
- interaction test theo regime, không săn significance trong nhiều nhóm nhỏ.

Mặc định hai phía:

- `H0`: AI-derived assessment không tạo giá trị giao dịch ròng gia tăng so với Tech-only.
- `H1`: Giá trị giao dịch ròng gia tăng khác 0.

## 7. Sealed holdout

Cửa sổ từng dự kiến bắt đầu 2026-08-14 không được kích hoạt vì chưa đủ freeze. HYB-001, HYB-002, HYB-004, HYB-006 và formal gate của HYB-007 historical đã FAIL; HYB-003 thiếu OOS cluster; HYB-005 thiếu effective sample. Không lineage nào được đưa vào sealed holdout. Bản HYB-007 prospective tạo do hiểu sai yêu cầu đã được rút trước model/outcome và không được dùng làm bằng chứng.

## 8. Checklist trước final run

- [x] Khóa Tech-Control và hash artifact/mã nguồn.
- [x] Có sổ cái tổng hợp Tech, LLM và transfer test.
- [x] Chốt LLM-only là diagnostic/negative control, không phải vé vào cửa của Tech+LLM.
- [x] Khóa kiến trúc HYB-003 và tạo decision/context table Stage A theo quy tắc outcome-blind.
- [x] Kiểm tra extractor HYB-003 Stage 1; hai lần chạy đều đạt 96/96 record.
- [x] Hoàn tất full extraction HYB-003 v3.1: 2.534/2.534 record; model, prompt, schema và missing/error rule có artifact.
- [x] Khóa fusion rule HYB-001; candidate này đã FAIL và không được retune trên cùng outcome.
- [x] Khóa kiến trúc, event contract, action duration, comparator và gate HYB-002 ở mức thiết kế.
- [x] Materialize runner, replay inputs và exact assignment HYB-002 trước khi đọc outcome; 23 intervention trên 13 trade.
- [x] Evaluate HYB-002: FAIL do paired net CI hoàn toàn âm, gross âm và chỉ 1/3 fold dương.
- [ ] [THIẾU] Materialize intrabar MDD đúng protocol; closed-trade MDD hiện chỉ là proxy. Việc bổ sung không thể đảo FAIL đã được quyết định bởi primary gates.
- [x] Khóa power/economic gate và Stage C HYB-003; Stage D v3.1 bị rút do evaluator lệch contract, remediation v3.2 dừng vì 8 < 12 OOS cluster.
- [x] Rút bản HYB-007 prospective tạo sai phạm vi trước model/outcome; giữ artifact dưới tên `WITHDRAWN_SCOPE_ERROR` để bảo toàn audit trail.
- [x] Chạy HYB-007 historical đúng thứ tự freeze → outcome-free sample PASS → evaluation; formal incremental-value gate FAIL nhưng ghi nhận tail-risk attenuation cục bộ.
- [x] Chạy HYB-008 đúng thứ tự freeze → outcome-free sample PASS → Stage A information FAIL; dừng trước policy/backtest và không retune.
- [ ] Đăng ký sealed holdout tương lai tối thiểu 180 ngày.
- [ ] Chạy base/stress/harsh cho mọi nhánh sau khi mở holdout.
- [x] Thực hiện paired inference exploratory HYB-001 với bốn placebo đã đăng ký; chưa có xác nhận trên sealed holdout.
- [ ] Không phê duyệt live chỉ từ kết quả luận văn.

## 9. Nguồn chính

- https://link.springer.com/article/10.1007/s10479-019-03357-1
- https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119
- https://www.sciencedirect.com/science/article/pii/S1042444X22000019
- https://onlinelibrary.wiley.com/doi/10.1002/fut.22425
- https://www.sciencedirect.com/science/article/pii/S1386418126000029
- https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178
- https://doi.org/10.1016/j.frl.2024.105227
- https://doi.org/10.1016/j.gfj.2024.100945
- https://bybit-exchange.github.io/docs/v5/market/kline
- https://bybit-exchange.github.io/docs/v5/market/funding/history
- https://bybit-exchange.github.io/docs/v5/market/instrument
