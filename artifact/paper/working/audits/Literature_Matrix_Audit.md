# Kiểm toán ma trận tài liệu

> Cập nhật: 2026-08-16. Tài liệu này hợp nhất ba nhật ký cũ: audit sơ bộ, candidate backlog và source-level audit. Hai file trùng đã được loại sau khi hợp nhất.

## Mục đích và tiêu chuẩn bằng chứng

Ma trận tài liệu là cơ sở tri thức có kiểm soát, không phải danh mục tham khảo tự động. Một record chỉ được dùng trong luận văn khi title, tác giả, venue, năm, DOI/URL và publication status đã được xác minh từ nguồn chính.

- `verified peer-reviewed`: bài journal/conference đã xác minh.
- `verified preprint`: arXiv/SSRN đã xác minh nhưng chưa peer review.
- `verified book/whitepaper`: nguồn nền tảng, không phải empirical benchmark.
- `unverified`: thiếu bằng chứng trường dữ liệu quan trọng.
- `rejected`: DOI/title sai hoặc record không truy vết được.

Google Scholar search URL không phải bibliographic evidence. Code chỉ được ghi “official” khi paper hoặc tổ chức/tác giả liên kết trực tiếp. Dataset và metric không được suy từ title hay từ một implementation bên thứ ba.

## Các lỗi lịch sử đã phát hiện

- Header `Google Scholar` và `Notes` từng bị đảo so với dữ liệu.
- Count giữa Master, Evidence và Dashboard từng dùng mẫu số khác nhau.
- `O01` là proposal/target venue, không phải publication.
- Các câu “first”, “only” hoặc số lượng paper thỏa gap từng không có search protocol đủ mạnh.
- Một số DOI từng trỏ sang bài hoàn toàn khác.

Các artifact sinh trước đợt sửa không được gọi là “100% source-verified”. Workbook hiện hành phải tính count từ cùng một filtered source-of-truth table.

## Các sửa bibliographic trọng yếu

| ID | Trạng thái xác minh | Sửa hoặc lưu ý bắt buộc |
|---|---|---|
| T01 | Đã xác minh | DeepLOB DOI `10.1109/TSP.2019.2907260`; FI-2010 dùng accuracy/recall/precision/F1, không phải trading return |
| T02 | Đã xác minh | Adv-ALSTM DOI `10.24963/ijcai.2019/810`; dữ liệu ACL18/KDD17; metric Acc/MCC |
| T03 | Đã thay record | Dùng Liu, Tsyvinski & Wu (2022), DOI `10.1111/jofi.13119` |
| T04 | Đã thay record | Dùng Helformer 2025, DOI `10.1186/s40537-025-01135-4`; DOI cũ từng trỏ bài ngân hàng |
| T09 | Đã sửa | AlphaStock DOI `10.1145/3292500.3330647`; DOI cũ trỏ paper khác |
| S07 | Đã thay record | FinSentGPT DOI `10.1016/j.irfa.2024.103291`; DOI cũ không liên quan |
| S11 | Đã xác minh | Kirtac & Germano (2024), DOI `10.1016/j.frl.2024.105227`; 965.375 news, OPT accuracy 74,4%, Sharpe 3,05 sau 10 bps |
| S12 | Đã sửa | DOI `10.1016/j.gfj.2024.100945`; dữ liệu MarketPsych thương mại |
| H02 | Đã xác minh | FinMem có repository tác giả, temporal split và 5 stochastic trials |
| H10 | Đã sửa | IPM 63(2), article 104466, DOI `10.1016/j.ipm.2025.104466`; backtest được báo cáo chỉ 3 ngày |
| E05 | Đã sửa | Hansen SPA DOI `10.1198/073500105000000063` |
| E07 | Đã sửa | Jobson–Korkie DOI `10.1111/j.1540-6261.1981.tb04891.x` |
| E09 | Đã sửa | Sullivan, Timmermann & White DOI `10.1111/0022-1082.00163`; 100 năm daily DJIA |

## Nhóm kỹ thuật crypto được duyệt làm nền tảng

| ID | Nguồn | Vai trò trong dự án |
|---|---|---|
| T03 | Common Risk Factors in Cryptocurrency | Universe rộng và momentum factor |
| T05 | Technical Trading and Cryptocurrencies | Rule search, OOS, cost, FWER/FDR |
| T06 | State Transitions and Momentum Effect | Regime-conditioned momentum |
| T08 | Trading Volume and Liquidity Provision | Reversal/liquidity transfer |
| T11 | Disagreement and Returns | Abnormal volume dưới short-sale constraints |
| T12 | Risk-Managed Momentum | Exposure/volatility scaling |
| T13 | Stop-Loss Rules and Momentum Payoffs | Stop-loss ablation |
| T14 | Liquidity Shocks and Risk-Managed Strategy | Amihud/funding-liquidity overlay |
| T15 | Risk Factors in Cryptocurrency Futures | Basis/momentum futures factor |
| T16 | Order Flow and Cryptocurrency Returns | Multi-exchange signed order flow |
| T17 | CTREND | Aggregate trend signal |

## Quy tắc đồng bộ với triển khai

1. Mỗi paper có một record source-of-truth duy nhất.
2. `references.bib`, Literature Review và workbook phải dùng cùng DOI/title/year.
3. Phương pháp gốc và transfer test phải nằm ở hai cột khác nhau.
4. Kết quả paper không được nhập vào cột kết quả dự án.
5. Record `unverified` không được dùng để tạo claim.
6. Negative transfer không làm paper bị loại khỏi literature; nó chỉ thay đổi deployment status trong dự án.
7. Sau mỗi thay đổi generator phải kiểm tra lại Master, selected subset, counts và Sheet 12.

## Trạng thái hiện tại

Ma trận hiện hành có 13 sheet, trong đó Sheet 12 đối chiếu backtest/phương pháp của T03/T05/T08/T11–T17, S11/S12, H02/H03/H10 và ba nhánh của dự án. Các phần mô tả `O-LLM` và `O-Hybrid` trong matrix cũ có thể còn ghi “chưa chạy”; sổ cái thí nghiệm mới là nguồn cập nhật hơn cho các development run Llama/Qwen.
