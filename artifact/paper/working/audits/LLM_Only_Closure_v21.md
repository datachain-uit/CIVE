# Kết luận nhánh LLM-only đến v21

> Addendum 2026-09-12: LLM-086 là diagnostic task-compatibility hậu closure cho exact GLM-4 9B Q3_K_M trên frozen daily JSON contract. Model fail-fast ngay record đầu trước outcome/full inference/HYB; diagnostic này không mở lại chuỗi predictive và không thay đổi kết luận v21.

> Chốt ngày 2026-09-11. Nguồn sự thật là artifact JSON, predeclaration và sổ cái thí nghiệm. Tài liệu này không mở lại threshold, model, coin hoặc outcome đã bị gate dừng.

## Kết luận ngắn

Chuỗi thí nghiệm hiện tại chưa xác nhận predictive incremental value hoặc economic incremental value của LLM-only trong bất kỳ thiết kế, asset, corpus và horizon nào đã đủ điều kiện đánh giá. Kết luận này hẹp hơn câu “LLM không có giá trị”.

LLM đã tạo hai dạng giá trị khác:

1. Giá trị vận hành và biểu diễn: extractor v3.9 của Ministral hoàn tất 39.393/39.393 bài theo schema đã khóa. Output này cho phép xây dựng biến sự kiện, audit scope theo asset và thực hiện các transfer test có thể tái lập.
2. Giá trị chẩn đoán: chuỗi gate xác định nơi pipeline thất bại do schema, độ lặp, provenance, effective sample, target coverage hoặc thiếu incremental prediction. Các kết quả âm ngăn việc biến tương quan hoặc backtest development thành claim alpha.

Hai dạng giá trị trên không đồng nghĩa với cải thiện Tech, dự báo return/risk tốt hơn comparator, giảm drawdown hoặc tạo lợi nhuận sau chi phí.

## Incremental value được đo như thế nào

| Tầng | Câu hỏi | Comparator cần thiết | Kết luận hiện tại |
|---|---|---|---|
| Vận hành | Model có tạo output đúng schema, ID, evidence và lặp lại được không? | Contract và hai run độc lập | Có ở một số model/version; v3.9 full extraction PASS |
| Biểu diễn/dự báo | Trường semantic do LLM tạo có giảm loss hơn baseline yếu hơn không? | Prior, market-only, metadata-only hoặc generic LLM tùy protocol | Chưa được xác nhận ở mọi gate đủ mẫu đã chạy |
| Kinh tế | Output LLM-only có tạo action/backtest sau cost tốt hơn comparator không? | Strategy không dùng semantic increment, cùng execution/cost | Không được mở ở các lineage gần đây vì predictive gate FAIL |
| Chẩn đoán | Thí nghiệm có xác định được giới hạn dữ liệu/mô hình một cách tái lập không? | Predeclaration, sample audit và stop rule | Có |

Trong v19 và v20, metadata-only vẫn phụ thuộc vào bước chọn bài theo affected_assets do LLM sinh. Vì vậy comparator này đo phần semantic field tăng thêm sau asset selection; nó không phải pipeline hoàn toàn không dùng LLM. Một pure no-LLM asset-metadata comparator cần một protocol tương lai riêng.

## Logic chọn model

### Nhóm direct-direction ban đầu

- Llama 3 được chọn làm model local khởi đầu vì có thể chạy trên phần cứng dự án và tạo output đủ ổn định ở pilot. Full run cho phép phát hiện bất định giữa hai lần chạy và kiểm tra calibration.
- Qwen 2.5 7B và Qwen 3 8B được chọn làm challenger khác họ/khác phiên bản, dùng cùng contract để tách lỗi model khỏi lỗi dữ liệu. Cả hai qua reliability nhưng không qua predictive calibration.
- Gemma 3 4B, DeepSeek-R1 7B, Nemotron 3 Nano 4B và Llama 3.1 8B mở rộng độ đa dạng kiến trúc/kích thước. Stop gate loại chúng ở reliability hoặc repeatability trước full inference.
- FinGPT ChatGLM2 được thử vì gần miền tài chính hơn model tổng quát, nhưng Stage 1 reliability thất bại. CryptoBERT được thử như classifier sentiment chuyên miền và qua inference, nhưng predictive CI không xác nhận edge.
- FinMem được kiểm tra ở implementation chính thức vì memory-agent phù hợp câu hỏi nghiên cứu. Dự án dừng tại feasibility do thiếu model input và credential cần thiết; không gọi đây là reproduction thất bại.

### Nhóm event extractor

- Ministral 3 8B được giữ cho v3 vì đã thể hiện reliability tốt trong contract trước đó và phù hợp phần cứng local. Các v3-v3.8 là sửa lỗi contract/post-processing có lưu dấu; không được tính như nhiều phép thử predictive độc lập.
- V3.9 là phiên bản đầu tiên hoàn tất full extraction. Việc hoàn tất schema chỉ cấp quyền xây panel predictive, không cấp quyền claim alpha.
- GLM-4 9B Q3_K_M là challenger cuối vì thuộc một họ chưa thử, artifact 5,1 GB phù hợp GPU 6 GB và có thể khóa digest local. Model fail-fast ở LLM-085 khi severity vượt miền [0,1].

### Model không chạy trong vòng chốt

- GLM-5.2, MiniMax-M3 và Kimi-K3 không có artifact local phù hợp đã được xác minh trên phần cứng hiện tại tại thời điểm khóa.
- Chạy bản API/cloud sẽ phát sinh chi phí theo usage, thay đổi điều kiện tái lập và không còn là cùng deployment local. Đây là hướng phát triển, không phải phần thiếu cần lấp để đảo kết luận hiện tại.
- Sau LLM-085 không tiếp tục model shopping. Model mới chỉ được mở bằng một protocol tương lai có rationale độc lập, resource gate và family-wise decision rule trước khi xem outcome.

## Logic chọn coin và horizon

- BTC là asset gốc vì corpus, target, Tech baseline và execution data của dự án đầy đủ nhất. Các predictive test BTC ở return 24 giờ, volatility 24 giờ và response 4 giờ đều không xác nhận semantic increment.
- ETH là transfer chính đầu tiên vì liên quan trực tiếp đến thiết kế Bennett và có 5.341 direct event trên 1.000 ngày. V17 đủ sample nhưng event-conditioned thua generic ở predictive MSE.
- SOL là primary cùng ETH trong v19-v20 vì có coverage cao thứ hai trong altcoin. V19 dừng outcome-free vì fold đầu có 98 event-day, dưới ngưỡng 100 đã khóa. V20 đủ 1.014 event và 876 bucket để đánh giá, nhưng semantic event không hơn comparator.
- XRP và BNB chỉ là conditional candidates vì coverage trực tiếp thấp hơn. XRP không đạt các ngưỡng sample v19-v20. BNB còn thiếu cả bar artifact trong hai screen, nên dừng trước target.
- Không hạ ngưỡng sau khi thấy audit. Một lần chạy tương lai chỉ hợp lệ khi có thêm dữ liệu/provenance và predeclaration mới.

## Hai transfer test cuối

### V19 multi-coin risk transfer

ETH là asset duy nhất qua screen. Trên 699 dự báo OOS, event-conditioned có MSE volatility 24 giờ 0,000387593, xấu hơn metadata 0,000368793 và generic 0,000374049. Chênh MSE baseline trừ event âm đối với cả hai comparator; event thắng 0/5 fold so với metadata và 1/5 so với generic. Với adverse excursion, event cũng xấu hơn cả hai comparator và thắng 0/5 fold.

V19 vì vậy dừng trước risk overlay lên Tech. Drawdown và cost chưa được đánh giá: đây là hệ quả của stop rule, không phải dữ liệu bị thiếu ngẫu nhiên và không phải bằng chứng overlay chắc chắn thất bại.

### V20 short-horizon event response transfer

ETH và SOL qua screen; XRP và BNB dừng outcome-free. ETH có 1.054 prediction OOS; event MSE 0,000240564, xấu hơn metadata 0,000237854 và generic 0,000239099, chỉ thắng 2/5 fold so với mỗi comparator. SOL có 622 prediction OOS; event MSE 0,000446401, xấu hơn metadata 0,000414946 và generic 0,000430266, chỉ thắng 1/5 fold. Pearson CI của event ở cả hai asset đều cắt 0.

V20 dừng trước action/backtest. Kết quả không phủ định khả năng event response ở corpus khác, model khác hoặc prospective release stream.

## GLM-4 9B Q3_K_M

LLM-085 đã khóa model digest f61310a4c5448541c2e684787bad318158ac5209a5abab3cd0719238535c10c6 và config SHA-256 811ceeb29d7fe53294b9c8f491cd1dbf1b87c329855275550ba0f35e646ab61a trước inference. Run 1 thử 8/114 record: 4 success và 4 error. Cùng một batch trả severity 2 hoặc 3 trong khi contract yêu cầu [0,1], nên số success tối đa chỉ còn 110/114 và gate fail-fast. Run 2, full extraction, outcome join và predictive test không được chạy.

Đây là operational failure của exact model artifact dưới exact frozen contract. Nó không chứng minh GLM-4 nói chung không hiểu tin tài chính, và không cung cấp predictive evidence dương hoặc âm.

## Phạm vi kết luận dùng trong luận văn

Được phép viết:

- Pipeline LLM tạo được representation sự kiện có cấu trúc và tái lập ở v3.9.
- Trong các predictive test đủ điều kiện đã chạy, semantic increment không cải thiện comparator đã đăng ký trước.
- Effective-sample và provenance gate đã loại một số asset/source trước outcome, giảm nguy cơ chọn kết quả thuận lợi.
- Nhánh LLM-only là negative control có kết quả âm trong phạm vi kiểm định, không phải bằng chứng phổ quát.

Không được viết:

- LLM không có giá trị.
- LLM chắc chắn không thể cải thiện Tech.
- V19 đã kiểm tra và thất bại về drawdown/cost.
- Metadata comparator v19-v20 hoàn toàn không dùng LLM.
- Kết quả development là validation, sealed holdout hoặc live performance.

## Hướng phát triển đã tách khỏi claim hiện tại

1. Thu thập prospective official event stream có timestamp/version chứng minh được và đánh giá trên holdout chưa xem.
2. Xây pure no-LLM asset-selection/metadata comparator để tách giá trị chọn asset khỏi giá trị semantic fields.
3. Chỉ mở Tech risk overlay khi một risk model tương lai vượt predictive gate; khi đó predeclare riêng utility, drawdown và incremental cost.
4. Tích lũy thêm direct-event coverage cho SOL/XRP/BNB rồi audit lại bằng ngưỡng mới được khóa trước outcome; không tái dùng ngưỡng hậu kiểm.
5. Nếu thử model local/API thế hệ mới, khóa trước family, exact artifact/API version, budget, prompt, sample, multiplicity và stop rule.
6. Giữ sealed holdout chưa mở cho một candidate Tech+LLM có rationale độc lập; không dùng nó để cứu một lineage LLM-only đã fail.

## Quyết định chuyển pha

Nhánh LLM-only dừng ở v21. Không chạy thêm model, coin, target hoặc backtest trong lineage hiện tại. Công việc tiếp theo chuyển sang Tech+LLM, nơi estimand là paired incremental decision value so với frozen Tech comparator; kết quả LLM-only chỉ đóng vai trò negative control và nguồn feature đã audit.
