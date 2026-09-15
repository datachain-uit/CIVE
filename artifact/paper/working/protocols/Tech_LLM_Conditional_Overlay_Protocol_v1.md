# Giao thức Tech+LLM conditional overlay v1

> Trạng thái: EVALUATED — EXPLORATORY DEVELOPMENT FAIL. Policy/assignment được khóa trước evaluation tại `paper/input/results/hybrid/tech_llm_conditional_overlay_v1_predeclared.json`; kết quả nằm tại `paper/input/results/hybrid/tech_llm_conditional_overlay_v1_development.json`. Không được sửa policy hoặc mở sealed holdout từ kết quả này.

## 1. Hai giả thuyết độc lập

LLM-only kiểm tra liệu biểu diễn LLM có giá trị dự báo vô điều kiện so với đối chứng đã đăng ký hay không. Các gate LLM-only hiện có không đạt hoặc dừng trước predictive evaluation; chúng bác bỏ standalone-alpha claim trong phạm vi đã kiểm định.

Tech+LLM kiểm tra một giả thuyết khác: sau khi frozen Tech-Control đã đề xuất giao dịch, thông tin LLM có cải thiện quyết định bằng cách xác nhận, veto hoặc giảm exposure hay không. LLM-only FAIL không được diễn giải thành bằng chứng rằng interaction value bằng 0 và không còn là điều kiện cấm mở một protocol Tech+LLM độc lập.

LLM-only vẫn là negative control bắt buộc phải báo cáo. Nó không phải comparator chính và không cung cấp threshold, policy hay quyền chạy cho Tech+LLM.

## 2. Kiến trúc và quyền hạn

Tại decision timestamp `t` mà frozen Tech-Control mở một trade mới, Tech-Control tạo tín hiệu cơ sở `s_t ∈ {0, 1}` vì control hiện hành chỉ long. Overlay LLM chỉ tạo trọng số `w_t ∈ {0, 0.5, 1}`. Vị thế Tech+LLM là `h_t = w_t s_t`; trọng số được giữ đến đúng exit của trade Tech tương ứng và không được xét lại giữa vòng đời trade.

Các bất biến bắt buộc:

- Nếu `s_t = 0` thì `h_t = 0`: LLM không tạo giao dịch mới.
- `sign(h_t)` không được khác `sign(s_t)`: LLM không đảo chiều tín hiệu Tech.
- `w_t = 1` là confirm, `w_t = 0.5` là downsize và `w_t = 0` là veto.
- Lỗi hoặc thiếu output LLM dùng `w_t = 1`, đồng nghĩa quay về Tech-only và phải được ghi audit; không được âm thầm loại timestamp.
- Overlay không thay đổi universe, technical predictor, execution timing, stop-loss, trailing stop, funding logic, cost model, risk engine hoặc position limit.

Policy dùng output event-risk v3.9 đã khóa. Với mỗi sự kiện negative, adverse score bằng `relevance_weight × severity × confidence × (0,5 + 0,5 × reported_surprise)`, trong đó trọng số relevance là 1 cho `direct`, 0,5 cho `indirect` và 0 cho `none`. Score theo ngày là giá trị lớn nhất trong information set đã available lúc entry. Vì Tech-Control chỉ long, negative là polarity bất lợi. Policy đơn điệu: `w_t=1` khi score < 0,68; `w_t=0,5` khi 0,68 ≤ score < 0,76; và `w_t=0` khi score ≥ 0,76. Các ngưỡng được chọn từ audit mật độ feature tại timestamp entry, không dùng PnL.

## 3. Estimand và thiết kế paired

Comparator chính là frozen Tech-only. Trên cùng decision timestamp do Tech-Control đề xuất giao dịch, đặt `d_t = r^{net}_{Tech+LLM,t} - r^{net}_{Tech-only,t}`, trong đó hai arm dùng cùng market data, universe, execution contract, fee, slippage, funding, risk budget và position limits.

Primary estimand là paired mean net return difference trên toàn bộ decision timestamp Tech-Control đã đề xuất trong evaluation set. Cumulative net return, MDD, tail loss/adverse excursion, stop-out rate, turnover, chi phí, số veto, tỷ lệ tránh giao dịch thua, số giao dịch thắng bị veto và opportunity cost là chỉ tiêu phụ.

Đơn vị resampling là cluster quý lịch trên 24 trade-entry opportunity. Bootstrap dùng 10.000 draw, seed 20.260.909 và CI hai phía 95%. Gate yêu cầu tối thiểu 20 opportunity, tối thiểu 6 opportunity có `w_t<1`, cận dưới CI của paired mean net difference dương, paired gross mean dương, paired net difference dương ở ít nhất 2/3 fold thời gian, và primary mean lớn hơn cả bốn placebo đã đăng ký. Audit feature-only ghi nhận 24 opportunity, gồm 4 veto và 3 downsize. Không được đổi primary estimand hoặc gate sau evaluation.

## 4. Đối chứng và ablation

Mỗi evaluation phải có:

1. frozen Tech-only;
2. Tech+LLM đúng timestamp;
3. metadata-only filter có cùng mật độ hoặc cùng miền trọng số;
4. shuffled-timestamp LLM filter;
5. delayed LLM signal;
6. opposite-polarity filter khi feature contract cho phép định nghĩa không mơ hồ;
7. báo cáo gross và net sau phí, slippage và funding.

Metadata-only và opposite-polarity giữ đúng mật độ 4 veto/3 downsize. Shuffled-timestamp hoán vị assignment bằng seed 20.260.909. Delayed signal dùng adverse score của information day sớm hơn 24 giờ. Không được chọn placebo, threshold hoặc exposure schedule dựa trên cấu hình thắng.

## 5. Biên dữ liệu và trạng thái bằng chứng

Không dùng các outcome đã xem của v1–v16 để tối ưu hậu nghiệm policy rồi trình bày như kiểm định xác nhận. Một evaluation trên giai đoạn đã xem chỉ được gọi là exploratory development dù policy được đăng ký sau. Validation xác nhận cần một khoảng thời gian hoặc tập decision timestamp chưa được dùng để chọn feature, policy, threshold hay gate.

Sealed holdout chỉ được mở sau khi khóa đồng thời:

- hash frozen Tech-Control;
- corpus, availability timestamp và exclusion rule của LLM;
- model digest, prompt, schema, postprocessor và failure policy;
- feature contract, polarity alignment, `w_t` mapping và mọi threshold;
- decision set, split, primary estimand, placebo, bootstrap và gate;
- common execution, cost và risk contract.

Evaluation development được khóa trên các entry từ `2022-09-13T00:00:00Z` đến `2025-08-28T00:00:00Z`, là vùng chồng lấp giữa frozen Tech-Control và v3.9. Outcome của giai đoạn này đã được dự án xem trước đây, nên kết quả chỉ là exploratory development dù assignment hiện tại được tạo không dùng PnL. Protocol cấp quyền đúng một paired evaluation theo predeclaration đã băm; vẫn không cấp quyền mở sealed holdout.

## 6. Logic kết luận

Nếu gate paired PASS, claim tối đa là: việc tích hợp representation và policy LLM đã đăng ký như một lớp lọc có điều kiện cải thiện frozen Tech-Control trong evaluation protocol đã kiểm định.

Nếu gate FAIL, kết luận là representation và policy LLM được kiểm định chưa tạo incremental decision value cho Tech-Control. Cả hai trường hợp đều không chứng minh standalone LLM alpha, không phục hồi LLM-only và không chứng minh khả năng vận hành live.

## 7. Kết quả HYB-001 đã khóa

Evaluation có 24 opportunity và đạt hai ngưỡng sample; policy can thiệp 7 lần, gồm 4 veto và 3 downsize. Tech-only đạt compounded net return +239,0022%, còn Tech+LLM đạt +111,4220% trên cùng opportunity set. Paired mean net difference là -2,15208 điểm phần trăm mỗi opportunity, với cluster-bootstrap CI 95% [-4,82034; -0,18626] điểm phần trăm. Paired gross mean là -2,23829 điểm phần trăm và cả ba fold đều âm.

Primary policy không vượt metadata-only, shuffled-timestamp, delayed-24h hoặc opposite-polarity. Bốn veto loại một trade Tech thua và ba trade Tech thắng. Closed-trade drawdown giảm từ 5,2883% xuống 4,7886%, nhưng đây là chỉ tiêu phụ ở độ phân giải trade đóng và không đảo kết luận của estimand chính.

Trạng thái chính thức là `exploratory-development-fail`. Kết luận tối đa: representation event-risk v3.9 cùng policy ngưỡng HYB-001 chưa tạo incremental decision value cho frozen Tech-Control trong development set đã kiểm định. Không được thử lại threshold trên cùng outcome rồi trình bày như xác nhận.
