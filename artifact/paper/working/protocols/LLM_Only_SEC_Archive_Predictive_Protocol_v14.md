# Giao thuc predictive LLM-only tren SEC RSS archive v14

> Trang thai: DATA GATE FAIL; STOPPED BEFORE TARGET JOIN. Protocol nay doc lap voi v3--v8: dung corpus SEC RSS Internet Archive v14 da dong outcome-blind. No khong dung, khong sua, va khong mo lai bat ky ket qua hay target panel nao cua v3--v8.

## Cau hoi va information set

Cau hoi duy nhat la: event-vector do LLM tao tu text SEC RSS, da co trong snapshot Internet Archive, co du bao BTCUSDT spot return 24 gio sau thoi diem snapshot tot hon representation sentiment LLM tong quat hay khong?

Don vi quan sat la mot `archive_capture_at`, khong phai mot item RSS. Toan bo item duoc admit co cung `archive_capture_at` duoc aggregate thanh mot information set. Thoi diem nay la information time duy nhat. `pubDate` chi la provenance va khong duoc dung de dat lenh, chia fold, hay tao target. Corpus va provenance bat buoc la `sec-rss-internet-archive-v14`, manifest SHA-256 `dfd7fee0bd38b6c72fbe4f4abf0cf0eaeb36cae420af43b0415278603abb4fc0` va corpus SHA-256 `3da9172fb8b3b07a5e2fe50fa45aebe389b5f36de1983a0665af08fcc655aff3`.

## Extractor va data gates

Moi record corpus duoc score dung mot worker bang local `ministral3-8b`, cung response schema va validation contract cua extractor v3.9, nhung input la corpus v14 va output la artifact v14 moi. Reuse schema/validator da kiem chung khong phai reuse extraction hay ket qua v3.9. Truoc run, runner phai ghi hash cua model snapshot, prompt, response schema, postprocessor, source corpus va config; bat ky hash khong khop thi dung.

Extractor chi nhan `record_id` va `text`. Output bat buoc la `btc_relevance`, `event_type`, `affected_assets`, `direction`, `severity`, `reported_surprise`, `expected_horizon`, `confidence`, va `evidence_span`. Extraction gate PASS chi khi count va order khop corpus, moi record schema-valid, `evidence_span` la substring cua text, va khong co error. Khong duoc doc candle, target, prediction, metric hay backtest truoc extraction gate nay.

Sau extraction, eligibility da khoa la `btc_relevance` trong `{direct, systemic}` va `event_type` trong `{macro_liquidity, regulation, etf_institutional_flow, exchange_security, liquidation_leverage, network_protocol, fraud_legal, adoption_business}`. Loai `market_commentary` va `other`; khong co loc thu cong, keyword filter, hay dieu chinh eligibility sau outcome. Data gate chi mo target join khi con it nhat 96 information set eligible theo `archive_capture_at`, va moi set co it nhat mot event eligible.

## Candle artifact va target

Target duy nhat la BTCUSDT spot 24-hour simple return. Candle artifact candidate la cac ZIP 4h theo thang cua Binance Vision: `data/spot/monthly/klines/BTCUSDT/4h/BTCUSDT-4h-YYYY-MM.zip`, kem `.CHECKSUM`, cho cac thang bao phu tu information set eligible som nhat den muon nhat va them thang can cho horizon.

Truoc khi doc gia, candle audit phai pin URL, thoi diem tai, SHA-256 local cua ZIP va checksum cong bo, schema CSV, timezone UTC cua open time, uniqueness/continuity cua 4h bars va coverage target. Artifact nay la **post-hoc versioned evaluation data**: checksum tao reproducibility va fixity cua snapshot da tai, nhung khong tu minh chung minh vintage candle da ton tai tai information time. Do do, v14 khong duoc dien giai la simulaton feed gia thoi gian thuc.

Voi moi information set o thoi diem `T`, execution open la open 4h dau tien co `open_time > T`; target la `open[t+24h] / open[t] - 1`. Candle chi dung de tao target va cham diem, khong xuat hien trong prompt, event-vector, feature, eligibility hay chia fold.

## Arms va feature contract

`prior` du bao trung binh target training fold va chi diagnostic. `llm-sentiment` la comparator chinh: direction fractions, signed direction, severity/confidence co dau, va mean/max cua severity, reported_surprise, confidence. `llm-event-conditioned` la treatment duy nhat: toan bo feature sentiment cong relevance fractions, event-type fractions, expected-horizon fractions, va signed impact co dinh theo event type/relevance. Relevance weight co dinh: direct 1.0, systemic 0.75. Khong tune trong so.

Moi predictive feature phai co tien to `llm_` va truy duoc truc tiep toi output extractor. Cam OHLCV, gia, return, volatility, volume, funding, regime, technical indicator, source identity, archive metadata, article count, text length, recency, calendar, va bat ky deterministic metadata nao. Evaluator fail-fast neu phat hien feature vi pham.

## Model, split va gate

Ridge co `alpha=10`, standardization chi fit tren training fold, khong hyperparameter tuning. Sap theo `archive_capture_at`; dung ba expanding folds, moi fold 24 information set OOS lien ke va purge 24 gio truoc validation. Data gate yeu cau dung 72 OOS prediction (3 x 24), khong thieu target, va event prediction khong hang.

Uncertainty dung paired moving-block bootstrap trong tung fold, 5,000 draw, block 4 information set, seed `20260908`, CI 95%. Predictive gate PASS chi khi dong thoi:

- can duoi CI 95% cua `MSE(llm-sentiment) - MSE(llm-event-conditioned)` lon hon 0;
- can duoi CI 95% Pearson cua event-conditioned lon hon 0;
- event-conditioned thang sentiment theo MSE it nhat 2/3 fold;
- dung 72 OOS prediction va prediction khong hang.

Neu fail, khoa artifact am va dung truoc threshold, action mapping, backtest, Tech+LLM va sealed holdout. Neu pass, chi duoc phep viet mot predeclaration backtest LLM-only development rieng; pass predictive khong chung minh loi nhuan hay kha nang live.

## Ket qua data gate da khoa

Extraction hoan tat 1.120/1.120 record, khong co loi; count, order, schema va `evidence_span` deu dat. Eligibility da predeclare giu lai 106 record nhung chi tao 64 information set duy nhat theo `archive_capture_at`, thap hon nguong 96 information set va thieu 32 set. Artifact `paper/input/results/llm/v14/sec_rss_archive_predictive_v14/extraction_gate.json` vi vay dat `DATA_GATE_FAIL_STOP_BEFORE_TARGET_JOIN`. Khong target nao duoc tao, khong metric predictive nao duoc tinh va khong backtest nao duoc mo.
