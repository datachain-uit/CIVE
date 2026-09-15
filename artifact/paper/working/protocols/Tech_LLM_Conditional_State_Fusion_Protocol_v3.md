# Giao thức Tech+LLM conditional state fusion v3

> Trạng thái: STAGE D v3.1 PROTOCOL DEVIATION. Evaluator không thực thi đúng feature/interaction contract đã khóa và dùng sai semantics target/cost/paired contrast; performance claim v3.1 đã bị rút. Remediation v3.2 hậu kiểm dừng ở `INSUFFICIENT_OOS_CLUSTERS` vì chỉ có 8 cluster OOS, dưới minimum 12. Stage E không được phép; chưa có bằng chứng performance hợp lệ cho HYB-003.

## 1. Câu hỏi và khoảng trống

HYB-003 hỏi liệu trạng thái văn bản có tạo **giá trị quyết định gia tăng sau chi phí** so với một mô hình chỉ dùng trạng thái Tech hay không. Comparator chính không còn chỉ là Tech-Control. Hai mô hình T1 và T3 phải dùng cùng target, learner, folds, ngân sách tuning và policy; khác biệt duy nhất là T3 nhận thêm text state cùng các interaction đã đăng ký.

HYB-001 và HYB-002 không trả lời câu hỏi này. HYB-001 dùng text để veto/downsize tại entry và giữ opportunity cost đến exit. HYB-002 dùng nhãn sự kiện âm để giảm exposure một bar nhưng không điều kiện hóa theo trạng thái Tech hoặc cơ chế kinh tế của headline. Audit replay độc lập đã tái tạo 24/24 shadow trade với sai số thành phần tối đa dưới `5e-9` và khôi phục gần như đúng tuyệt đối mean/CI của HYB-002. Do đó, kết quả âm không phải do phép suy ngược quantity. Audit ngữ nghĩa đồng thời cho thấy bucket `liquidation_leverage` đã gom các tin về bankruptcy, withdrawals, token unlock và một headline nói rõ Bitcoin shorts bị thanh lý; nhãn `direction=negative` không xác định đúng tác động lên một vị thế long.

Nguồn máy đọc được của các phát hiện trên là `paper/input/results/hybrid/tech_llm_intratrade_shock_shield_v2_replay_audit.json`. Đây là audit hậu nghiệm, không phải validation của HYB-003.

## 2. Kiến trúc và các arm có kiểm soát

- **T0 — Tech-Control:** execution đã khóa, không có learned overlay.
- **T1 — Tech-state-only:** mô hình action-value chỉ dùng trạng thái vị thế và thị trường có sẵn tại thời điểm quyết định.
- **T2 — Text-only:** ablation chẩn đoán, không phải comparator chính.
- **T3 — Tech-state + text-state:** cùng mô hình và ngân sách với T1, bổ sung text state nhân quả cùng interaction đã đăng ký.

Primary contrast là `T3 - T1`. Contrast này cô lập phần giá trị do text mang thêm sau khi đã kiểm soát trạng thái Tech. System contrast là `T3 - T0`; nó kiểm tra liệu phần gia tăng đó có đủ lớn để cải thiện hệ thống thật sự sau phí, slippage và funding hay không. HYB-003 chỉ được gọi là có incremental system value khi đồng thời vượt cả hai contrast.

## 3. Đơn vị quyết định và quyền hạn

Một observation hợp lệ là một bar 4 giờ nằm sau entry và trước shadow exit của frozen Tech-Control. Tech-Control giữ toàn quyền tạo entry, hướng long, universe, sizing cơ sở và exit. HYB-003 chỉ chọn exposure `w_t ∈ {0,5; 1,0}` trong một bar. Nếu shadow trade còn mở ở mốc kế tiếp thì exposure trở lại `1,0`; nếu shadow Tech thoát, mọi arm thoát cùng timestamp và reason.

Thứ tự sự kiện là: `shadow rebalance exit → restore nếu cần → overlay action mới → funding → shadow intrabar stop → close mark`. Missing/error hoặc text pressure không xác định luôn fallback về `w_t=1,0`.

## 4. Target căn theo quyết định

Target chính là chênh lệch net utility phản thực giữa exposure `0,5` và `1,0` từ open hiện tại đến open kế tiếp hoặc shadow exit sớm hơn. Hai nhánh dùng cùng market path, shadow lifecycle và execution semantics. Net utility trừ adverse execution, fee và funding; drawdown được đánh giá riêng thay vì gộp vào một trọng số utility có thể tùy chỉnh.

Target này đo trực tiếp lợi ích cận biên của hành động mà overlay được phép thực hiện. Nó thay thế target hướng thị trường vô điều kiện và tránh việc một headline “xấu” tự động đồng nghĩa với giảm vị thế long.

## 5. Feature contract

T1 dùng asset identity, tuổi trade, return từ entry, khoảng cách đến stop theo ATR, ATR/price, các return/range quá khứ 4h–24h, funding hiện tại/quá khứ và frozen rank/momentum score nếu có thể materialize nhân quả.

Text state của T2/T3 phải trả lời tác động lên vị thế đang giữ, không chỉ sentiment:

- asset và phạm vi ảnh hưởng;
- áp lực lên vị thế long: adverse, supportive, two-sided hoặc unknown;
- cơ chế: forced-long-selling, forced-short-buying, solvency, security-loss, protocol-outage, legal-restriction, flow-demand hoặc other;
- giai đoạn: rumor, initial-announcement, escalation, ongoing, resolution hoặc retrospective;
- phân phối horizon 4h, 12h, 24h và 72h;
- novelty so với thông tin đã quan sát trước đó;
- số nguồn độc lập, confidence và reliability của extraction.

Không được dùng `direction=negative`, generic sentiment hoặc `event_type` đơn lẻ để tạo action. Unknown và two-sided không được tự động ánh xạ thành adverse. Tin trùng sự kiện phải được deduplicate theo first availability; event state chỉ được decay tiến về phía trước.

Các interaction T3 được giới hạn trước ở: pressure × distance-to-stop/ATR; novelty × trade age; stage × recent realized range; 4h horizon mass × action horizon; asset scope × held asset. Không được bổ sung interaction sau khi đọc metric HYB-003.

## 6. Learner và policy

T1 và T3 dùng regularized linear conditional action-value model với calibrated uncertainty. Mọi lựa chọn regularization và deadband nằm trong expanding training fold; T3 không được có ngân sách tuning lớn hơn T1. Action `0,5` chỉ được chọn khi ước lượng net advantage vượt toàn bộ round-trip cost đã đăng ký cộng uncertainty margin đã khóa. Nếu không, policy abstain và giữ `1,0`.

Thiết kế này ưu tiên khả năng quy thuộc incremental value. Một end-to-end agent có memory/tool/reflection có thể thay đổi nhiều thành phần cùng lúc nhưng không cô lập được phần đóng góp của text trong điều kiện dữ liệu hiện tại.

## 7. Split, suy luận và gate

Tất cả split phải theo thời gian với embargo ít nhất bằng target horizon tối đa cộng một bar. Inference bootstrap theo shadow-trade cluster; không xem 525 decision row hậu-entry là 525 quan sát độc lập vì chúng nằm trong tối đa 24 trade. Minimum cluster count và minimum detectable effect phải được tính ở Stage B rồi freeze trước evaluation.

Development PASS yêu cầu đồng thời:

1. cận dưới CI 95% cluster-bootstrap của `T3-T1` lớn hơn 0;
2. cận dưới CI 95% cluster-bootstrap của `T3-T0` lớn hơn 0 sau chi phí;
3. T3 có contrast net dương ở ít nhất 2/3 fold thời gian;
4. T3 thắng timestamp-shuffled, metadata-only và delayed-text placebos;
5. intrabar MDD của T3 không xấu hơn T0 theo một định nghĩa đã freeze;
6. effective trade clusters đạt minimum do power gate xác định.

Nếu chỉ `T3-T1` PASS nhưng `T3-T0` FAIL, text có incremental predictive/decision information so với risk model nhưng chưa tạo system value. Nếu power gate FAIL, trạng thái là `INSUFFICIENT_DATA`, không phải bằng chứng text vô ích.

## 8. Trình tự thực thi

1. **Stage A — Data:** materialize causal Tech-state panel và text-state schema; audit timestamp, side/stage, deduplication, missing/error và hash.
2. **Stage B — Power:** đo số cluster, prevalence của text state và MDE trước khi fit/evaluate T3.
3. **Stage C — Freeze:** khóa exact features, target, learner, folds, costs, deadband, placebos, assignments và mọi SHA-256.
4. **Stage D — Development:** chạy T0/T1/T2/T3 trên vùng lịch sử đã xem; kết quả chỉ là exploratory development.
5. **Stage E — Confirmation:** chỉ candidate development PASS mới được đăng ký sealed prospective holdout với ngày bắt đầu mới; không backfill ngày đã qua.

Thiết kế máy đọc được nằm tại `paper/input/results/hybrid/tech_llm_conditional_state_fusion_v3_design.json`. Stage A đã materialize 525 decision row thuộc 23 trade cluster và 2.534 headline-context; reliability Stage 1 PASS 96/96, full extraction PASS 2.534/2.534 và Stage B power gate PASS. Stage C đã freeze, nhưng Stage D v3.1 lệch contract; remediation v3.2 chỉ có vai trò chẩn đoán hậu kiểm và không khôi phục trạng thái predeclared của candidate.

## 9. Giới hạn hiện tại

[ĐÃ CÓ: text-state extractor v3 với schema held-long pressure/mechanism/stage/horizon/scope/confidence; Stage 1 PASS 96/96 ở cả hai run.]

[ĐÃ CÓ: full text-state extraction v3.1 — 2.534/2.534 record PASS, 0 lỗi schema, 14 fallback (ngưỡng 260); gate SHA-256 `7fc88ef5`.]

[ĐÃ CÓ: causal Tech-state panel có exact counterfactual action labels và data audit; 525 decision row, 23 eligible trade cluster.]

[ĐÃ CÓ: Stage B power audit PASS — 23 cluster, 16 text-new cluster, 17 applicable cluster; MDE all-decision 0,001032 < median overlay cost 0,001146.]

[ĐÃ CÓ: Stage C freeze predeclaration — khóa 13 T1 features, 12 T3 text features, 6 interaction đăng ký, Ridge learner, 3 fold với embargo 76h, deadband rule, 3 placebo, MDD definition và 6 điều kiện PASS. SHA-256 `ccfd5ffb`.]

[ĐÃ CÓ: Audit Stage D v3.1 — `PROTOCOL_DEVIATION_RESULT_NOT_REPORTABLE_AS_FROZEN_STAGE_D`. Artifact: `paper/input/results/hybrid/hyb003_stage_d_v3_1_protocol_deviation_audit.json`.]

[ĐÃ CÓ: Remediation v3.2 hậu kiểm — 170 OOS decision row thuộc 8 cluster; trạng thái `INSUFFICIENT_OOS_CLUSTERS`; không có action ở cả ba arm. Artifact này không phải predeclared result.]

[THIẾU: một candidate mới với panel/feature contract nhất quán và sealed future holdout. Stage E hiện không được phép.]
