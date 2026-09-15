# Admission screen: SEC RSS trong Internet Archive

> Ngay audit: 2026-09-07. Pham vi outcome-blind. Khong truy cap candle/market outcome, khong chay LLM, khong fit model va chua tai corpus day du.

## Candidate va information-time contract

Candidate la cac snapshot RSS `https://www.sec.gov/news/pressreleases.rss` duoc Internet Archive luu doc lap. Record duoc phep dung se bao gom title, description, link, GUID, `pubDate` va archive provenance. **Decision time duy nhat la archive capture time UTC**, khong phai `pubDate`. `pubDate` chi duoc dung nhu timestamp do SEC phat hanh va phai parse duoc kem UTC offset; item co `pubDate` muon hon archive capture time bi loai.

Quy tac nay tranh suy dien rang page da co tai thoi diem publisher tu ghi. No chi khang dinh rang text da co trong snapshot archive tai `archive_capture_at`, vi vay evaluation sau nay chi duoc dat target sau thoi diem do. Day la delayed-archive information set, khong phai tai lap tin hieu real-time cua SEC.

## Bang chung source-level

Read-only CDX query cua Internet Archive cho URL RSS, HTTP 200, tra 141 snapshot HTTP 200 sau khi deduplicate theo ngay, tu 2021 den 2026: 2021 co 32, 2022 co 30, 2023 co 39, 2024 co 18, 2025 co 15 va 2026 co 7. Moi record index co capture timestamp UTC, digest va length. Snapshot 2021-03-24 da duoc doc de kiem schema va co item voi `pubDate` nhu `Mon, 22 Mar 2021 10:00:00 -0400`.

SEC xac nhan tat ca content do Chinh phu tao tren sec.gov duoc free to access and reuse; scope corpus cam media, logo va bat ky noi dung khong phai plain-text title/description do SEC phat hanh.

## Hard-gate decision

| Hard gate | Trang thai | Contract kiem soat |
| --- | --- | --- |
| Version/archive lich su doc lap | PASS | Internet Archive CDX record pin URL, `archive_capture_at`, digest va length; snapshot la artifact doc lap voi SEC. |
| Quyen dung text cho nghien cuu/LLM | PASS trong scope | Chi plain-text title/description cua SEC; loai media/logo va noi dung khong phai Government-created. |
| UTC offset moi record | PASS co dieu kien record | Chi admit item co `pubDate` parse duoc kem explicit offset; decision time la CDX UTC capture timestamp. Khong tu gan timezone. |
| Khong co price/market label/feature/outcome | PASS theo corpus contract | Corpus contract chi luu text va provenance RSS; khong luu hay dung gia/candle/market field, outcome, feature hay reflection. |

`SOURCE_ADMITTED_FOR_OUTCOME_BLIND_CORPUS_BUILD`.

## Gioi han va buoc duoc phep

Admission nay khong phai predictive PASS va khong mo action/backtest. Buoc duy nhat duoc mo la tai cac snapshot RSS da predeclare, verify digest/parse, ap dung record filter, deduplicate theo GUID + archive availability time, va dong manifest outcome-blind. Bat ky record fail `pubDate` offset, co `pubDate` sau capture, hay khong phai plain-text SEC feed item deu bi loai. Chi sau khi manifest duoc dong moi duoc viet protocol predictive LLM-only moi.

## Nguon va truy van tai lap

- SEC RSS: https://www.sec.gov/news/pressreleases.rss
- SEC reuse policy: https://www.sec.gov/about/webmaster-frequently-asked-questions
- SEC dissemination policy: https://www.sec.gov/about/privacy-information
- Internet Archive CDX documentation: https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md
- CDX query: https://web.archive.org/cdx/search/cdx?url=www.sec.gov%2Fnews%2Fpressreleases.rss&output=json&filter=statuscode:200&fl=timestamp,digest,length&collapse=timestamp:8&from=2021&to=2026
