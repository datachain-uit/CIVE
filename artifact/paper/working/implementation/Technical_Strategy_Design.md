# Thiết kế chiến lược kỹ thuật — nhánh không dùng AI

## Mục tiêu và ranh giới

Mục tiêu là xây dựng một Tech-Control có thể kiểm toán, dùng dữ liệu point-in-time, execution bảo thủ và chi phí thực tế để làm control cho thí nghiệm AI. Nhánh này không được thay đổi sau khi treatment bắt đầu. Nó không phải khuyến nghị live.

## Thiết kế đang khóa

- Venue: Bybit linear USDT perpetual.
- Universe: top-5 trailing exchange turnover 30 ngày, membership có độ trễ một ngày; lấy cả hợp đồng `Trading` và `Closed` theo launch/delivery time.
- Regime: BTC `close[t] >= close[t-7] >= close[t-14]` trên nến ngày đã đóng.
- Event: compressed-channel growth.
- Xếp hạng: momentum 20 ngày.
- Danh mục: long-only, top-1, gross exposure 1x, không pyramid.
- Risk: fixed stop 3 ATR, trailing stop 4 ATR.
- Execution: next eligible 4H open, `open_funding_intrabar_v2`, funding thật, không same-bar re-entry.
- Search: grid 54 cấu hình, chọn bằng 6 fold train; 2 fold sau chỉ mở khi cấu hình đã khóa.

## Lịch sử quyết định và kết quả chính

| Giai đoạn / biến thể | Dữ liệu và protocol | Kết quả chính | Quyết định |
|---|---|---|---|
| Channel rule theo từng coin | 4 năm, 5 coin | Không coin nào đạt majority gate; BTC 2/6, BNB 1/6, còn lại 0/6 | Bác bỏ standalone rule |
| Cross-asset top-2 daily | Fixed 5 coin, 10 bps | +140,26%, MDD 19,96%, 7/7 fold dương | Chuyển sang execution 4H |
| 4H với stop+trail | Fixed 5 coin | +54,65%, MDD 20,09%, 192 fills | Trail làm mất nhiều hiệu suất |
| Fixed stop 2,5 ATR | Fixed 5 coin | +123,16%, MDD 18,19%, 132 fills | Giữ làm ứng viên trung gian |
| Bear book độc lập | BTC DOWN-DOWN, 2 momentum yếu nhất | -29,38%, 2/7 fold dương | Bác bỏ |
| Funding carry một sàn | Long spot/short perpetual | -73,22%, 0/8 fold dương | Bác bỏ |
| AutoQuant core top-2 | Base/stress/harsh | +123,96% / +98,49% / +71,22% | Cost-robust nhưng selection risk cao |
| Growth top-1 không ATR intraday | Fixed 5 coin | +202,53%, MDD 15,60%; harsh +138,52% | Research candidate, fold cuối âm |
| Volume veto | Abnormal-volume proxy | +89,48%; thấp hơn control | Bác bỏ |
| OI rising 7 ngày | Bybit OI history | +128,54%; thấp hơn control | Bác bỏ |
| Funding-crowding veto | Settled funding 3 ngày | +203,23%; harsh +147,10% | Promising filter, chưa chọn |
| Basis gate | Bybit/OKX perpetual premium | 49,13%–175,06%; đều dưới control | Bác bỏ gate |
| Paper-style basis factor | Perpetual transfer | -40,48% đến -81,28%; 5-bps long-high +46,14% với MDD 67,23% | Bác bỏ transfer |
| Taker-flow proxy | Binance USD-M một sàn | 106,60%–200,47%, dưới control | Bác bỏ proxy |
| Fixed current-liquid 10 coin | 1x | +260,51%, MDD 15,60% | Có survivorship, không publication claim |
| PIT top-5 trong pool 10 coin | no-same-bar-reentry | +163,88%, MDD 11,28% | Control trung gian |
| Oscillator transfer | RSI/Stochastic/CCI | -5,56%/-43,81% có regime; khoảng -96% khi bỏ regime | Bác bỏ; không phải CTREND replication |
| Lifecycle v1 | 987 contract có dữ liệu, 43 từng top-5 | +168,62%, MDD 10,56%, 66 fills | Đã bị v2 thay thế |
| Lifecycle hardened v2 | Cùng cấu hình, event order chuẩn | +217,48%, MDD 10,56%, 62 fills | Artifact được freeze |

## Universe lifecycle

Builder quét 991 perpetual giao với cửa sổ bốn năm và có dữ liệu dùng được cho 987 hợp đồng. Có 43 hợp đồng từng lọt top-5 thanh khoản causal, trong đó 6 hợp đồng hiện đã đóng. Membership chỉ sử dụng turnover đã hoàn thành trước ngày giao dịch. Delisting được xem là sự kiện execution rõ ràng.

## Kết quả Tech-Control v1 hardened

| Chi phí | Return | MDD | Fills | Fold dương | Hai fold cuối |
|---|---:|---:|---:|---:|---|
| Base | +217,48% | 10,56% | 62 | 6/8 | -0,33%; -3,33% |
| Stress | +204,37% | 11,46% | 62 | 6/8 | âm ở cả hai fold |
| Harsh | +186,69% | 12,71% | 62 | 6/8 | âm ở cả hai fold |

Hai fold cuối đã được xem nên không phải sealed holdout. Kết quả chứng minh một control nghiên cứu mạnh trong development sample, không chứng minh future validity.

## Robustness và selection risk

- Candidate xếp hạng 2/54 trên sáu fold development dưới semantics v2.
- 27 lân cận top-1 đều dương toàn mẫu; return nhỏ nhất 85,32%, median 140,55%, lớn nhất 218,34%.
- Mọi cấu hình top-1 đều âm trên hai fold cuối: recent decay là failure mode chung, không phải một sharp optimum đơn lẻ.
- CSCV trên 8 partition cho PBO 0/70; DSR probability 0,9996. Đây là diagnostic trên development sample đã xem.
- 82,5% net PnL đến từ XRP và BTC; positive-contribution HHI 0,3699.
- Leave-one-out vẫn dương với từng coin bị loại; bỏ đồng thời BTC và XRP còn +41,02%.
- Breakeven empirical với fee 6 bps/side nằm giữa 150 và 175 bps adverse execution/side.

## Điều không được làm

- Không đổi tham số Tech vì kết quả LLM hoặc Hybrid.
- Không gọi hai fold cuối là final holdout.
- Không so return leverage với 1x rồi gọi là alpha cao hơn.
- Không gọi transfer test là replication khi dữ liệu/universe/frequency khác paper.
- Không dùng Tech-Control để live trước một sealed holdout mới.
