# LLM-only v10: corpus co the tai phan phoi

Status: REPRODUCIBLE_TEXT_PILOT_NOT_PREDICTIVE_ADMISSION. Thay nguon Reddit bang
thong cao chinh sach tien te do Federal Reserve Board phat hanh. Day la thay doi
cau hoi/nguon bang chung sang su kien vi mo, khong phai social-media sentiment.

Update provenance: v10.2 recovered gzip snapshots offline. Of 24 statements,
19 current text extracts match independent near-release archived extracts, zero
mismatch, and five remain unresolved because of timeout/503. This supports text
version stability for the matched subset, not public availability at capture time.
See `paper/input/results/llm/v10/fomc_archived_version_audit_v10_2.json`.

The outcome-free planning diagnostic estimates a two-sided correlation MDE of
0.5450809287 at alpha 0.05 and power 0.80 under optimistic independent-observation
assumptions. Therefore the 24-event pilot is not admitted to a predictive gate.
See `paper/input/results/llm/v10/fomc_provenance_summary_v10.json`.

## Quyen va nguon

Board cho phep sao chep/phan phoi thong tin cua minh theo public-domain notice,
tru ngoai le duoc ghi ro. Chi dong goi text thong cao Board-authored; khong gom
logo, anh, dau hieu co quan hay tac pham ben thu ba. Ghi nguon Board va khong
ham y duoc Board bao tro. Khong ap dung notice nay cho cac Federal Reserve Bank
khac, bai bao ben ngoai hay du lieu gia. Nguon:
https://www.federalreserve.gov/disclaimer.htm

Ban sao policy/calendar va SHA256 duoc luu trong manifest:
`paper/input/results/llm/v10/open_fomc_pilot/manifest.json`.
Policy raw: `paper/input/references/source_artifacts/open_fomc_v10/policy.html`.

## Pilot da tao

24 thong cao, moi nam 8 ban trong 2022-2024, duoc chon tu tat ca link statement
dung quy tac tren lich chinh thuc da snapshot. Khong chon theo return hay ket qua
model. Tinh day du chi trong danh muc lich da kiem tra; khong dai dien toan bo
tin ve BTC, speeches, minutes hay moi thong bao bat thuong.

`corpus.json` giu van ban, URL, source/text SHA256, ngay tai, gio cong bo goc
EST/EDT va UTC. Metadata khong duoc lam predictive feature. Input LLM chi la
text; con so lai suat nam trong cau van khong duoc tach thanh feature ky thuat.
Khong dung OHLCV, lagged return, funding hoac chi bao. Chua noi gia hay chay LLM.

## Reviewer

`reviewer_text_pilot.zip` chua corpus, manifest, NOTICE, code va verifier.
Giai nen vao thu muc bat ky, chay `python verify.py` bang Python standard library.
Lenh kiem tra moi file va tung text hash offline, khong can account/API key.

De tai lai tu nguon, dat hai script build va helper trong `tools/llm/` cua mot
workspace moi, sau do chay build script. Code build dung layout workspace nay;
khong chay no truc tiep tu thu muc ZIP tuy y. Nguon live co the thay doi; snapshot
text dong goi moi la dinh nghia input cua pilot, khong phai ban tai moi.

Day CHUA la goi tai lap toan bo thi nghiem: con thieu model/checkpoint hash,
prompt/schema, dependency lock, seed/decoding, predictions, split/target code,
quyen phan phoi market labels va moi truong chay. Chua upload/publish ra ngoai.
Co the gan DOI/archive version cho goi hoan chinh sau khi dong bang thi nghiem.

## Gioi han

Timestamp co nguon chinh thuc va quy tac EST/EDT ro rang. Tuy nhien hash tai hom
nay chi khoa ban hien tai: khong chung minh noi dung nay giong het ban o gio
cong bo. Truong `historical_first_version_verified` van false. Can kiem tra ban
phat hanh luu tru doc lap hoac khai bao ro gia dinh archived-release; khong goi
la strict PIT khi chua co bang chung.

Khong tang so mau bang cach xem cac doan cua cung thong cao la su kien doc lap.
24 su kien khong du de mac dinh co statistical power; phai danh gia coverage,
overlap voi gia development san co va power truoc predictive freeze. Cac ket qua
v3-v9 da biet; day la follow-up development, khong phai xac nhan doc lap.

Buoc tiep: kiem tra original versions va corpus quy mo phu hop; khoa mot protocol
event-response text-only truoc khi doc outcome. Khong suy dien thanh loi nhuan.
