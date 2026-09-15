# Sàng lọc CFTC RSS cho LLM-only

> Ngay screen: 2026-09-07. Pham vi outcome-blind: chi doc metadata RSS; khong tai text corpus, khong truy cap candle/market outcome va khong chay model.

## Gia thuyet candidate

RSS General Press Releases cua CFTC co the la nguon phu hop neu tung item cung cap `pubDate` kem UTC offset va co archive lich su doc lap. CFTC mo ta RSS la kenh phan phoi content thay doi thuong xuyen; Web Policy cua CFTC noi government information tren website la public domain, voi ngoai le cho tai lieu do ben thu ba dong gop/licensed.

## Ket qua

`BLOCKED_RSS_METADATA_UNVERIFIABLE`.

Read-only request toi `https://www.cftc.gov/RSS/RSSGP/rssgp.xml` tra HTTP 403 Cloudflare challenge. Vi vay khong the xac minh bang artifact may doc duoc rang item co `pubDate` kem UTC offset, khong the pin feed snapshot, va khong the doi chieu archive lich su cua tung item.

Khong dung UI/browser de vuot access control, khong suy dien timestamp tu giao dien Press Releases, va khong admission candidate nay. Khong co text corpus nao duoc tai hay doc.

## Dieu kien de xem lai

Chi xem lai neu CFTC cong bo mot endpoint/archive RSS ma co the truy cap cong khai, may doc duoc va luu `pubDate` kem UTC offset cho tung item. Endpoint do phai duoc pin/hash truoc khi bat ky corpus contract nao duoc mo.

## Nguon public da kiem tra

- CFTC RSS landing page: https://www.cftc.gov/RSS/index.htm
- CFTC Web Policy: https://www.cftc.gov/WebPolicy/index.htm
- Endpoint da block: https://www.cftc.gov/RSS/RSSGP/rssgp.xml
