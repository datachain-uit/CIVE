# Sàng lọc Common Crawl x CFTC cho LLM-only

> Ngay screen: 2026-09-07. Pham vi outcome-blind: chi truy van read-only Common Crawl CDX index; khong tai WARC/WET, khong doc text corpus, khong truy cap market/candle va khong chay model.

## Candidate

Su dung cac release Common Crawl da cong bo, gioi han URL vao `cftc.gov/PressRoom/PressReleases/`, va chi sau do loc trang CFTC co noi dung lien quan crypto. CFTC tu xac nhan thong tin chinh phu tren website la public domain, ngoai tru tai lieu do ben thu ba dong gop/licensed. Common Crawl luu WARC record co timestamp UTC va chi so index tra ve URL, capture timestamp, digest, WARC filename, offset va length nen co the tai lap ma khong phai tu crawl website.

## Kiem tra index

Da truy van read-only index `CC-MAIN-2024-10` voi URL prefix CFTC Press Releases, HTTP 200, HTML va `collapse=urlkey`.

Index tra ve cac URL mang ma release cu, vi du `https://www.cftc.gov/PressRoom/PressReleases/5193-06`, nhung co capture timestamp `20240223164618` va WARC file nam trong release `CC-MAIN-2024-10`. Nghia la archive timestamp co UTC va tai lap, nhung la thoi diem crawler thu thap mot trang da ton tai tu truoc, khong phai bang chung ve thoi diem ban dau cong bo noi dung.

## Hard-gate va quyet dinh

| Hard gate | Trang thai | Ly do |
| --- | --- | --- |
| Archive/version lich su doc lap | PASS o cap archive | Common Crawl release va WARC locator co dinh danh tai lap. |
| Quyen dung text | Conditional | CFTC noi government information tren site la public domain; corpus contract phai loai tai lieu ben thu ba. |
| UTC offset moi record | PASS o cap capture | WARC timestamp duoc bieu dien UTC. |
| PIT / information time cho event | **FAIL** | `WARC-Date` chi cho biet thoi diem archive capture. No khong chung minh trang la thong tin moi o thoi diem do; index cho thay release cu duoc capture nam 2024. Khong duoc gan event time bang WARC capture cho noi dung da co tu nhieu nam truoc. |
| Khong co price/market label/feature/outcome | Chua audit corpus | Chua tai hay parse text; khong co corpus contract de ket luan admission. |

`REJECTED_FOR_LLM_ONLY_EVENT_CORPUS_PIT`.

Nguon nay khong duoc dung de mo treatment. Viec dung Common Crawl thay vi tu crawl giup reviewer tai lap archive, nhung khong tu dong giai quyet tinh moi cua event va information-time causality. Khong tai WARC/WET hay corpus tu candidate nay.

## Nguon public da kiem tra

- CFTC Web Policy: https://www.cftc.gov/WebPolicy/index.htm
- Common Crawl Get Started: https://commoncrawl.org/get-started
- Common Crawl archive/index overview: https://commoncrawl.org/latest-crawl
- Common Crawl WARC format overview: https://commoncrawl.org/blog/web-archiving-file-formats-explained
- Reproducible index query: https://index.commoncrawl.org/CC-MAIN-2024-10-index?url=cftc.gov%2FPressRoom%2FPressReleases%2F*&output=json&filter=status:200&filter=mime:text%2Fhtml&collapse=urlkey
