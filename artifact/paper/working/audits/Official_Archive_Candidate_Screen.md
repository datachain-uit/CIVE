# Sàng lọc candidate archive chinh thuc cho LLM-only

> Ngay screen: 2026-09-07. Day la provenance screen outcome-blind; khong phai protocol treatment, khong tai corpus, khong truy cap candle/market outcome va khong chay model.

## Candidate

**Federal Register bulk XML (GovInfo / National Archives), theo nam/issue.**

Nguon nay la mot dataset cong khai cua National Archives cho cac issue Federal Register theo nam va GovInfo cung cap bulk XML theo nam tu 2000. Tung issue la mot package co content va metadata/preservation metadata; OFR mo ta cac tai lieu da xuat ban la permanent Federal records. Huong dan XML cua OFR/GPO noi rang, theo nguyen tac chung, khong han che tai su dung thong tin trong Federal Register documents vi U.S. Government works khong thuoc ban quyen.

## Ket qua hard-gate hien tai

| Hard gate | Trang thai | Ly do |
| --- | --- | --- |
| Version/archive lich su doc lap | Chua dong | Archive chinh thuc va package/issue theo ngay la bang chung kha thi, nhung can pin chinh xac year/issue/package identifiers va fixity artifact truoc admission. |
| Quyen dung text cho nghien cuu/LLM | Chua dong | Huong dan OFR/GPO ung ho tai su dung Federal Register, nhung corpus contract phai loai tru bat ky noi dung ben thu ba duoc incorporate by reference va ghi ro pham vi text duoc dung. |
| UTC offset moi record | **FAIL / chua duoc chung minh** | Tai lieu da kiem tra xac nhan ngay phat hanh va archive, nhung chua co artifact chung minh moi document duoc dung co timestamp kem UTC offset. Khong duoc tu gan offset tu publication date hay dien giai gio filing khong offset thanh UTC. |
| Khong co price/market label/feature/outcome | Chua dong | Nguon la van ban quy dinh/chinh sach, nhung chua co schema contract va filter da khoa. Admission chi cho phep text va metadata provenance da predeclare; cam cac truong outcome hay tinh nang thi truong neu phat sinh o buoc sau. |

## Quyet dinh

`NOT_ADMITTED_FOR_LLM_ONLY_CORPUS`.

Candidate nay khong duoc tai toan bo va khong duoc dung de tao event-vector khi timestamp gate chua PASS. No chi la mot nguon dang xem xet, tach biet hoan toan voi v3-v8 va khong tao ra treatment hay ket qua moi.

## Dieu kien duy nhat de chuyen screen

Can co artifact chinh thuc, co the tai lap, cho phep xac minh **timestamp UTC-offset tren tung document se admit**. Artifact do phai duoc pin/hash va duoc doi chieu voi historical package/issue truoc khi lam bat ky corpus download nao. Neu khong co, candidate bi loai; khong dung gia dinh timezone, backfill timestamp hay day lui cutoff de luot gate.

## Nguon public da kiem tra

- National Archives, Federal Register Dataset: https://www.archives.gov/open/dataset-fedreg.html
- National Archives, Federal Register FAQ: https://www.archives.gov/federal-register/faqs
- GovInfo, Federal Register help: https://www.govinfo.gov/help/fr
- GovInfo, Developer Hub / Bulk Data Repository: https://www.govinfo.gov/developers
- OFR/GPO, Federal Register XML User Guide: https://www.govinfo.gov/bulkdata/FR/resources/FDsys_OFR-XML_User-Guide-v1.pdf
