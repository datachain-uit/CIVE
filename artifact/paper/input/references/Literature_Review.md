# Tổng quan tài liệu cho đánh giá có kiểm soát AI trong giao dịch crypto

## Phạm vi

Tổng quan tập trung vào bốn nhóm: nền tảng tài chính/kiểm định, technical crypto, sentiment/LLM và hệ thống hybrid/multi-agent. Mục tiêu không phải gom nhiều paper nhất, mà xác định phương pháp nào có thể làm baseline, phương pháp nào chỉ cung cấp nguyên tắc thiết kế, và transfer test nào đã được chạy trên dữ liệu dự án.

## Nền tảng tài chính và kiểm định

| Mã | Nguồn | Đóng góp liên quan |
|---|---|---|
| F01 | Markowitz (1952), *Portfolio Selection* | Khung mean–variance; không phải benchmark code/dataset |
| F02 | Sharpe (1966), *Mutual Fund Performance* | Sharpe ratio; không phải empirical trading benchmark |
| F03 | Murphy (1999), *Technical Analysis of the Financial Markets* | Nguồn nghề nghiệp cho technical indicators |
| F04 | Chan (2013), *Algorithmic Trading* | Quy trình thực hành và backtest |
| F05 | Tsay (2005), *Analysis of Financial Time Series* | Chuỗi thời gian tài chính |
| F06 | López de Prado (2018), *Advances in Financial Machine Learning* | Backtest overfitting, purging/embargo, DSR/CSCV |
| E04 | White (2000) | Reality Check cho data snooping |
| E05 | Hansen (2005) | Superior Predictive Ability test |
| E06 | Diebold–Mariano | So sánh predictive accuracy khi có loss series rõ ràng |
| E08 | Bailey & López de Prado (2014) | Deflated Sharpe Ratio |
| E09 | Sullivan, Timmermann & White (1999) | Data-snooping trong technical-rule search |

## Các nghiên cứu kỹ thuật về crypto

### T05 — Hudson & Urquhart (2021)

Nghiên cứu khoảng 14.919 technical rules trên BTC/LTC/ETH/XRP, tách IS/OOS, xét breakeven cost và kiểm soát FWER/FDR. Đây là nền tảng mạnh cho kỷ luật search, không phải công thức strategy để sao chép trực tiếp. Dự án dùng nguyên tắc này cho grid và inference của Tech-Control.

### T03 — Liu, Tsyvinski & Wu (2022)

Xây dựng factor market, size và momentum trên cross-section crypto rộng. Dự án dùng bằng chứng này để biện minh cho universe point-in-time và momentum ranking. Transfer hẹp sang perpetual cố định cho kết quả âm nên không được gọi là replication.

### T06 — Hsieh, Huang & Liu (2025)

Cho thấy momentum phụ thuộc trạng thái thị trường, đặc biệt ở chuyển trạng thái UP-UP bền. Dự án chuyển ý tưởng thành BTC regime gate causal dùng nến ngày đã đóng.

### T08, T11 và T14 — volume, disagreement và liquidity shock

Ba nguồn cho thấy volume/liquidity có vai trò điều kiện, không phải alpha vô điều kiện. Dự án đã thử reversal/liquidity, abnormal-volume veto và Amihud gate; các transfer đều không cải thiện control tương ứng.

### T12 và T13 — risk-managed momentum và stop-loss

Các nghiên cứu hỗ trợ việc tách risk management thành ablation. Dự án báo cáo exposure, stop và trailing riêng; không sao chép scaling/threshold của paper khi tần suất và contract khác nhau.

### T15 — Chi et al. (2023)

Nghiên cứu basis/momentum trên 12 OKEx current-quarter futures 2017–2021. Dự án dùng Bybit/OKX perpetual premium để transfer, nhưng kết quả paper-style trên perpetual yếu hoặc âm. Khác biệt dated futures/perpetual và thời kỳ được ghi rõ.

### T16 — Anastasopoulos et al. (2026)

World signed order flow từ 300+ sàn và 11 đồng tiền định giá có OOS economic value. Binance taker-flow một sàn của dự án không tương đương world flow và đã bị bác bỏ làm entry/rank feature.

### T17 — Fieberg et al. (2025)

CTREND kết hợp 28 indicator trên hơn 3.000 coin bằng rolling cross-sectional C-ENet. Dự án chỉ thử transfer minh bạch RSI/Stochastic/CCI; kết quả âm nên không được mô tả là CTREND replication.

### T18 và T19 — cơ chế hợp đồng vĩnh cửu

Ackerer, Hugonnier và Jermann (2026) cung cấp nền tảng định giá không chênh lệch giá cho hợp đồng tương lai vĩnh cửu và làm rõ vai trò neo giá của funding. Chen, Ma và Nie (2024) hệ thống hóa cơ chế hợp đồng trên sàn tập trung và phi tập trung, đồng thời phân tích khác biệt về thiết kế và hành vi người giao dịch. Hai công trình được dùng để định nghĩa sản phẩm, funding và phạm vi thị trường; chúng không phải bằng chứng về hiệu quả của tín hiệu giao dịch trong đề tài.

## Sentiment và LLM

### S01 — FinBERT

Domain adaptation cho Financial PhraseBank và FiQA. Đây là baseline NLP tài chính, không tự động là trading signal.

### S05 — FinGPT

Khung LLM tài chính mở và fine-tuning hiệu quả tài nguyên. Có giá trị về hệ sinh thái model; không dùng headline return chưa kiểm toán làm benchmark.

### S11 — Kirtac & Germano (2024)

Sử dụng 965.375 tin tài chính Mỹ, CRSP return và Refinitiv news. OPT đạt accuracy 74,4%; long-short strategy được báo Sharpe 3,05 sau 10 bps. Dự án giữ cấu trúc text → sentiment → subsequent return nhưng dùng CryptoVision và BTC perpetual; kết quả Llama development có CI cắt 0.

### S12 — Bennett et al. (2024)

Dùng hơn 50 thước đo sentiment MarketPsych để dự báo ETH và adaptive ensemble theo recent MSFE. Đây là nguồn crypto multi-source gần câu hỏi nghiên cứu, nhưng dữ liệu thương mại không thể replication. Dự án chỉ giữ nguyên tắc OOS, fusion và source ablation.

## Hybrid và multi-agent

### H02 — FinMem

Năm dataset cổ phiếu, temporal train/test, memory causal và năm stochastic trials với Wilcoxon inference. Dự án giữ yêu cầu repeat và temporal causality; memory module chưa được triển khai.

### H03 — FinAgent

Kết hợp price, chart, text và tool trên năm cổ phiếu cùng ETHUSD. Dự án giữ nguyên tắc multimodal fusion nhưng yêu cầu AI chỉ thay một decision field để đo `Tech+LLM - Tech-only`.

### H10 — Jung & Lee (2026)

Multi-agent zero-shot dùng technical, on-chain, macro và text cho BTC. Paper báo 21,75% total return, 29,30% annualized và Sharpe 1,08, nhưng backtest trading chỉ ba ngày. Vì vậy nguồn này hữu ích về kiến trúc/rationale, không đủ làm chuẩn hiệu quả dài hạn.

## Khoảng trống nghiên cứu

Các nghiên cứu thường thay đồng thời predictor, feature, portfolio rule, risk và execution. Điều đó không xác định được phần đóng góp riêng của AI. Luận văn giải quyết khoảng trống hẹp hơn: giữ nguyên universe, calendar, execution, risk và cost rồi đo treatment effect theo cặp khi thêm LLM assessment.

## Quy tắc sử dụng tài liệu

- Chỉ trích dẫn record đã xác minh trong ma trận và `references.bib`.
- Tách rõ kết quả paper, kết quả reproduction và kết quả transfer.
- Không dùng Google Scholar search URL làm nguồn chính.
- Không suy metric/dataset/code từ abstract khi paper không báo cáo.
- Không so sánh headline return nếu universe, period, leverage, contract và cost khác nhau.
