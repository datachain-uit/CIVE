# Ghi chú triển khai các phương pháp kỹ thuật từ tài liệu

## Nguyên tắc

Mỗi mục phải tách bốn phần: phương pháp của tác giả, dữ liệu của tác giả, phần được chuyển sang dự án, và kết quả trên dữ liệu dự án. Chỉ dùng từ “replication” khi tái lập đúng dữ liệu, universe, feature, tần suất và protocol gốc; phần lớn thí nghiệm dưới đây là transfer test.

## Đối chiếu nguồn và kết quả chuyển giao

| Mã | Phương pháp gốc | Dữ liệu/kết quả gốc đáng chú ý | Triển khai trên dữ liệu dự án | Kết quả dự án | Kết luận |
|---|---|---|---|---|---|
| T05 | Hudson & Urquhart (2021): khoảng 14.919 technical rules, FWER/FDR, OOS và breakeven cost | BTC CoinDesk/Bitstamp; LTC/ETH/XRP CoinMarketCap; BTC không có OOS return dương được báo cáo | Dùng kỷ luật rule family, train-fold selection, cost stress và inference cho Bybit perpetual | Dẫn tới Tech-Control lifecycle, không sao chép rule grid gốc | Paper-inspired implementation |
| T03 | Liu, Tsyvinski & Wu (2022): market/size/momentum factors | Cross-section crypto rộng | Fixed-ten perpetual long-short transfer, 10 bps | -40,15% | Transfer thất bại; giữ nguyên tắc universe rộng |
| T08 | Bianchi et al. (2022): reversal mạnh khi detrended volume thấp | CryptoCompare/CoinGecko, hơn 80 sàn, 2017–2022 | Simplified long-only reversal/liquidity transfer | -91,72% cho low-relative-volume | Transfer thất bại |
| T12 | Risk-managed momentum | CoinMarketCap weekly cross-section; volatility scaling | Inverse-volatility/exposure ablation trên perpetual | Không tạo candidate tốt hơn control sau chuẩn hóa exposure | Không chọn |
| T13 | Stop-loss cho momentum | 147 coin, dữ liệu tháng, stop 10%–50% | Fixed/trailing ATR trên bar 4H | Fixed stop hữu ích; trailing ban đầu làm giảm return mạnh | Giữ ý tưởng ablation, không sao chép threshold |
| T14 | Liquidity shock condition exposure | BTC/ETH/XLM/LTC/XRP; market và funding liquidity | Amihud proxy causal ở asset/market/combined gate | Không cải thiện sáu fold train | Tắt mặc định; không replication |
| T15 | Basis/momentum factor trên futures | 12 OKEx current-quarter futures 2017–2021; paper báo 329,21% annualized abnormal return cho high-minus-low basis | Bybit/OKX perpetual premium, actual funding, 11 bps one-way | Long-high -40,48%; consensus long-high -42,54%; high-minus-low -81,28%; ở 5 bps consensus long-high +46,14% nhưng MDD 67,23% | Bác bỏ transfer |
| T16 | World signed order flow | 84 coin, 300+ sàn, 11 đồng tiền định giá; OOS economic value | `log(taker-buy/taker-sell)` từ Binance USD-M một sàn | Các biến thể 106,60%–200,47%, đều dưới control tương ứng | Bác bỏ proxy; chưa replication |
| T17 | CTREND: kết hợp 28 tín hiệu bằng rolling C-ENet | Hơn 3.000 coin, 2015–2022 | Xếp hạng RSI/Stochastic/CCI minh bạch | Top-1/top-2 weekly -5,56%/-43,81% có regime; khoảng -96% không regime | Bác bỏ transfer hẹp |

## Các ablation nội bộ quan trọng

| Thành phần | Control | Biến thể | Kết quả | Quyết định |
|---|---:|---:|---:|---|
| Stop/trailing | Stop+trail +54,65% | Không ATR exit +137,52%; fixed 2,5 ATR +123,16% | Trail là nguồn giảm hiệu suất chính | Dùng fixed+trailing mới sau grid lifecycle |
| Pyramiding | Fixed-stop +123,96% | 3-layer +93,40%, MDD 11,79% | Giảm return và DD | Chỉ defensive scenario |
| Bear book | Cash ngoài bull regime | Short-only -29,38% | Không có edge | Bác bỏ |
| Funding carry | Không có carry book | Delta-neutral -73,22% | 0/8 fold dương | Bác bỏ |
| Derivatives confirmation | Control +202,53% | OI +128,54%; funding veto +203,23%; combined +124,13% | Chỉ funding veto giảm turnover | Không thay winner |
| Wider universe | Fixed 5 +202,53% | Fixed 10 +260,51% | Tăng return nhưng survivorship | Dẫn tới lifecycle universe |
| Exposure | 1x +260,51% | 1,5x +512,02%; 2x +876,25% trước PIT correction | Thêm risk/exposure, không thêm alpha | Không dùng làm control |

## Cấu hình cuối cùng được chọn

Optimizer thay đổi position count, liquidity universe/lookback, momentum horizon, stop và trail; chỉ dùng sáu fold đầu để chọn. Sau khi chuyển sang universe lifecycle đầy đủ và semantics v2, cấu hình freeze là top-1, momentum 20 ngày, stop 3 ATR, trail 4 ATR, universe top-5 30 ngày và 1x.

Kết quả canonical là +217,48%, MDD 10,56%, 62 fills; stress +204,37%; harsh +186,69%. Con số +168,62% là artifact v1 đã bị thay thế, không phải control freeze hiện hành.

## Quy tắc viết paper

- Nêu rõ nguồn và DOI trước khi mô tả phương pháp.
- Tách `kết quả tác giả` khỏi `kết quả dự án` thành hai cột.
- Ghi đúng contract type: spot, dated futures hoặc perpetual.
- Không so sánh trực tiếp headline return khi leverage, period, cost và universe khác nhau.
- Negative transfer là kết quả nghiên cứu hợp lệ.
- Mọi số liệu phải trỏ tới artifact trong sổ cái thí nghiệm.
