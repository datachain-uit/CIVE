# HYB-010 — nguồn gốc thiết kế thực tế

HYB-010 không được hình thành độc lập trước mọi kết quả. Thiết kế này xuất hiện sau khi dự án đã xem outcome của các HYB trước và nhận ra rằng tín hiệu LLM có thể mang incremental value qua việc giảm một số thước đo rủi ro, dù những policy giảm exposure ban đầu làm mất lợi nhuận.

## Chuỗi bằng chứng dẫn đến HYB-010

1. **HYB-001** làm closed-trade MDD giảm từ `5,2883%` xuống `4,7886%`, nhưng compounded net return giảm từ `+239,0022%` xuống `+111,4220%`. Kết quả này cho thấy giảm exposure có thể giảm rủi ro đo được, đồng thời cảnh báo rằng attenuation quá mạnh làm mất phần lớn return.
2. **HYB-007** cho thấy worst-bar cải thiện `0,3076` điểm phần trăm với CI 95% dương và ES10 cluster cải thiện từ `-3,0630%` lên `-1,7897%`, đồng thời vượt placebo trên các endpoint rủi ro. Mean net delta vẫn âm. Kết quả này xác nhận incremental value theo chiều downside risk trong mẫu historical, nhưng policy chưa chuyển được giá trị đó thành lợi nhuận.
3. **HYB-009** giữ cùng Tech-Control và sizing pipeline rồi thay representation. CryptoBERT là model duy nhất trong audit mô tả tốt hơn Tech, shuffled weight và constant-0,75 trên cả closed-trade MDD, ES10 và worst trade. Đây là lý do thực tế CryptoBERT được chọn cho HYB-010; lựa chọn này dựa trên outcome đã xem.
4. **HYB-010** thay pure attenuation bằng bounded reallocation: giữ nguyên entry, direction, exit và execution của Tech, nhưng ánh xạ causal bearish percentile `q` thành exposure `w = 1,25 - 0,5q`. Mục tiêu là giảm vốn tương đối ở entry bearish cao và dùng phần risk budget đó để tăng có giới hạn ở entry bearish thấp.

## Phạm vi diễn giải

HYB-010 là post-outcome exploratory development. Không được mô tả HYB-010 hoặc việc chọn CryptoBERT như một giả thuyết độc lập đã đăng ký trước HYB-001/HYB-007/HYB-009. Kết quả HYB-010 có thể được dùng làm bằng chứng incremental value historical trong đúng mẫu và metric đã đánh giá. Muốn khái quát hóa, dự án phải giữ nguyên policy đã khóa và đánh giá trên một khoảng dữ liệu độc lập mới, không chọn lại model, offset hoặc bounds.

Artifact máy đọc được: `paper/input/results/hybrid/hyb010_design_lineage_postoutcome.json`.
