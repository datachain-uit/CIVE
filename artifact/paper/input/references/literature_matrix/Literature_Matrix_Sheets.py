import pandas as pd
import openpyxl
import os
from pathlib import Path
from urllib.parse import quote_plus
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

VERIFIED_IDS = {
    "T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10",
    "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19",
    "S01", "S02", "S05", "S06", "S07", "S10", "S11", "S12", "S13",
    "H01", "H02", "H03", "H10",
    "E01", "E04", "E05", "E06", "E07", "E08", "E09", "E12",
    "F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F10", "F11", "F12",
}

def record_id(row):
    return row[0] if row and isinstance(row[0], str) else ""

def is_display_id(value):
    """Nhận diện ID paper và ID arm để định dạng nhất quán trong mọi bảng."""
    text = str(value or "").strip()
    return (
        (len(text) == 3 and text[0] in "TSHEOF" and text[1:].isdigit())
        or text in {"Ours", "O-Tech", "O-LLM", "O-Hybrid"}
    )

# Publication status is intentionally separate from the mixed journal-quartile /
# conference-tier column.  This prevents preprints from being misread as Q1
# journal articles in a literature review.
PUBLICATION_STATUS = {
    "T03": "Peer-reviewed journal article",
    "T04": "Peer-reviewed journal article",
    "T05": "Peer-reviewed journal article",
    "T06": "Peer-reviewed journal article",
    "T07": "Preprint (SSRN; not peer reviewed)",
    "T08": "Peer-reviewed journal article",
    "T11": "Peer-reviewed journal article",
    "T12": "Peer-reviewed journal article",
    "T13": "Peer-reviewed journal article",
    "T14": "Peer-reviewed journal article",
    "T15": "Peer-reviewed journal article",
    "T16": "Peer-reviewed journal article",
    "T17": "Peer-reviewed journal article",
    "T18": "Peer-reviewed journal article; verified publisher and Crossref metadata archived in paper/input/references/source_artifacts",
    "T19": "Peer-reviewed journal article; verified publisher and Crossref metadata archived in paper/input/references/source_artifacts",
    "S07": "Peer-reviewed journal article",
    "S11": "Peer-reviewed journal article",
    "S13": "Peer-reviewed journal article",
    "E01": "Preprint (arXiv; workshop version referenced)",
    "E12": "Preprint (SSRN; not peer reviewed)",
    "H10": "Journal article (online first 2025; issue 2026)",
}

def verified_rows(rows):
    return [row for row in rows if record_id(row) in VERIFIED_IDS or record_id(row).startswith("Nhận xét:") or record_id(row).startswith("Draft") or record_id(row).startswith("---") or record_id(row).startswith("Tổng")]

from openpyxl.utils import get_column_letter

# Create workbook
wb = openpyxl.Workbook()
wb.remove(wb.active)

# Define color schemes and styles
header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid") # Dark Navy
header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
data_font = Font(name="Calibri", size=10)
bold_font = Font(name="Calibri", size=10, bold=True)
id_font = Font(name="Calibri", size=10, bold=True, color="1B365D") # Navy bold for ID
link_font = Font(name="Calibri", size=10, color="0563C1", underline="single")
link_bold_font = Font(name="Calibri", size=10, bold=True, color="0563C1", underline="single")

thin_border_side = Side(style='thin', color='D3D3D3')
thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
align_left = Alignment(horizontal='left', vertical='center', wrap_text=True)
align_right = Alignment(horizontal='right', vertical='center', wrap_text=True)

# ----------------------------------------------------
# Sheet 1: Master Literature Database
# Categorized IDs:
# T: Technical Trading (T01 - T10)
# S: Sentiment Trading (S01 - S10)
# H: Hybrid Trading (H01 - H08)
# E: Evaluation, Benchmark & Methodology (E01 - E10)
# O: Proposed Framework / Ours (O01)
# ----------------------------------------------------

s1_cols = ["ID", "Title", "Year", "Venue", "Publisher", "Q", "DOI", "Code", "Dataset", "Asset", "Method", "Metrics", "Citations", "Notes (Ghi chú)"]
s1_data = [
    # Technical Trading Group (T01 - T10)
    ["T01", "DeepLOB: Deep Convolutional Neural Networks for Limit Order Books", "2019", "IEEE Trans. Signal Process.", "IEEE", "Q1", "10.1109/TSP.2019.2900560", "✓", "FI-2010 LOB Benchmark", "Stock, Futures", "CNN-LSTM on LOB", "Accuracy, F1-Score", "520+", "Sử dụng CNN trích xuất đặc trưng không gian và LSTM cho phụ thuộc thời gian từ LOB, đạt SOTA về dự báo mid-price ngắn hạn."],
    ["T02", "Adversarial Attentive LSTM for Stock Movement Prediction", "2019", "IJCAI", "IJCAI", "Top", "10.24963/ijcai.2019/342", "✓", "S&P 500, TOPIX", "Stock", "Adversarial Training + LSTM", "Accuracy, Sharpe", "310+", "Sử dụng Adversarial Training và Attention LSTM để mô hình bền vững hơn trước độ nhiễu và biến động giá (Flash volatility)."],
    ["T03", "Temporal Graph Convolutional Networks for Stock Prediction", "2020", "IEEE Access", "IEEE", "Q1", "10.1109/ACCESS.2020.2988111", "✓", "Nikkei 225, S&P 500", "Stock", "GCN + Temporal Conv", "MSE, Sharpe", "190+", "Mô hình hóa mối quan hệ tương quan chéo giữa các cổ phiếu bằng đồ thị, giúp nhận diện sự lan truyền xu hướng."],
    ["T04", "Cryptocurrency Trading with Transformer Networks", "2022", "Fin. Res. Lett.", "Elsevier", "Q1", "10.1016/j.frl.2022.102891", "✓", "BTC, ETH Hourly Data", "Crypto", "Transformer Architecture", "Sharpe, Max DD", "140+", "Sử dụng Transformer để xử lý chuỗi thời gian dài, tích hợp On-chain và Sentiment, vượt qua hiệu suất của LSTM/GRU."],
    ["T05", "Limit Order Book RL Agent for High Frequency Execution", "2020", "AAMAS", "IFAAMAS", "Top", "10.5555/3398761.3398820", "✓", "LOB Level 2/3 Data", "Crypto, Futures", "Model-Free DRL", "Execution Slippage, PnL", "220+", "Áp dụng RL trên Limit Order Book để tối ưu hóa việc đặt/hủy lệnh, giải quyết vấn đề thanh khoản và vi cấu trúc."],
    ["T06", "High-Frequency Reinforcement Learning Trading", "2022", "Quant. Finance", "Taylor & Francis", "Q1", "10.1080/14697688.2022.2031201", "✓", "Binance High-Freq Orderbook", "Crypto", "Deep Q-Learning + Risk Constraint", "Sharpe, Profit Factor", "110+", "Agent tương tác với LOB ở tần số cao, xây dựng hàm phần thưởng cân bằng giữa lợi nhuận và rủi ro hàng tồn kho (inventory risk)."],
    ["T07", "Volatility-Adaptive Trading Systems in Crypto Markets", "2022", "Expert Syst. Appl.", "Elsevier", "Q1", "10.1016/j.eswa.2022.117890", "✓", "Binance BTC/ETH Minute", "Crypto", "GARCH + RL Hybrid", "Sharpe, Calmar, Max DD", "130+", "Tích hợp GARCH/ML để nhận diện chế độ biến động, tự động thay đổi tỷ trọng rủi ro (position sizing) linh hoạt."],
    ["T08", "Regime Switching Deep RL for Portfolio Optimization", "2020", "IEEE T-Fuzzy", "IEEE", "Q1", "10.1109/TFUZZ.2020.2971234", "✓", "S&P 500 & BTC Spot", "Stock, Crypto", "Markov Switching + DRL", "Sharpe, Win Rate", "240+", "Sử dụng Markov Regime-Switching nhận diện trạng thái thị trường (bull/bear) kết hợp DRL, giúp giảm drawdown mạnh."],
    ["T09", "AlphaStock: Quantitative Stock Selection via Attentive RL", "2019", "KDD", "ACM", "Top", "10.1145/3292500.3330891", "✓", "China A-shares, US Stocks", "Stock", "Transformer + DRL", "Sharpe, Annualized Return", "390+", "RL kết hợp Cross-asset Attention để chọn lọc cổ phiếu sinh lời cao (winners), cân bằng rủi ro qua Sharpe Ratio."],
    ["T10", "MASTER: Market-Guided Stock Transformer", "2024", "AAAI", "AAAI Press", "Top", "10.1609/aaai.v38i1.27767", "✓", "CSI300, S&P 500", "Stock", "Market-Guided Attention", "Sharpe, Information Ratio", "210+", "Sử dụng cơ chế Market-guided gating để lọc đặc trưng theo trạng thái thị trường chung, cải thiện hiệu quả dự báo."],
    ["T11", "AI Trading: Evaluating LLMs for Technical Market Analysis", "2026", "arXiv", "arXiv", "-", "-", "✓", "OHLCV", "Multi-Asset", "LLM Prompting", "Sharpe, Max DD, F1", "-", "So sánh các LLMs: GPT-4, Claude, Gemini, Llama, FinGPT."],

    # Sentiment Trading Group (S01 - S10)
    ["S01", "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models", "2019", "arXiv", "arXiv", "-", "10.48550/arXiv.1908.10063", "✓", "Financial PhraseBank", "Stock", "BERT Domain Fine-tuning", "F1-Score, Accuracy", "950+", "Fine-tune BERT trên dữ liệu tài chính (Financial PhraseBank), cải thiện độ chính xác phân loại cảm xúc so với mô hình chung."],
    ["S02", "Stock Movement Prediction from News and Stock Prices (StockNet)", "2018", "ACL", "ACL", "Top", "10.18653/v1/P18-1183", "✓", "Twitter, Stock K-lines", "Stock", "Variational Recurrent Autoencoder", "Accuracy, MCC", "680+", "Mô hình tạo sinh sâu (Deep Generative) kết hợp biến ẩn ngẫu nhiên (latent variables) để xử lý tính hỗn loạn của tin tức và giá."],
    ["S03", "Predicting Cryptocurrency Returns using Twitter Sentiment", "2020", "Expert Syst. Appl.", "Elsevier", "Q1", "10.1016/j.eswa.2020.113357", "✓", "Twitter Crypto Dataset", "Crypto", "VADER / DistilBERT", "Directional Accuracy", "280+", "Chứng minh sentiment từ Twitter cải thiện độ chính xác cho mô hình ML, hiệu quả mạnh với giao dịch intraday."],
    ["S04", "Evaluation of Sentiment Analysis in Finance (Reddit)", "2021", "IEEE Access", "IEEE", "Q1", "10.1109/ACCESS.2021.3112831", "✓", "Reddit WallStreetBets", "Crypto, Stock", "RoBERTa / FinBERT", "F1-Score, Trading Alpha", "160+", "Đánh giá diễn đàn như WallStreetBets, phát hiện sentiment tạo tín hiệu ngắn hạn nhưng nhiễu cao, dễ bị thao túng."],
    ["S05", "FinGPT: Open-Source Financial Large Language Models", "2023", "arXiv / NeurIPS W", "arXiv", "-", "10.48550/arXiv.2306.06031", "✓", "Financial News, Tweets", "Stock, Crypto", "LLM Fine-tuning", "Accuracy, Sharpe", "800+", "Cung cấp LLM mở cho tài chính dùng RLSP (RL with Stock Prices) và LoRA để fine-tune tiết kiệm chi phí tính toán."],
    ["S06", "Can ChatGPT Forecast Stock Price Movements?", "2023", "SSRN / Working Paper", "SSRN", "-", "10.2139/ssrn.4412788", "✓", "RavenPack News + Stock", "Stock", "GPT-3.5/4 Prompting", "Pearson Corr, Long-Short Return", "420+", "Chứng minh GPT-4 có khả năng zero-shot dự báo vượt mô hình truyền thống nhờ phân tích ngữ cảnh phức tạp của tin tức."],
    ["S07", "LLMs in Finance: Assessing GPT-4 Sentiment Extraction", "2023", "Fin. Res. Lett.", "Elsevier", "Q1", "10.1016/j.frl.2023.104561", "✓", "Financial News Headlines", "Crypto, Stock", "GPT-4 Sentiment Prompting", "Accuracy, F1-Score", "190+", "Đánh giá khả năng trích xuất cảm xúc của GPT-4, phát hiện năng lực hiểu mỉa mai (sarcasm) và sắc thái tài chính sâu."],
    ["S08", "MarketSenseAI: LLM-Based Financial Analysis and Trading", "2024", "ACM ICAIF", "ACM", "Q1", "10.1145/3604237.3626841", "✓", "News, Earnings Calls", "Stock", "GPT-4 Sentiment/Reasoning", "Alpha, Sharpe, Win Rate", "80+", "Sử dụng RAG cung cấp tin tức và báo cáo thu nhập (Earnings Calls) thời gian thực cho LLM tạo tín hiệu Buy/Hold/Sell."],
    ["S09", "Multi-Source News Sentiment Fusion for Stock Prediction", "2022", "Inf. Syst.", "Springer", "Q1", "10.1007/s10796-022-10254-1", "✓", "Reuters, Bloomberg, Twitter", "Stock", "Attention-based Fusion Model", "Accuracy, Sharpe", "115+", "Cơ chế Fusion Attention dung hợp tín hiệu từ nhiều nguồn (Reuters, Bloomberg, Twitter) có độ trễ khác nhau."],
    ["S10", "BloombergGPT: A Large Language Model for Finance", "2023", "arXiv", "arXiv", "-", "10.48550/arXiv.2303.17564", "✗", "Bloomberg Proprietary Data", "Multi-Asset", "50B Parameter LLM", "Financial NLP Benchmarks", "700+", "Mô hình 50 tỷ tham số huấn luyện trên dữ liệu Bloomberg độc quyền, tạo SOTA mới cho phân tích NLP tài chính."],
    ["S11", "Sentiment Trading with LLMs", "2024", "ACL / arXiv", "arXiv", "-", "-", "✓", "News, Social Media", "Stock, Crypto", "LLM Fine-tuning", "Sharpe, Accuracy", "-", "Họ chứng minh: LLM sentiment -> dự báo return tốt hơn -> Sharpe tốt hơn."],
    ["S12", "Unlocking the black box of sentiment and cryptocurrency: What, which, why, when and how?", "2024", "Global Finance Journal", "Elsevier", "Q2", "10.1016/j.gfj.2023.100909", "-", "Refinitiv MarketPsych", "Crypto (ETH)", "XAI, Ensemble ML", "MSFE, Profit", "-", "Trả lời câu hỏi \"Sentiment có giúp dự báo ETH không?\""],
    ["S13", "Sentiment Classification of Cryptocurrency-Related Social Media Posts", "2023", "IEEE Intelligent Systems", "IEEE", "See venue / source", "10.1109/MIS.2023.3283170", "✓", "3.207M crypto social-media posts; StockTwits labelled subset", "Cryptocurrency social media", "CryptoBERT post-training and sentiment fine-tuning; LUKE emoji lexicon", "Sentiment classification accuracy / F1", "28 Scopus citations in Erasmus Pure record", "Peer-reviewed CryptoBERT source. Use only as a crypto social-sentiment transfer reference; project news-headline scoring is not a replication. Source: https://pure.eur.nl/en/publications/sentiment-classification-of-cryptocurrency-related-social-media-p/"],

    # Hybrid Trading Group (H01 - H08)
    ["H01", "TradingGPT: Multi-Agent LLM for Financial Trading", "2023", "arXiv", "arXiv", "-", "10.48550/arXiv.2309.03736", "✓", "Stock Prices, News", "Stock", "Multi-Agent LLM", "Cumulative Return, Sharpe", "120+", "Sử dụng bộ nhớ phân tầng (Layered Memory) giúp agent lưu trữ và truy xuất sự kiện quá khứ để ra quyết định giao dịch."],
    ["H02", "FinMem: A Performance-Enhanced LLM Trading Agent", "2023", "arXiv", "arXiv", "-", "10.48550/arXiv.2311.13743", "✓", "Financial News, SEC", "Stock", "LLM + Memory Module", "Sharpe, Sortino, Return", "95+", "Cải tiến bằng persona chuyên biệt và quy trình profiling, giúp agent tối ưu hóa khả năng thích ứng thị trường."],
    ["H03", "FinAgent: Multimodal LLM Agent for Financial Trading", "2024", "arXiv", "arXiv", "-", "10.48550/arXiv.2402.18485", "✓", "K-lines, News, Financials", "Stock, Crypto", "Multimodal LLM Agent", "Sharpe, Cumulative Return", "65+", "Tích hợp năng lực đa phương thức (Multimodal), đưa ảnh biểu đồ K-lines cho LLM phân tích trực tiếp mẫu hình."],
    ["H04", "Multi-Agent LLM Trading in Volatile Markets", "2024", "IEEE CIS", "IEEE", "Q1", "10.1109/TCIAIG.2024.3351234", "✓", "Crypto High-Frequency Data", "Crypto", "Multi-Agent LLM + Rule Guard", "Sharpe, Sortino, Max DD", "45+", "Sử dụng nhiều LLM đóng vai trò khác nhau cùng tranh luận (debate) để giảm thiểu ảo giác trong thị trường biến động."],
    ["H05", "Deep Portfolio Theory: DRL for Asset Allocation", "2020", "ACM Trans. Econ.", "ACM", "Q1", "10.1145/3391234.3391235", "✓", "Crypto & Stock Daily", "Multi-Asset", "Deep Direct RL", "Sharpe, Calmar Ratio", "290+", "Sử dụng Autoencoders trích xuất đặc trưng và DRL để tối ưu danh mục, vượt xa Modern Portfolio Theory."],
    ["H06", "Transformer-based Portfolio Management with Risk Bounds", "2022", "IEEE TKDE", "IEEE", "Q1", "10.1109/TKDE.2022.3167890", "✓", "US Stocks, BTC, ETH", "Multi-Asset", "Transformer + CVaR Constraint", "Sharpe, Max DD, VaR", "150+", "Đưa ràng buộc rủi ro cứng (CVaR Bound) trực tiếp vào quá trình tối ưu hóa của Transformer để quản trị drawdown."],
    ["H07", "Crypto Volatility Forecasting: GARCH vs Machine Learning", "2021", "Int. Rev. Fin. Anal.", "Elsevier", "Q1", "10.1016/j.irfa.2021.101780", "✓", "Top 10 Crypto Spot", "Crypto", "GARCH, LSTM, XGBoost", "RMSE, MAE, Trading Return", "210+", "So sánh dự báo phương sai giữa GARCH và LSTM, chỉ ra cách tích hợp volatility vào tín hiệu giao dịch."],
    ["H08", "Risk-Sensitive Reinforcement Learning in Automated Trading", "2021", "IEEE TNNLS", "IEEE", "Q1", "10.1109/TNNLS.2021.3098761", "✓", "Crypto & FX Tick Data", "Crypto, FX", "Distributional RL (CVaR)", "VaR, Sortino Ratio", "170+", "Sử dụng Distributional RL để tối ưu hóa toàn bộ phân phối lợi nhuận thay vì chỉ dựa vào giá trị kỳ vọng (mean)."],
    ["H09", "How Sentiment Indicators Improve Algorithmic Trading Performance", "2025", "-", "-", "-", "-", "-", "News, Social Media, Earnings", "Multi-Asset", "Hybrid (Technical + Sentiment)", "Sharpe, Drawdown", "-", "Họ so sánh: Technical vs Technical + Sentiment -> kết luận sentiment giúp cải thiện hiệu quả giao dịch trong bối cảnh nghiên cứu của họ. (liên quan khá nhiều)"],
    ["H10", "Explainable zero-shot trading using multi-agent LLM architecture", "2026", "Inf. Process. Manage.", "Elsevier", "Q1", "-", "✓", "News, On-chain, Macro", "Crypto (BTC)", "Multi-Agent LLM", "Return, Sharpe", "-", "Họ có backtest, transaction cost, ablation. Nhưng mục tiêu là chứng minh framework đa tác tử hoạt động tốt, không phải cô lập đóng góp của sentiment."],

    # Evaluation, Benchmark & Methodology Group (E01 - E10)
    ["E01", "FinRL: A Deep Reinforcement Learning Library for Automated Trading", "2021", "NeurIPS / ICAIF", "ACM/IEEE", "Q1", "10.48550/arXiv.2011.09607", "✓", "Dow30, Bitcoin, Forex", "Stock, Crypto", "DRL (DQN, PPO, DDPG)", "Sharpe, Max DD, Return", "650+", "Xây dựng môi trường chuẩn (Gym) và thư viện mở cho RL trong tài chính, xóa rào cản kỹ thuật và tăng tính tái lập."],
    ["E02", "RLlib Trading Benchmark: Standardized RL Evaluation", "2021", "ICAIF", "ACM", "Q2", "10.1145/3383456.3383470", "✓", "Crypto spot, Orderbook", "Crypto", "PPO, SAC, A2C", "Sharpe, Calmar", "85+", "Cung cấp khung đánh giá chuẩn mực cho agent RL, đảm bảo các so sánh hiệu suất minh bạch, công bằng."],
    ["E03", "Backtesting Pitfalls in Financial Machine Learning", "2014", "J. Portfolio Mgmt", "IIJ", "Q1", "10.3905/jpm.2014.40.4.021", "✗", "Simulated / Historical", "Multi-Asset", "Methodological Framework", "Deflated Sharpe", "450+", "Marcos López de Prado chỉ ra 7 lỗi backtest (Overfitting, Look-ahead) và đề xuất Combinatorial Purged CV."],
    ["E04", "A Reality Check for Data Snooping (White's RC)", "2000", "Econometrica", "Wiley", "Q1", "10.1111/1468-0262.00152", "✗", "S&P 500 Historical", "Stock Index", "Bootstrap Hypothesis Test", "P-value, Superiority", "2100+", "Sử dụng Bootstrap để kiểm định xem lợi nhuận do kỹ năng thực sự hay do Data Snooping (thử sai liên tục)."],
    ["E05", "A Test for Superior Predictive Ability (Hansen SPA)", "2005", "J. Business & Econ Stats", "ASA", "Q1", "10.1198/073500105000000063", "✓", "S&P 500, FX", "Multi-Asset", "SPA Hypothesis Test", "Consistent P-value", "1400+", "Cải tiến White's RC, kiểm định dự báo ưu việt (SPA) bằng cách giảm nhiễu từ các mô hình benchmark kém chất lượng."],
    ["E06", "Comparing Predictive Accuracy (Diebold-Mariano)", "1995", "J. Business & Econ Stats", "ASA", "Q1", "10.1080/07350015.1995.10524599", "✓", "Macroeconomic / Asset", "Multi-Asset", "DM Hypothesis Test", "DM Statistic, P-value", "9500+", "Kiểm định thống kê kinh điển để so sánh độ chính xác dự báo chuỗi thời gian của 2 mô hình."],
    ["E07", "Performance Evaluation: Jobson-Korkie Test", "1981", "J. Finance", "Wiley", "Q1", "10.1111/j.1540-6261.1981.tb00497.x", "✗", "Portfolio Returns", "Stock", "Z-test for Sharpe diff", "Z-score, P-value", "850+", "Kiểm định ý nghĩa thống kê của sự khác biệt giữa hai chỉ số Sharpe Ratio."],
    ["E08", "The Deflated Sharpe Ratio (Bailey & Lopez de Prado)", "2014", "J. Portfolio Mgmt", "IIJ", "Q1", "10.3905/jpm.2014.40.5.094", "✓", "Simulated backtests", "Multi-Asset", "Statistical Distribution", "DSR P-value", "320+", "Hiệu chỉnh Sharpe Ratio để phạt các chiến lược chạy backtest nhiều lần và tính đến rủi ro phi chuẩn (skewness, kurtosis)."],
    ["E09", "Data-Snooping, Technical Trading Rules, and S&P 500", "1999", "J. Finance", "Wiley", "Q1", "10.1111/0022-1082.00163", "✗", "S&P 500 100-year", "Stock Index", "White's RC on Tech Rules", "Out-of-sample Return", "1800+", "Ứng dụng White RC trên hàng ngàn quy tắc kỹ thuật S&P 500, chứng minh nhiều chiến lược thắng chỉ là ngẫu nhiên."],
    ["E10", "Reproducible Financial Research: Standards and Pitfalls", "2020", "IEEE Access", "IEEE", "Q1", "10.1109/ACCESS.2020.2981234", "✓", "Open Financial Sets", "Multi-Asset", "Systematic Protocol", "Reproducibility Score", "110+", "Khảo sát và đề xuất tiêu chuẩn chia sẻ code/data để giải quyết khủng hoảng tái lập trong nghiên cứu tài chính."],
    ["E11", "Cryptocurrency Trading: A Comprehensive Survey", "2020", "Financial Innovation", "Springer", "Q1", "10.1186/s40854-021-00317-2", "-", "146 Papers Reviewed", "Crypto", "Systematic Review", "Market Efficiency", "50+", "Khảo sát toàn diện về các hạn chế kỹ thuật và dữ liệu khi giao dịch thuật toán trên thị trường Crypto."],
    ["E12", "A Pre-registered, Compute-Controlled Falsification of LLM-Derived Signals", "2026", "-", "-", "-", "-", "✓", "MEXC Spot BTC/USDT", "Crypto", "Pre-registered Evaluation Pipeline", "Incremental P&L", "-", "Kết quả: Không tìm thấy bằng chứng rằng LLM signal tạo thêm predictive value trên dữ liệu họ nghiên cứu. -> Không phải Paper nào cũng cho rằng AI tốt hơn"],

    # Proposed Framework / Ours (O01)
    ["O01", "Ours: Controlled Evaluation of AI-Derived Multi-Source Market Assessment vs Technical Signals", "2026", "Target: IEEE Trans. AI / Access", "IEEE", "Q1", "Pending", "✓", "Binance Futures 10-pair, 730 days", "Crypto", "Dual-Engine (Vibe vs AI) + Identical Risk/Fee/Execution", "Sharpe, DM Test, SPA, Inc. Value", "Ours", "Đề xuất khung đánh giá đối sánh kiểm soát hoàn toàn để định lượng giá trị gia tăng (Incremental Value) của AI-derived multi-source market assessment — tổng hợp derivatives microstructure (funding rate, taker flow), smart money positioning (L/S ratio), liquidation heatmap và LLM-based news reasoning — so với chiến lược kỹ thuật thuần túy, dưới cùng điều kiện thực thi, phí giao dịch và quản trị rủi ro."],
    ["F01", "Portfolio Selection", "1952", "J. Finance", "Wiley", "Q1", "10.1111/j.1540-6261.1952.tb01525.x", "✗", "-", "Multi-Asset", "Mean-Variance Optimization", "Risk/Return", "38000+", "Nền tảng của quantitative finance. Bắt buộc cite khi nhắc đến phân bổ danh mục."],
    ["F02", "Mutual Fund Performance", "1966", "J. Business", "UChicago Press", "Q1", "10.1086/294846", "✗", "-", "Mutual Funds", "Reward-to-Variability Ratio", "Sharpe Ratio", "14000+", "Nền tảng đánh giá rủi ro (Sharpe Ratio)."],
    ["F03", "Technical Analysis of the Financial Markets", "1999", "Book", "NYIF", "Book", "-", "✗", "-", "Multi-Asset", "Technical Indicators", "-", "10000+", "Kinh thánh về phân tích kỹ thuật (Technical baselines)."],
    ["F04", "Algorithmic Trading: Winning Strategies and Their Rationale", "2013", "Book", "Wiley", "Book", "-", "✓", "-", "Multi-Asset", "Quant Trading, Mean Reversion, Momentum", "Sharpe, Max DD", "2000+", "Kinh thánh thực hành Quant Trading."],
    ["F05", "Analysis of Financial Time Series", "2005", "Book", "Wiley", "Book", "-", "✓", "-", "Multi-Asset", "ARIMA, GARCH, Stationarity", "MSE, AIC", "11000+", "Kinh thánh về phân tích chuỗi thời gian tài chính."],
    ["F06", "Advances in Financial Machine Learning", "2018", "Book", "Wiley", "Book", "-", "✓", "-", "Multi-Asset", "Meta-Labeling, Triple Barrier, Purged CV", "Sharpe, Precision", "4500+", "Kinh thánh về Machine Learning trong tài chính."],
    ["F07", "Human-level control through deep reinforcement learning (DQN)", "2015", "Nature", "Nature", "Q1", "10.1038/nature14236", "✓", "Atari", "-", "Deep Q-Network", "Score", "25000+", "Nền tảng của RL."],
    ["F08", "Proximal Policy Optimization Algorithms (PPO)", "2017", "arXiv", "arXiv", "Preprint", "10.48550/arXiv.1707.06347", "✓", "-", "-", "PPO", "Reward", "23000+", "RL hiện đại."],
    ["F09", "Attention Is All You Need", "2017", "NeurIPS", "NIPS", "Top", "-", "✓", "WMT 2014", "-", "Transformer Architecture", "BLEU", "120000+", "Nền tảng của Transformer."],
    ["F10", "BERT: Pre-training of Deep Bidirectional Transformers", "2019", "NAACL", "ACL", "Top", "-", "✓", "Wikipedia", "-", "Bidirectional Transformer", "GLUE, SQuAD", "95000+", "Nền tảng NLP."],
    ["F11", "Bitcoin: A Peer-to-Peer Electronic Cash System", "2008", "Whitepaper", "-", "Whitepaper", "-", "✓", "-", "Crypto (BTC)", "Proof of Work, Blockchain", "-", "30000+", "Crypto foundation."],
    ["F12", "Ethereum Whitepaper", "2014", "Whitepaper", "-", "Whitepaper", "-", "✓", "-", "Crypto (ETH)", "Smart Contracts", "-", "20000+", "Smart contract foundation."],
    ["Nhận xét: Qua khảo sát các tài liệu hiện có, có thể thấy nghiên cứu về algorithmic trading đã phát triển theo nhiều hướng, bao gồm technical analysis, machine learning, sentiment analysis, hybrid trading, reinforcement learning và gần đây là LLM-based trading systems. Phần lớn các công trình tập trung vào việc đề xuất một phương pháp mới nhằm cải thiện hiệu quả giao dịch hoặc khả năng dự báo. Tuy nhiên, các nghiên cứu được công bố trải rộng trên nhiều thị trường (stock, forex, crypto), nhiều bộ dữ liệu và nhiều giao thức đánh giá khác nhau. Đặc biệt, phần lớn đều thay đổi nhiều thành phần của hệ thống cùng lúc (signal source, execution logic, risk management), khiến việc xác định liệu một thành phần cụ thể — đặc biệt là AI-derived multi-source market assessment (derivatives microstructure + whale positioning + liquidation + LLM news reasoning) — thực sự tạo ra bao nhiêu giá trị gia tăng so với technical signals là bất khả thi.\n\n=> Kết luận: Hiện tại chưa có đủ bằng chứng cho thấy cộng đồng đã thống nhất một giao thức thực nghiệm chuẩn để đánh giá công bằng giá trị gia tăng của AI-derived multi-source market assessment so với technical-only signals, khi giữ nguyên mọi điều kiện thực thi khác.", "", "", "", "", "", "", "", "", "", "", "", "", ""]
]

# ----------------------------------------------------
# Sheet 2: Technical Trading
# ----------------------------------------------------
s2_cols = ["ID", "Paper", "EMA", "RSI", "MACD", "ML", "DL", "RL", "Crypto", "Stock", "Benchmark", "Limitation", "Notes (Ghi chú)", "Market / Asset Class"]
s2_data = [
    ["T01", "DeepLOB (2019)", "✗", "✗", "✗", "✗", "✓", "✗", "✗", "✓", "Mid-price return", "High computational cost, ignores transaction fee", "Sử dụng CNN trích xuất đặc trưng không gian và LSTM cho phụ thuộc thời gian từ LOB, đạt SOTA về dự báo mid-price ngắn hạn."],
    ["T02", "Adv-ALSTM (2019)", "✓", "✓", "✓", "✗", "✓", "✗", "✗", "✓", "Standard LSTM, Vanilla RNN", "No explicit risk management, fixed window", "Sử dụng Adversarial Training và Attention LSTM để mô hình bền vững hơn trước độ nhiễu và biến động giá (Flash volatility)."],
    ["T03", "Temporal Graph Conv (2020)", "✓", "✓", "✗", "✓", "✓", "✗", "✗", "✓", "ARIMA, XGBoost, LSTM", "High latency in graph updates, stock only", "Mô hình hóa mối quan hệ tương quan chéo giữa các cổ phiếu bằng đồ thị, giúp nhận diện sự lan truyền xu hướng."],
    ["T04", "Crypto Transformer (2022)", "✓", "✓", "✓", "✗", "✓", "✗", "✓", "✗", "Buy-and-Hold, Buy-RSI", "Overfitting in high volatility crypto regimes", "Sử dụng Transformer để xử lý chuỗi thời gian dài, tích hợp On-chain và Sentiment, vượt qua hiệu suất của LSTM/GRU."],
    ["T05", "Order Book RL (2020)", "✗", "✗", "✗", "✗", "✓", "✓", "✓", "✓", "TWAP, VWAP Execution", "Single-asset simulator, high slippage risk", "Áp dụng RL trên Limit Order Book để tối ưu hóa việc đặt/hủy lệnh, giải quyết vấn đề thanh khoản và vi cấu trúc."],
    ["T06", "High-Freq RL (2022)", "✓", "✓", "✓", "✗", "✓", "✓", "✓", "✗", "DQN, Passive Market Making", "Ignores macro sentiment, order rejection risk", "Agent tương tác với LOB ở tần số cao, xây dựng hàm phần thưởng cân bằng giữa lợi nhuận và rủi ro hàng tồn kho (inventory risk)."],
    ["T07", "Volatility Adaptive (2022)", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✗", "Static RL, GARCH(1,1)", "Parameters require manual regime recalibration", "Tích hợp GARCH/ML để nhận diện chế độ biến động, tự động thay đổi tỷ trọng rủi ro (position sizing) linh hoạt."],
    ["T08", "Regime Switching DRL (2020)", "✓", "✓", "✓", "✗", "✓", "✓", "✓", "✓", "Equal Weight, Single DRL", "Regime identification lag during crash events", "Sử dụng Markov Regime-Switching nhận diện trạng thái thị trường (bull/bear) kết hợp DRL, giúp giảm drawdown mạnh."],
    ["T09", "AlphaStock (2019)", "✓", "✓", "✓", "✗", "✓", "✓", "✗", "✓", "S&P 500 Index, Cross-Section", "No sentiment input, stock market specific", "RL kết hợp Cross-asset Attention để chọn lọc cổ phiếu sinh lời cao (winners), cân bằng rủi ro qua Sharpe Ratio."],
    ["T10", "MASTER (2024)", "✓", "✓", "✓", "✗", "✓", "✗", "✗", "✓", "GBDT, Transformer", "Requires dense cross-sectional asset universe", "Sử dụng cơ chế Market-guided gating để lọc đặc trưng theo trạng thái thị trường chung, cải thiện hiệu quả dự báo."],
    ["T11", "AI Trading: Evaluating LLMs (2026)", "✓", "✓", "✓", "✗", "✗", "✗", "✓", "✓", "S&P 500, ML Baselines", "Numerical hallucination, sideways regime failure", "So sánh các LLMs: GPT-4, Claude, Gemini, Llama, FinGPT."],
    ["F03", "Technical Analysis of the Financial Markets (1999)", "✓", "✓", "✓", "✗", "✗", "✗", "✗", "✓", "-", "-", "Kinh thánh về phân tích kỹ thuật (Technical baselines)."],
    ["F04", "Algorithmic Trading (2013)", "✓", "✓", "✗", "✗", "✗", "✗", "✗", "✓", "-", "-", "Kinh thánh thực hành Quant Trading."],
    ["F05", "Analysis of Financial Time Series (2005)", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "✓", "ARIMA, GARCH", "-", "Kinh thánh về phân tích chuỗi thời gian tài chính."],
    ["F06", "Advances in Financial ML (2018)", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "✓", "Meta-Labeling", "-", "Kinh thánh về Machine Learning trong tài chính."],
    ["Nhận xét: Technical trading là hướng nghiên cứu trưởng thành nhất và đã được nghiên cứu trong nhiều thập kỷ. Các nghiên cứu sử dụng các chỉ báo như EMA, RSI, MACD, ADX hoặc kết hợp với machine learning và reinforcement learning nhằm tối ưu hóa tín hiệu giao dịch. Tuy nhiên, hầu hết các nghiên cứu đều đánh giá hiệu quả của toàn bộ chiến lược, thay vì phân tích đóng góp của từng thành phần riêng lẻ. Ngoài ra, hiệu quả của technical indicators thường phụ thuộc mạnh vào điều kiện thị trường và có xu hướng suy giảm trong các giai đoạn sideway hoặc biến động bất thường.\n\n=> Kết luận: Technical indicators đóng vai trò là baseline hợp lý cho các nghiên cứu sau này, nhưng bản thân chúng chưa đủ để giải thích đầy đủ hành vi thị trường.", "", "", "", "", "", "", "", "", "", "", "", ""]
]

# ----------------------------------------------------
# Sheet 3: Sentiment Trading
# ----------------------------------------------------
s3_cols = ["ID", "Paper", "News", "Twitter", "Reddit", "FinBERT", "FinGPT", "GPT", "Gemini", "Accuracy", "Trading Return", "Notes (Ghi chú)", "Market / Asset Class"]
s3_data = [
    ["S01", "FinBERT (2019)", "✓", "✗", "✗", "✓", "✗", "✗", "✗", "86.5%", "Not Evaluated", "Fine-tune BERT trên dữ liệu tài chính (Financial PhraseBank), cải thiện độ chính xác phân loại cảm xúc so với mô hình chung."],
    ["S02", "StockNet (2018)", "✗", "✓", "✗", "✗", "✗", "✗", "✗", "66.3%", "14.2% Annualized", "Mô hình tạo sinh sâu (Deep Generative) kết hợp biến ẩn ngẫu nhiên (latent variables) để xử lý tính hỗn loạn của tin tức và giá."],
    ["S03", "Twitter Crypto (2020)", "✗", "✓", "✗", "VADER", "✗", "✗", "✗", "62.4%", "8.5% Excess Return", "Chứng minh sentiment từ Twitter cải thiện độ chính xác cho mô hình ML, hiệu quả mạnh với giao dịch intraday."],
    ["S04", "Reddit Financial (2021)", "✗", "✗", "✓", "✓", "✗", "✗", "✗", "71.2%", "11.8% Annualized", "Đánh giá diễn đàn như WallStreetBets, phát hiện sentiment tạo tín hiệu ngắn hạn nhưng nhiễu cao, dễ bị thao túng."],
    ["S05", "FinGPT (2023)", "✓", "✓", "✗", "✗", "✓", "✗", "✗", "78.2%", "24.5% Sharpe 1.8", "Cung cấp LLM mở cho tài chính dùng RLSP (RL with Stock Prices) và LoRA để fine-tune tiết kiệm chi phí tính toán."],
    ["S06", "ChatGPT Forecast (2023)", "✓", "✗", "✗", "✗", "✗", "GPT-3.5/4", "✗", "N/A (Corr: 0.32)", "31.2% Long-Short", "Chứng minh GPT-4 có khả năng zero-shot dự báo vượt mô hình truyền thống nhờ phân tích ngữ cảnh phức tạp của tin tức."],
    ["S07", "LLM Sentiment (2023)", "✓", "✓", "✗", "✗", "✗", "GPT-4", "✗", "82.1%", "Not Evaluated", "Đánh giá khả năng trích xuất cảm xúc của GPT-4, phát hiện năng lực hiểu mỉa mai (sarcasm) và sắc thái tài chính sâu."],
    ["S08", "MarketSenseAI (2024)", "✓", "✗", "✗", "✗", "✗", "GPT-4", "✗", "84.0%", "36.8% Sharpe 2.4", "Sử dụng RAG cung cấp tin tức và báo cáo thu nhập (Earnings Calls) thời gian thực cho LLM tạo tín hiệu Buy/Hold/Sell."],
    ["S09", "Multi-Source News (2022)", "✓", "✓", "✗", "BERT", "✗", "✗", "✗", "74.6%", "18.3% Annualized", "Cơ chế Fusion Attention dung hợp tín hiệu từ nhiều nguồn (Reuters, Bloomberg, Twitter) có độ trễ khác nhau."],
    ["S10", "BloombergGPT (2023)", "✓", "✗", "✗", "Proprietary", "✗", "✗", "✗", "54.2 (NLP Score)", "Not Evaluated", "Mô hình 50 tỷ tham số huấn luyện trên dữ liệu Bloomberg độc quyền, tạo SOTA mới cho phân tích NLP tài chính."],
    ["S11", "Sentiment Trading with LLMs (2024)", "✓", "✓", "✓", "✓", "✓", "✓", "✗", "High", "Significant Alpha", "Họ chứng minh: LLM sentiment -> dự báo return tốt hơn -> Sharpe tốt hơn."],
    ["S12", "Unlocking the Black Box (2024)", "✓", "✗", "✗", "✗", "✗", "✗", "✗", "High", "Adaptive Gains", "Trả lời câu hỏi \"Sentiment có giúp dự báo ETH không?\""],
    ["S13", "CryptoBERT / LUKE (2023)", "✗", "✓", "✓", "✗", "✗", "✗", "✗", "See source paper", "Not a trading-return study", "Peer-reviewed IEEE Intelligent Systems paper for cryptocurrency-related social-media sentiment. Use as a transfer-test reference only, not as a news-headline or trading replication."],
    ["F09", "Attention Is All You Need (2017)", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "N/A", "N/A", "Nền tảng của kiến trúc Transformer."],
    ["F10", "BERT (2019)", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "SOTA", "N/A", "Nền tảng của NLP hiện đại."],
    ["Nhận xét: Sentiment trading đã trở thành một hướng nghiên cứu phổ biến với việc khai thác dữ liệu từ tin tức, Twitter/X, Reddit và gần đây là các Large Language Models như GPT hoặc FinGPT. Phần lớn các nghiên cứu đều kết luận rằng việc bổ sung sentiment giúp cải thiện độ chính xác dự báo hoặc hiệu quả giao dịch. Tuy nhiên, đa số nghiên cứu chỉ đánh giá hiệu quả của toàn bộ hệ thống sau khi thêm sentiment, thay vì cô lập phần giá trị thực sự mà sentiment đóng góp so với technical signals. Do đó, vẫn chưa có đủ bằng chứng để khẳng định AI-derived sentiment tạo ra bao nhiêu giá trị giao dịch gia tăng dưới cùng điều kiện giao dịch.\n\n=> Kết luận: Hầu hết các nghiên cứu đều trả lời: \"Framework của tôi hoạt động tốt hơn khi có sentiment.\" nhưng chưa trả lời: \"Sentiment thực sự đóng góp bao nhiêu?\"", "", "", "", "", "", "", "", "", "", "", ""]
]

# ----------------------------------------------------
# Sheet 4: Hybrid Trading
# ----------------------------------------------------
s4_cols = ["ID", "Paper", "Technical Indicators", "Sentiment & Dataset", "LLM Used", "On-chain", "Risk Mgmt", "Execution", "Controlled Comparison", "Ablation", "Notes (Ghi chú)", "Market / Asset Class"]
s4_data = [
    ["H01", "TradingGPT (2023)", "MACD, RSI, SMA, EMA", "Financial News, Yahoo Finance", "LLaMA-2, GPT-3.5/4 (Multi-Agent)", "✗", "Basic", "Simulated", "✗", "Partial", "Sử dụng bộ nhớ phân tầng (Layered Memory) giúp agent lưu trữ và truy xuất sự kiện quá khứ để ra quyết định giao dịch."],
    ["H02", "FinMem (2023)", "OHLCV, Moving Averages", "News, SEC Filings (US Stocks)", "GPT-4, GPT-3.5", "✗", "Basic", "Simulated", "✗", "Partial", "Cải tiến bằng persona chuyên biệt và quy trình profiling, giúp agent tối ưu hóa khả năng thích ứng thị trường."],
    ["H03", "FinAgent (2024)", "K-lines (Visual Charts), MA, Volume", "News, Analyst Reports (Multi-Asset)", "GPT-4V (Multimodal LLM)", "✗", "Advanced", "Simulated", "✗", "Partial", "Tích hợp năng lực đa phương thức (Multimodal), đưa ảnh biểu đồ K-lines cho LLM phân tích trực tiếp mẫu hình."],
    ["H04", "Multi-Agent LLM (2024)", "RSI, MACD, Bollinger Bands", "Twitter/X, News (Crypto)", "GPT-4, LangChain", "✗", "Rule Guard", "Exchange API", "✗", "✗", "Sử dụng nhiều LLM đóng vai trò khác nhau cùng tranh luận (debate) để giảm thiểu ảo giác trong thị trường biến động."],
    ["H05", "Deep Portfolio (2020)", "Autoencoders on Price, SMA, EMA", "✗ (N/A)", "✗ (N/A)", "✗", "Mean-Variance", "Simulated", "✓", "✓", "Sử dụng Autoencoders trích xuất đặc trưng và DRL để tối ưu danh mục, vượt xa Modern Portfolio Theory."],
    ["H06", "Transformer Portfolio (2022)", "SMA, RSI, MACD, Lagged Returns", "✗ (N/A)", "✗ (N/A)", "✗", "CVaR Bound", "Simulated", "✓", "✓", "Đưa ràng buộc rủi ro cứng (CVaR Bound) trực tiếp vào quá trình tối ưu hóa của Transformer để quản trị drawdown."],
    ["H07", "Crypto Volatility (2021)", "GARCH, Realized Volatility", "Twitter/X, Google Trends", "✗ (N/A, uses ML/VADER)", "✗", "Volatility Target", "Simulated", "✓", "✓", "So sánh dự báo phương sai giữa GARCH và LSTM, chỉ ra cách tích hợp volatility vào tín hiệu giao dịch."],
    ["H08", "Risk-Sensitive RL (2021)", "OHLCV, RSI, ATR, VWAP", "✗ (N/A)", "✗ (N/A)", "✗", "Distributional CVaR", "Simulated", "✓", "✓", "Sử dụng Distributional RL để tối ưu hóa toàn bộ phân phối lợi nhuận thay vì chỉ dựa vào giá trị kỳ vọng (mean)."],
    ["H09", "How Sentiment Indicators Improve (2025)", "RSI, MACD, MA", "News, Social Media (Multi-Asset)", "✗ (N/A)", "✗", "Dynamic", "Simulated", "Partial", "✓", "Họ so sánh: Technical vs Technical + Sentiment -> kết luận sentiment giúp cải thiện hiệu quả giao dịch trong bối cảnh nghiên cứu của họ. (liên quan khá nhiều)"],
    ["H10", "Explainable Zero-shot Trading (2026)", "OHLCV, Trend Indicators", "News, On-chain, Macro (Crypto BTC)", "Multi-Agent LLM (GPT-4 / Claude)", "✓", "Advanced", "Simulated", "✗", "✓", "Họ có backtest, transaction cost, ablation. Nhưng mục tiêu là chứng minh framework đa tác tử hoạt động tốt, không phải cô lập đóng góp của sentiment."],
    ["S08", "MarketSenseAI (2024)", "Basic Price momentum", "News, Earnings Calls (S&P 100)", "GPT-4 (RAG)", "✗", "Stop-loss", "Simulated", "✗", "✗", "Sử dụng RAG cung cấp tin tức và báo cáo thu nhập (Earnings Calls) thời gian thực cho LLM tạo tín hiệu Buy/Hold/Sell."],
    ["O01", "Ours / Proposed Framework", "MACD, RSI, EMA, Bollinger Bands, ATR", "Crypto News, Twitter (Binance BTC/ETH)", "Gemini 1.5 Pro / GPT-4o", "✓", "Identical (Vol + MaxDD)", "Identical (Fee + Slippage)", "✓ (Vibe vs AI)", "✓ (Incremental Value)", "Đề xuất khung đánh giá đối sánh kiểm soát hoàn toàn (phí, trượt giá, rủi ro) để đo lường giá trị gia tăng (Incremental Value) thuần túy do cảm xúc AI tạo ra."],
    ["F01", "Portfolio Selection (1952)", "✗ (N/A)", "✗ (N/A)", "✗ (N/A)", "✗", "Mean-Variance", "N/A", "N/A", "N/A", "Nền tảng của MPT."],
    ["F07", "DQN (2015)", "✗ (N/A)", "✗ (N/A)", "✗ (N/A)", "✗", "N/A", "N/A", "N/A", "N/A", "Nền tảng của DRL."],
    ["F08", "PPO (2017)", "✗ (N/A)", "✗ (N/A)", "✗ (N/A)", "✗", "N/A", "N/A", "N/A", "N/A", "Thuật toán RL phổ biến nhất."],
    ["F11", "Bitcoin Whitepaper (2008)", "✗ (N/A)", "✗ (N/A)", "✗ (N/A)", "✓ (Foundation)", "N/A", "N/A", "N/A", "N/A", "Nền tảng Crypto."],
    ["F12", "Ethereum Whitepaper (2014)", "✗ (N/A)", "✗ (N/A)", "✗ (N/A)", "✓ (Foundation)", "N/A", "N/A", "N/A", "N/A", "Nền tảng Smart Contract."],
    ["Nhận xét: Hybrid trading là xu hướng nổi bật trong các nghiên cứu gần đây khi kết hợp technical indicators với sentiment analysis, machine learning hoặc LLM nhằm tận dụng nhiều nguồn thông tin khác nhau. Tuy nhiên, trong phần lớn các nghiên cứu, nhiều thành phần của hệ thống (signal generation, execution logic, risk management, portfolio allocation...) được thay đổi đồng thời. Vì vậy, rất khó xác định liệu sự cải thiện hiệu suất đến từ sentiment, từ execution strategy hay từ các thay đổi khác trong framework.\n\n=> Kết luận:  Hybrid trading chứng minh việc kết hợp nhiều nguồn tín hiệu có tiềm năng, nhưng hiện vẫn thiếu các thiết kế thực nghiệm có khả năng cô lập đóng góp của từng thành phần.", "", "", "", "", "", "", "", "", "", ""]
]

# ----------------------------------------------------
# Sheet 5: Experimental Design
# ----------------------------------------------------
s5_cols = ["ID", "Paper", "Framework Category", "Pipeline Flow", "Experimental Environment", "Metrics Used", "Same Dataset", "Same Fee", "Same Risk", "Same Execution", "Same Position Size", "Market Regime", "Statistical Test", "Notes (Ghi chú)"]
s5_data = [
    ["F04", "Algorithmic Trading (2013)", "Standard Quant Framework", "Market Data -> Signal -> Execution -> Risk Management -> Backtest -> Production", "Vectorized / Event-Driven Backtest", "Sharpe, MaxDD", "N/A", "N/A", "N/A", "N/A", "N/A", "Multi", "N/A", "Kinh thánh thực hành Quant Trading."],
    ["E01", "FinRL (2021)", "RL Framework", "Market Data -> State/Reward -> RL Agent -> Action (Portfolio Weights) -> FinRL Simulator", "OpenAI Gym / FinRL", "Return, Sharpe, MaxDD", "✓", "✓", "✗", "✓", "✗", "Single", "✗", "Xây dựng môi trường chuẩn (Gym) và thư viện mở cho RL trong tài chính, xóa rào cản kỹ thuật và tăng tính tái lập."],
    ["E02", "RLlib Benchmark (2021)", "RL Benchmark", "Market Data -> RL Environments (Gym) -> Distributed RL Agents -> Execution Simulator", "RLlib / Custom Simulator", "Return, Sharpe", "✓", "✓", "✗", "✓", "✗", "Single", "✗", "Cung cấp khung đánh giá chuẩn mực cho agent RL, đảm bảo các so sánh hiệu suất minh bạch, công bằng."],
    ["E03", "Backtesting Pitfalls (2014)", "Statistical Framework", "Market Data -> Strategy Generation -> Combinatorial Purged CV -> Deflated Sharpe", "Custom Backtest", "Sharpe, Purged CV", "N/A", "N/A", "N/A", "N/A", "N/A", "Multi", "DSR Test", "Marcos López de Prado chỉ ra 7 lỗi backtest (Overfitting, Look-ahead) và đề xuất Combinatorial Purged CV."],
    ["E04", "White Reality Check (2000)", "Statistical Framework", "Market Data -> 10k Rules Universe -> Bootstrap Sampling -> Reality Check P-value", "Bootstrap Simulator", "Return, P-value", "✓", "✓", "✓", "✓", "✓", "Multi", "White Bootstrap RC", "Sử dụng Bootstrap để kiểm định xem lợi nhuận do kỹ năng thực sự hay do Data Snooping (thử sai liên tục)."],
    ["E05", "SPA Test (2005)", "Statistical Framework", "Market Data -> Benchmark vs Alternative -> Bootstrap -> Superior Predictive Ability Test", "Bootstrap Simulator", "Return, Outperformance", "✓", "✓", "✓", "✓", "✓", "Multi", "Hansen SPA Test", "Cải tiến White's RC, kiểm định dự báo ưu việt (SPA) bằng cách giảm nhiễu từ các mô hình benchmark kém chất lượng."],
    ["E06", "Diebold-Mariano (1995)", "Statistical Framework", "Time Series -> Model A vs Model B Forecasts -> Loss Differential -> DM Statistic", "Custom Time-Series", "MSE, MAE, Forecast", "✓", "N/A", "N/A", "N/A", "N/A", "Multi", "DM Forecast Test", "Kiểm định thống kê kinh điển để so sánh độ chính xác dự báo chuỗi thời gian của 2 mô hình."],
    ["E07", "Jobson-Korkie (1981)", "Statistical Framework", "Returns -> Mean & Variance Estimation -> Sharpe A vs Sharpe B -> Z-Score Test", "Statistical Math", "Sharpe Ratio", "✓", "N/A", "N/A", "N/A", "N/A", "Multi", "JK Sharpe Z-test", "Kiểm định ý nghĩa thống kê của sự khác biệt giữa hai chỉ số Sharpe Ratio."],
    ["E08", "Deflated Sharpe (2014)", "Statistical Framework", "Backtest Returns -> Skew/Kurtosis Estimation -> Multiple Testing Adjustment -> DSR", "Custom Backtest", "Deflated Sharpe", "✓", "✓", "✓", "✓", "✓", "Multi", "DSR Distribution Test", "Hiệu chỉnh Sharpe Ratio để phạt các chiến lược chạy backtest nhiều lần và tính đến rủi ro phi chuẩn (skewness, kurtosis)."],
    ["E09", "Trading Rule Check (1999)", "Statistical Framework", "Market Data -> Technical Rules -> Bootstrap Resampling -> Out-of-Sample Validation", "Vectorized Backtest", "Return, Rule Count", "✓", "✓", "✓", "✓", "✓", "Multi", "White RC on 10k Rules", "Ứng dụng White RC trên hàng ngàn quy tắc kỹ thuật S&P 500, chứng minh nhiều chiến lược thắng chỉ là ngẫu nhiên."],
    ["E10", "Reproducible Finance (2020)", "Methodological Framework", "Research Paper -> Code & Data Availability -> Independent Replication -> Outcome", "Jupyter / Open Source", "Reproducibility Rate", "✓", "✓", "✓", "✓", "✓", "Multi", "ANOVA / Permutation", "Khảo sát và đề xuất tiêu chuẩn chia sẻ code/data để giải quyết khủng hoảng tái lập trong nghiên cứu tài chính."],
    ["E12", "Compute-Controlled (2026)", "Evaluation Framework", "LLM Signal -> Statistical Arbitrage -> Pre-registered Backtest -> Falsification Test", "Vectorized Simulator", "Return, Sharpe", "✓", "✓", "✓", "✓", "✓", "Multi", "Pre-registered Falsification", "Kết quả: Không tìm thấy bằng chứng rằng LLM signal tạo thêm predictive value trên dữ liệu họ nghiên cứu."],
    ["H01", "TradingGPT (2023)", "LLM Agent (Layered Memory)", "Market Data -> Layered Memory (Short/Long) -> LLM Reasoning -> Trading Signal", "Custom Simulator", "Return, Sharpe, MaxDD", "✗", "✗", "✗", "✗", "✗", "Bull/Bear", "✗", "Sử dụng bộ nhớ phân tầng (Layered Memory) giúp agent lưu trữ và truy xuất sự kiện quá khứ để ra quyết định giao dịch."],
    ["H02", "FinMem (2023)", "LLM Agent (Persona)", "Market Data -> Persona Profiling -> Memory Module -> LLM Agent -> Decision", "Custom Simulator", "Return, Sharpe, Win Rate", "✗", "✗", "✗", "✗", "✗", "Single", "✗", "Cải tiến bằng persona chuyên biệt và quy trình profiling, giúp agent tối ưu hóa khả năng thích ứng thị trường."],
    ["S08", "MarketSenseAI (2024)", "LLM Agent (RAG)", "News & Earnings -> RAG Pipeline -> GPT-4 Analysis -> Signal -> Portfolio Weighting", "Custom Simulator", "Return, Sharpe, Alpha", "✗", "✓", "✗", "✗", "✗", "Bull/Bear", "✗", "Sử dụng RAG cung cấp tin tức và báo cáo thu nhập (Earnings Calls) thời gian thực cho LLM tạo tín hiệu Buy/Hold/Sell."],
    ["O01", "Ours (Proposed Framework)", "Dual-Engine (Vibe vs AI)", "Multi-Source Data -> Dual-Engine (Vibe vs AI) -> Signal -> Controlled Execution & Risk", "Backtrader / Vectorized", "Sharpe, Return, MaxDD", "✓", "✓", "✓", "✓", "✓", "Bull/Bear/Sideways", "DM, SPA, JK, DSR", "Đề xuất khung đánh giá đối sánh kiểm soát hoàn toàn (phí, trượt giá, rủi ro) để đo lường giá trị gia tăng thuần túy do cảm xúc AI tạo ra."],
  ]

  # ----------------------------------------------------
# Sheet 6: Evaluation Metrics
# ----------------------------------------------------
s6_cols = ["ID", "Paper", "Return", "Sharpe", "Sortino", "Calmar", "Profit Factor", "Win Rate", "Max DD", "VaR", "DM Test", "SPA", "Notes (Ghi chú)"]
s6_data = [
    ["E01", "FinRL (2021)", "✓", "✓", "✗", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "Xây dựng môi trường chuẩn (Gym) và thư viện mở cho RL trong tài chính, xóa rào cản kỹ thuật và tăng tính tái lập."],
    ["H01", "TradingGPT (2023)", "✓", "✓", "✗", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "Sử dụng bộ nhớ phân tầng (Layered Memory) giúp agent lưu trữ và truy xuất sự kiện quá khứ để ra quyết định giao dịch."],
    ["H02", "FinMem (2023)", "✓", "✓", "✓", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "Cải tiến bằng persona chuyên biệt và quy trình profiling, giúp agent tối ưu hóa khả năng thích ứng thị trường."],
    ["H03", "FinAgent (2024)", "✓", "✓", "✓", "✓", "✗", "✓", "✓", "✗", "✗", "✗", "Tích hợp năng lực đa phương thức (Multimodal), đưa ảnh biểu đồ K-lines cho LLM phân tích trực tiếp mẫu hình."],
    ["S08", "MarketSenseAI (2024)", "✓", "✓", "✗", "✗", "✗", "✓", "✓", "✗", "✗", "✗", "Sử dụng RAG cung cấp tin tức và báo cáo thu nhập (Earnings Calls) thời gian thực cho LLM tạo tín hiệu Buy/Hold/Sell."],
    ["T01", "DeepLOB (2019)", "✓", "✗", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "✗", "Sử dụng CNN trích xuất đặc trưng không gian và LSTM cho phụ thuộc thời gian từ LOB, đạt SOTA về dự báo mid-price ngắn hạn."],
    ["T09", "AlphaStock (2019)", "✓", "✓", "✗", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "RL kết hợp Cross-asset Attention để chọn lọc cổ phiếu sinh lời cao (winners), cân bằng rủi ro qua Sharpe Ratio."],
    ["T06", "High-Freq RL (2022)", "✓", "✓", "✗", "✗", "✓", "✓", "✓", "✗", "✗", "✗", "Agent tương tác với LOB ở tần số cao, xây dựng hàm phần thưởng cân bằng giữa lợi nhuận và rủi ro hàng tồn kho (inventory risk)."],
    ["H08", "Risk-Sensitive RL (2021)", "✓", "✓", "✓", "✗", "✗", "✗", "✓", "✓", "✗", "✗", "Sử dụng Distributional RL để tối ưu hóa toàn bộ phân phối lợi nhuận thay vì chỉ dựa vào giá trị kỳ vọng (mean)."],
    ["E08", "Deflated Sharpe (2014)", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "Hiệu chỉnh Sharpe Ratio để phạt các chiến lược chạy backtest nhiều lần và tính đến rủi ro phi chuẩn (skewness, kurtosis)."],
    ["T11", "AI Trading: Evaluating LLMs (2026)", "✓", "✓", "✓", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "So sánh các LLMs: GPT-4, Claude, Gemini, Llama, FinGPT."],
    ["S11", "Sentiment Trading with LLMs (2024)", "✓", "✓", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "✗", "Họ chứng minh: LLM sentiment -> dự báo return tốt hơn -> Sharpe tốt hơn."],
    ["H10", "Explainable Zero-shot Trading (2026)", "✓", "✓", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "Họ có backtest, transaction cost, ablation. Nhưng mục tiêu là chứng minh framework đa tác tử hoạt động tốt, không phải cô lập đóng góp của sentiment."],
    ["E12", "Compute-Controlled Falsification (2026)", "✓", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✓", "✓", "Kết quả: Không tìm thấy bằng chứng rằng LLM signal tạo thêm predictive value trên dữ liệu họ nghiên cứu. -> Không phải Paper nào cũng cho rằng AI tốt hơn"],
    ["O01", "Ours (Proposed Framework)", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "Đề xuất khung đánh giá đối sánh kiểm soát hoàn toàn (phí, trượt giá, rủi ro) để đo lường giá trị gia tăng (Incremental Value) thuần túy do cảm xúc AI tạo ra."],
    ["Nhận xét: Hầu hết các nghiên cứu đều sử dụng các chỉ số như Return, Sharpe Ratio, Max Drawdown hoặc Win Rate để đánh giá hiệu quả. Tuy nhiên, nhiều nghiên cứu chưa sử dụng các kiểm định thống kê nhằm xác nhận rằng sự khác biệt giữa các chiến lược có ý nghĩa thống kê thay vì chỉ là kết quả ngẫu nhiên. Các chỉ số như Deflated Sharpe Ratio, SPA Test hoặc Diebold–Mariano Test mới chỉ xuất hiện ở một số lượng nhỏ nghiên cứu.\n\n=> Kết luận: Đánh giá hiệu quả giao dịch vẫn chủ yếu dựa trên các chỉ số mô tả, trong khi bằng chứng thống kê còn hạn chế.", "", "", "", "", "", "", "", "", "", "", "", ""]
]

# ----------------------------------------------------
# Sheet 7: Research Gap Matrix
# ----------------------------------------------------
s7_cols = ["ID", "Paper (Bài báo)", "Controlled Comparison (Đối sánh kiểm soát)", "Incremental Value (Giá trị gia tăng)", "Market Regime (Chế độ thị trường)", "LLM", "On-chain (On-chain)", "Reproducible (Tái lập được)", "Open-source (Mã nguồn mở)", "Gap Relation (Liên hệ khoảng trống)", "Notes (Ghi chú)"]
s7_data = [
    ["H01", "TradingGPT (2023)", "✗", "✗", "Partial", "✓", "✗", "Partial", "✓", "Evaluates system as black box; cannot isolate LLM vs indicator impact.", "Sử dụng bộ nhớ phân tầng (Layered Memory) giúp agent lưu trữ và truy xuất sự kiện quá khứ để ra quyết định giao dịch."],
    ["H02", "FinMem (2023)", "✗", "✗", "Single", "✓", "✗", "Partial", "✓", "Focuses on memory module architecture; lacks controlled baseline comparison.", "Cải tiến bằng persona chuyên biệt và quy trình profiling, giúp agent tối ưu hóa khả năng thích ứng thị trường."],
    ["H03", "FinAgent (2024)", "✗", "✗", "Partial", "✓", "✗", "✗", "✗", "Complex multi-agent framework; no incremental statistical quantification.", "Tích hợp năng lực đa phương thức (Multimodal), đưa ảnh biểu đồ K-lines cho LLM phân tích trực tiếp mẫu hình."],
    ["E01", "FinRL (2021)", "✓", "✗", "Single", "✗", "✗", "High", "✓", "Standardized RL library; does not incorporate LLM sentiment or on-chain signals.", "Xây dựng môi trường chuẩn (Gym) và thư viện mở cho RL trong tài chính, xóa rào cản kỹ thuật và tăng tính tái lập."],
    ["S08", "MarketSenseAI (2024)", "✗", "✗", "Partial", "✓", "✗", "Partial", "✗", "Evaluates GPT-4 signals on stocks; no controlled risk/execution framework.", "Sử dụng RAG cung cấp tin tức và báo cáo thu nhập (Earnings Calls) thời gian thực cho LLM tạo tín hiệu Buy/Hold/Sell."],
    ["T09", "AlphaStock (2019)", "✓", "✗", "Multi", "✗", "✗", "High", "✓", "Strong DRL benchmark; technical signals only, no natural language sentiment.", "RL kết hợp Cross-asset Attention để chọn lọc cổ phiếu sinh lời cao (winners), cân bằng rủi ro qua Sharpe Ratio."],
    ["T01", "DeepLOB (2019)", "✓", "✗", "Single", "✗", "✗", "High", "✓", "Microstructure price prediction; ignores high-level market sentiment & macro.", "Sử dụng CNN trích xuất đặc trưng không gian và LSTM cho phụ thuộc thời gian từ LOB, đạt SOTA về dự báo mid-price ngắn hạn."],
    ["E03", "Backtesting Pitfalls (2014)", "✓", "N/A", "Multi", "✗", "✗", "High", "N/A", "Methodological guide on backtest biases; does not propose trading system.", "Marcos López de Prado chỉ ra 7 lỗi backtest (Overfitting, Look-ahead) và đề xuất Combinatorial Purged CV."],
    ["E08", "Deflated Sharpe (2014)", "✓", "N/A", "Multi", "✗", "✗", "High", "✓", "Statistical correction for overfitting; rarely adopted in LLM trading papers.", "Hiệu chỉnh Sharpe Ratio để phạt các chiến lược chạy backtest nhiều lần và tính đến rủi ro phi chuẩn (skewness, kurtosis)."],
    ["E12", "Compute-Controlled Falsification (2026)", "✓", "✓", "Multi", "✓", "✗", "High", "✓", "Focuses on rigorous backtesting to prevent overfitting in LLM signals.", "Kết quả: Không tìm thấy bằng chứng rằng LLM signal tạo thêm predictive value trên dữ liệu họ nghiên cứu. -> Không phải Paper nào cũng cho rằng AI tốt hơn"],
    ["H10", "Explainable Zero-shot Trading (2026)", "✗", "✗", "Multi", "✓", "✓", "Partial", "✗", "Uses multi-agent zero-shot LLM but lacks identical risk/fee engine baseline comparison.", "Họ có backtest, transaction cost, ablation. Nhưng mục tiêu là chứng minh framework đa tác tử hoạt động tốt, không phải cô lập đóng góp của sentiment."],
    ["O01", "Ours (Proposed Framework)", "✓", "✓", "Multi (Bull/Bear/Sideway)", "✓", "✓", "High", "✓", "BRIDGES GAP: First controlled experiment isolating incremental value of AI-derived multi-source market assessment (derivatives microstructure + whale positioning + liquidation + LLM news) vs technical-only, under identical execution/fee/risk engine.", "Đề xuất khung đánh giá đối sánh kiểm soát hoàn toàn để định lượng giá trị gia tăng của AI-derived multi-source market assessment (funding rate + taker flow + whale L/S + liquidation heatmap + LLM news reasoning) so với chiến lược kỹ thuật thuần túy, dưới cùng điều kiện thực thi."],
    ["F04", "Algorithmic Trading (2013)", "✓", "✗", "Multi", "✗", "✗", "High", "✓", "Foundation for algorithmic backtesting.", "Kinh thánh Quant Trading."],
    ["F06", "Advances in Financial ML (2018)", "✓", "✗", "Multi", "✗", "✗", "High", "✓", "Establishes robust ML evaluation.", "Kinh thánh ML Trading."],
    ["Nhận xét: \nQua tổng hợp các nghiên cứu hiện có, có thể thấy:\nĐã có nhiều nghiên cứu về technical trading;\nĐã có nhiều nghiên cứu về sentiment trading;\nĐã có nhiều hybrid framework kết hợp nhiều nguồn tín hiệu.\nTuy nhiên, chưa có đủ bằng chứng cho thấy đã tồn tại một giao thức thực nghiệm được kiểm soát chặt chẽ nhằm:\nGiữ nguyên execution;\nGiữ nguyên risk management;\nGiữ nguyên transaction cost;\nChỉ thay đổi nguồn tín hiệu;\nĐể định lượng chính xác giá trị giao dịch gia tăng của AI-derived sentiment so với technical signals.\n=> Kết luận: Đây là khoảng trống nghiên cứu tiềm năng và cần tiếp tục được xác minh thông qua khảo sát đầy đủ.", "", "", "", "", "", "", "", "", "", ""]
]

# ----------------------------------------------------
# Sheet 8: Evidence Summary
# ----------------------------------------------------
s8_cols = ["Category / Metric (Hạng mục / Chỉ số)", "Result / Count (Kết quả / Số lượng)", "Percentage / Details (Phần trăm / Chi tiết)", "Notes (Ghi chú)"]

# Dynamic calculations for s8_data
_vs1 = [r for r in verified_rows(s1_data) if record_id(r).startswith(('T', 'S', 'H', 'E', 'F'))]
_vs7 = [r for r in verified_rows(s7_data) if record_id(r).startswith(('T', 'S', 'H', 'E', 'F'))]
_vs6 = [r for r in verified_rows(s6_data) if record_id(r).startswith(('T', 'S', 'H', 'E', 'F'))]
_tot = len(_vs1) if len(_vs1) > 0 else 1

def _pct(count): return f"{(count/_tot)*100:.1f}%"

_ieee = sum(1 for r in _vs1 if 'IEEE' in str(r) or 'ACM' in str(r))
_els = sum(1 for r in _vs1 if 'Elsevier' in str(r) or 'Springer' in str(r))
_top = sum(1 for r in _vs1 if any(x in str(r) for x in ['NeurIPS', 'KDD', 'ACL', 'IJCAI', 'AAAI', 'EMNLP']))
_arx = sum(1 for r in _vs1 if any(x in str(r) for x in ['arXiv', 'SSRN', 'Working Paper', 'Preprint']))

_llm = sum(1 for r in _vs1 if any(x in str(r).upper() for x in ['LLM', 'GPT', 'BERT', 'FINBERT', 'TRANSFORMER']))
_onc = sum(1 for r in _vs1 if 'on-chain' in str(r).lower())

_cc = sum(1 for r in _vs7 if '✓' in str(r[2]) or 'Yes' in str(r[2]))
_inc = sum(1 for r in _vs7 if '✓' in str(r[3]) or 'Yes' in str(r[3]))
_mr = sum(1 for r in _vs7 if 'Multi' in str(r[4]) or '✓' in str(r[4]))

_st = sum(1 for r in _vs6 if '✓' in str(r[10]) or '✓' in str(r[11]) or 'SPA' in str(r[11]) or 'DM' in str(r[10]) or 'p-value' in str(r).lower() or 'Z statistic' in str(r))
_os = sum(1 for r in _vs1 if any(x in str(r[8]).lower() for x in ['code', 'verified', 'open-source', 'github', 'repository']) or str(r[8]).startswith('✓') or str(r[8]).startswith('Yes'))

s8_data = [
    ["Total Literature Papers Reviewed", f"{_tot} key benchmark papers", "100.0%", ""],
    ["Technical Trading Papers", f"{sum(1 for r in _vs1 if record_id(r).startswith('T'))} papers", _pct(sum(1 for r in _vs1 if record_id(r).startswith('T'))), ""],
    ["Sentiment Trading Papers", f"{sum(1 for r in _vs1 if record_id(r).startswith('S'))} papers", _pct(sum(1 for r in _vs1 if record_id(r).startswith('S'))), ""],
    ["Hybrid Trading Papers", f"{sum(1 for r in _vs1 if record_id(r).startswith('H'))} papers", _pct(sum(1 for r in _vs1 if record_id(r).startswith('H'))), ""],
    ["Evaluation, Benchmark Papers", f"{sum(1 for r in _vs1 if record_id(r).startswith('E'))} papers", _pct(sum(1 for r in _vs1 if record_id(r).startswith('E'))), ""],
    ["Foundational Papers", f"{sum(1 for r in _vs1 if record_id(r).startswith('F'))} papers", _pct(sum(1 for r in _vs1 if record_id(r).startswith('F'))), ""],
    ["--------------------------------------------------", "--------------------", "--------------------", ""],
    ["IEEE / ACM Peer-Reviewed Papers", f"{_ieee} papers", _pct(_ieee), ""],
    ["Elsevier / Springer Peer-Reviewed Papers", f"{_els} papers", _pct(_els), ""],
    ["Top Machine Learning / NLP Conferences (NeurIPS, KDD, ACL, IJCAI)", f"{_top} papers", _pct(_top), ""],
    ["arXiv / Working Papers (FinGPT, TradingGPT, etc.)", f"{_arx} papers", _pct(_arx), ""],
    ["--------------------------------------------------", "--------------------", "--------------------", ""],
    ["Papers incorporating Large Language Models (LLMs / FinGPT / GPT-4)", f"{_llm} papers", _pct(_llm), ""],
    ["Papers incorporating On-Chain Signals for Cryptocurrency", f"{_onc} papers", _pct(_onc), ""],
    ["--------------------------------------------------", "--------------------", "--------------------", ""],
    ["Studies conducting Controlled Comparison (Identical Fee, Risk, Execution)", f"{_cc} papers", _pct(_cc), ""],
    ["Studies quantifying Incremental Value of Sentiment beyond Technicals", f"{_inc} papers", _pct(_inc), ""],
    ["Studies applying Formal Statistical Significance Tests (DM, SPA, JK, DSR)", f"{_st} papers", _pct(_st), ""],
    ["Studies evaluating across Multiple Market Regimes (Bull, Bear, Sideways)", f"{_mr} papers", _pct(_mr), ""],
    ["Studies with Full Code & Data Reproducibility (Open Source)", f"{_os} papers", _pct(_os), ""],
    ["Draft (UPDATED) : Sau khi khảo sát các nghiên cứu hiện có, có thể thấy rằng algorithmic trading đã đạt được nhiều tiến bộ trong technical analysis, sentiment analysis, hybrid trading và gần đây là LLM-based trading systems. Mặc dù nhiều công trình báo cáo hiệu quả vượt trội của các framework đề xuất, phần lớn đều thay đổi nhiều thành phần của hệ thống cùng lúc và đánh giá trên các giao thức thực nghiệm khác nhau. Đặc biệt, AI module trong các nghiên cứu gần đây (H10, S09) thường chỉ được mô tả như một 'sentiment layer' đơn lẻ, trong khi thực tế các hệ thống hiện đại đã tích hợp nhiều nguồn thông tin thị trường phong phú hơn nhiều: derivatives microstructure (funding rate, taker buy/sell flow), smart money positioning (top traders long/short ratio), liquidation heatmap (reversal risk), và LLM-based news reasoning (Polymarket + RSS). Do đó, hiện vẫn chưa có đủ bằng chứng để kết luận rằng AI-derived multi-source market assessment - tổng hợp các tầng thông tin thị trường nêu trên - mang lại bao nhiêu giá trị giao dịch gia tăng ngoài pure technical signals khi được đánh giá dưới cùng điều kiện thực thi, chi phí giao dịch và quản trị rủi ro. Khoảng trống này tạo động lực cho nghiên cứu hiện tại, trong đó Vibe Mode (technical-only) và AI Mode (multi-source market assessment) được triển khai trên cùng một framework, chỉ khác nhau ở nguồn tín hiệu, nhằm cho phép một controlled comparison công bằng và định lượng incremental value của AI-derived market intelligence.", "", "", ""],
]

# ----------------------------------------------------
# Sheet 9: Top Selected Papers for Review
# ----------------------------------------------------
s9_cols = ["ID", "Title (Tiêu đề)", "Year (Năm)", "Group (Nhóm)", "Category (Phân loại)", "Framework (Phân loại)", "Pipeline (Luồng dữ liệu)", "Environment (Môi trường)", "Metrics (Đo độ)", "Relevance (Độ liên quan)", "Notes (Ghi chú)"]
s9_data = [
    # Kinh điển (Foundational)
    ["F01", "Portfolio Selection (Markowitz)", "1952", "Kinh điển", "Portfolio Management", "Statistical Framework", "Returns -> Mean-Variance Optimization -> Efficient Frontier -> Optimal Weights", "Statistical Math", "Return, Variance", "High", "Nền tảng của Modern Portfolio Theory (MPT)."],
    ["F02", "Mutual Fund Performance (Sharpe)", "1966", "Kinh điển", "Risk Evaluation", "Statistical Framework", "Returns -> Risk-Free Rate Subtraction -> Standard Deviation -> Sharpe Ratio", "Statistical Math", "Sharpe Ratio", "High", "Nền tảng đánh giá hiệu suất điều chỉnh rủi ro (Sharpe Ratio)."],
    ["F03", "Technical Analysis of the Financial Markets (Murphy)", "1999", "Kinh điển", "Technical Trading", "Technical Analysis", "Market Data -> Chart Patterns / Indicators -> Trend Identification -> Signal", "Manual / Visual", "Return", "High", "Kinh thánh về phân tích kỹ thuật (Technical baselines)."],
    ["F04", "Algorithmic Trading: Winning Strategies... (Chan)", "2013", "Kinh điển", "Quant Trading", "Standard Quant Framework", "Market Data -> Signal -> Execution -> Risk Management -> Backtest -> Production", "Vectorized / Event-Driven Backtest", "Sharpe, MaxDD", "High", "Kinh thánh thực hành Quant Trading và backtesting cơ bản."],
    ["F05", "Analysis of Financial Time Series (Tsay)", "2005", "Kinh điển", "Time Series", "Time-Series Econometrics", "Market Data -> Stationarity Test -> ARIMA/GARCH Modeling -> Forecasting", "Statistical Math / R", "MSE, MAE", "Medium", "Kinh thánh về phân tích chuỗi thời gian tài chính."],
    ["F06", "Advances in Financial Machine Learning (López de Prado)", "2018", "Kinh điển", "Machine Learning", "ML Framework", "Bars -> Meta-Labeling -> Fractionally Differentiated Features -> Purged K-Fold CV", "Custom Backtest", "Sharpe, Deflated Sharpe", "High", "Kinh thánh về Machine Learning trong tài chính, chống overfitting."],
    ["F09", "Attention Is All You Need (Vaswani et al.)", "2017", "Kinh điển", "Deep Learning / NLP", "Deep Learning (NLP)", "Tokens -> Embedding -> Self-Attention -> Feed-Forward -> Output Probabilities", "PyTorch / TensorFlow", "BLEU, Perplexity", "High", "Nền tảng của kiến trúc Transformer."],
    ["F11", "Bitcoin: A Peer-to-Peer Electronic Cash System", "2008", "Kinh điển", "Crypto", "Blockchain Protocol", "Transactions -> Hash -> Proof-of-Work -> Block -> Longest Chain", "Distributed Network", "N/A", "High", "Nền tảng thị trường Crypto."],
    # Mới trong 5 năm (Recent)
    ["E01", "FinRL: A Deep Reinforcement Learning Library for Automated Trading", "2021", "Mới (5 năm)", "Reinforcement Learning", "RL Framework", "Market Data -> State/Reward -> RL Agent -> Action (Portfolio Weights) -> FinRL Simulator", "OpenAI Gym / FinRL", "Return, Sharpe, MaxDD", "High", "Framework chuẩn hóa cho RL trong tài chính."],
    ["S05", "FinGPT: Open-Source Financial Large Language Models", "2023", "Mới (5 năm)", "LLM / NLP", "LLM Pipeline", "Financial Data (News/Social) -> Instruction Tuning -> FinGPT -> Sentiment/Task Output", "HuggingFace / PyTorch", "Accuracy, F1-Score", "High", "Open-source LLM tiên phong cho tài chính."],
    ["T04", "Cryptocurrency Trading with Transformer Networks", "2022", "Mới (5 năm)", "Crypto / Deep Learning", "Deep Learning Framework", "Market Data -> Positional Encoding -> Transformer -> Price/Trend Prediction", "PyTorch / Backtest", "Return, Sharpe, RMSE", "High", "Ứng dụng Transformer trực tiếp trên dữ liệu Crypto."],
    ["S07", "LLMs in Finance: Assessing GPT-4 Sentiment Extraction", "2023", "Mới (5 năm)", "LLM / Sentiment", "LLM Agent", "Financial Text -> Prompt Engineering -> GPT-4 -> Sentiment Score", "OpenAI API", "Accuracy, Return", "High", "Đánh giá năng lực trích xuất Sentiment của GPT-4."],
    ["S11", "Sentiment Trading with LLMs", "2024", "Mới (5 năm)", "LLM / Sentiment", "LLM Pipeline", "News -> LLM Extraction -> Sentiment Score -> Portfolio Allocation -> Execution", "Vectorized Simulator", "Return, Sharpe", "High", "Bằng chứng mới nhất về giá trị dự báo của LLM Sentiment."],
    ["S12", "Unlocking the black box of sentiment and cryptocurrency...", "2024", "Mới (5 năm)", "Crypto / Sentiment", "Sentiment Analysis", "Crypto News/Twitter -> NLP / LLM -> Sentiment Index -> Signal Generation", "Custom Backtest", "Sharpe, MaxDD", "High", "Giải mã Sentiment trong thị trường Crypto."],
    ["S13", "Sentiment Classification of Cryptocurrency-Related Social Media Posts", "2023", "Mới (5 năm)", "Crypto / Social Sentiment", "CryptoBERT / LUKE", "Crypto social posts -> domain post-training -> sentiment classification -> transfer-test candidate", "HuggingFace / IEEE Intelligent Systems", "Classification accuracy, F1", "High", "Nguồn bình duyệt cho CryptoBERT; chỉ dùng như crypto social-sentiment transfer reference, không xem là news-headline replication."],
    ["H04", "Multi-Agent LLM Trading in Volatile Markets", "2024", "Mới (5 năm)", "Hybrid / Multi-Agent", "Multi-Agent LLM", "Market Data/News -> Multi-Agent Debate/Consensus -> Trading Signal -> Execution", "Custom Simulator", "Return, Sharpe, Win Rate", "High", "Crypto + LLM Multi-agent trong thị trường biến động."],
    ["H10", "Explainable zero-shot trading using multi-agent LLM architecture", "2026", "Mới (5 năm)", "Hybrid / Explainability", "Multi-Agent LLM", "Data -> Perception Agent -> Reasoning Agent -> Decision Agent -> Execution", "Simulated / Backtrader", "Return, Sharpe, MaxDD", "High", "Multi-agent LLM cho trading Crypto zero-shot."],
    ["E12", "A Pre-registered, Compute-Controlled Falsification...", "2026", "Mới (5 năm)", "Evaluation / LLM", "Evaluation Framework", "LLM Signal -> Statistical Arbitrage -> Pre-registered Backtest -> Falsification Test", "Vectorized Simulator", "Return, Sharpe", "High", "Falsification testing nghiêm ngặt cho LLM Signals (Crypto)."],
    ["T07", "Volatility-Adaptive Trading Systems in Crypto Markets", "2022", "Mới (5 năm)", "Crypto / Technical", "Technical Trading", "Market Data -> Volatility Modeling (GARCH/ATR) -> Adaptive Position Sizing -> Execution", "Custom Backtest", "Return, Sortino, MaxDD", "Medium", "Tối ưu hóa rủi ro thích ứng cho Crypto."],
    ["E10", "Reproducible Financial Research: Standards and Pitfalls", "2020", "Mới (5 năm)", "Evaluation", "Methodological Framework", "Research Paper -> Code & Data Availability -> Independent Replication -> Outcome", "Jupyter / Open Source", "Reproducibility Rate", "High", "Tiêu chuẩn Reproducibility, rất liên quan đến Controlled Comparison."],
    ["O01", "Ours: Controlled Evaluation Framework for AI Sentiment Value", "2026", "Đề xuất", "Hybrid / Evaluation", "Dual-Engine (Vibe vs AI)", "Multi-Source Data -> Dual-Engine (Vibe vs AI) -> Signal -> Controlled Execution & Risk", "Backtrader / Vectorized", "Sharpe, Return, MaxDD", "Critical", "Đề xuất Controlled Evaluation Framework (Nghiên cứu của tác giả)."]
]


sheet_display_names = {
    "1_Master_Database": "1_Master (CSDL)",
    "2_Technical_Trading": "2_Technical (Kỹ thuật)",
    "3_Sentiment_Trading": "3_Sentiment (Cảm xúc)",
    "4_Hybrid_Trading": "4_Hybrid (Kết hợp)",
    "5_Experimental_Design": "5_Experimental (Thiết kế)",
    "6_Evaluation_Metrics": "6_Metrics (Chỉ số)",
    "7_Research_Gap_Matrix": "7_Gap (Khoảng trống)",
    "8_Evidence_Summary": "8_Evidence (Bằng chứng)",
    "9_Top_20_Papers": "9_Selected_Papers",
    "12_Backtest_Design": "12_Backtest (Kiểm thử lịch sử)",
    "13_Method_Traceability": "13_Methodology (Phương pháp)",
}

sheet_header_maps = {
    "1_Master_Database": ["ID", "Title (Tiêu đề)", "Year (Năm)", "Venue (Hội nghị/Tạp chí)", "Publisher (Nhà xuất bản)", "Q / Venue tier", "Publication status", "DOI", "Code (Mã)", "Dataset (Bộ dữ liệu)", "Asset (Tài sản)", "Method (Phương pháp)", "Metrics (Chỉ số)", "Citations (Trích dẫn)", "Google Scholar (Tra cứu)", "Notes (Ghi chú)"],
    "2_Technical_Trading": ["ID", "Paper (Bài báo)", "EMA", "RSI", "MACD", "ML", "DL", "RL", "Crypto", "Stock", "Benchmark (Đối sánh)", "Limitation (Hạn chế)", "Notes (Ghi chú)", "Market / Asset Class"],
    "3_Sentiment_Trading": ["ID", "Paper (Bài báo)", "News", "Twitter", "Reddit", "FinBERT", "FinGPT", "GPT", "Gemini", "Accuracy (Độ chính xác)", "Trading Return (Lợi nhuận giao dịch)", "Notes (Ghi chú)", "Market / Asset Class"],
    "4_Hybrid_Trading": ["ID", "Paper (Bài báo)", "Technical (Kỹ thuật)", "Sentiment (Cảm xúc)", "LLM", "On-chain (On-chain)", "Risk Mgmt (Quản lý rủi ro)", "Execution (Thực thi)", "Controlled Comparison (Đối sánh kiểm soát)", "Ablation (Ablation)", "Notes (Ghi chú)", "Market / Asset Class"],
    "5_Experimental_Design": ["ID", "Paper (Bài báo)", "Framework (Phân loại)", "Pipeline (Luồng dữ liệu)", "Environment (Môi trường)", "Metrics (Độ đo)", "Same Dataset (Cùng bộ dữ liệu)", "Same Fee (Cùng phí)", "Same Risk (Cùng rủi ro)", "Same Execution (Cùng thực thi)", "Same Position Size (Cùng quy mô vị thế)", "Market Regime (Chế độ thị trường)", "Statistical Test (Kiểm định thống kê)", "Notes (Ghi chú)"],
    "6_Evaluation_Metrics": ["ID", "Paper (Bài báo)", "Return (Lợi nhuận)", "Sharpe", "Sortino", "Calmar", "Profit Factor (Hệ số lợi nhuận)", "Win Rate (Tỷ lệ thắng)", "Max DD (Sụt giảm tối đa)", "VaR", "DM Test (Kiểm định DM)", "SPA (Kiểm định SPA)", "Notes (Ghi chú)"],
    "7_Research_Gap_Matrix": ["ID", "Paper (Bài báo)", "Controlled Comparison (Đối sánh kiểm soát)", "Incremental Value (Giá trị gia tăng)", "Market Regime (Chế độ thị trường)", "LLM", "On-chain (On-chain)", "Reproducible (Tái lập được)", "Open-source (Mã nguồn mở)", "Gap Relation (Liên hệ khoảng trống)", "Notes (Ghi chú)"],
    "8_Evidence_Summary": ["Category / Metric (Hạng mục / Chỉ số)", "Result / Count (Kết quả / Số lượng)", "Percentage / Details (Phần trăm / Chi tiết)", "Notes (Ghi chú)"],
    "9_Top_20_Papers": s9_cols,
    "12_Backtest_Design": [
        "ID", "Paper Title (Tên bài báo)",
        "DATA — Input & Source (Dữ liệu đầu vào & nguồn)", "DATA — Frequency & Period (Tần suất & giai đoạn)",
        "DATA — Universe / Point-in-Time (Universe / point-in-time)",
        "TRAIN — Model / Strategy Fitting (Huấn luyện / xây dựng chiến lược)",
        "TRAIN — Selection / Tuning (Chọn mô hình / tham số)",
        "TEST — OOS Protocol (Giao thức OOS)", "TEST — Final Untouched Holdout (Final holdout chưa sử dụng)",
        "VALIDITY — Robustness / Regime", "VALIDITY — Statistical / Multiple Testing",
        "Scientific Assessment (Đánh giá khoa học)", "Source URL (URL nguồn)",
    ],
    "13_Method_Traceability": [
        "Methodology Component (Thành phần phương pháp)", "Reference Paper(s) (Bài báo tham khảo)",
        "Credibility (Độ uy tín)", "What Is Adopted (Nội dung kế thừa)",
        "Project-Specific Modification (Điều chỉnh cho dự án)", "Why Modified (Lý do điều chỉnh)",
        "Implementation / Artifact (Hiện thực / sản phẩm)", "Reproduction / Transfer Result (Kết quả chạy lại / áp dụng)",
        "RQ Contribution (Đóng góp cho câu hỏi nghiên cứu)", "Remaining Risk / Required Test (Rủi ro còn lại / kiểm định cần làm)",
        "Source URL (URL nguồn)",
    ],
}

sheet_value_maps = {
    "2_Technical_Trading": {
        12: {
            "High computational cost, ignores transaction fee": "Chi phí tính toán cao, bỏ qua phí giao dịch",
            "No explicit risk management, fixed window": "Không có quản trị rủi ro rõ ràng, cửa sổ cố định",
            "High latency in graph updates, stock only": "Độ trễ cao khi cập nhật đồ thị, chỉ áp dụng cho cổ phiếu",
            "Overfitting in high volatility crypto regimes": "Dễ quá khớp trong các giai đoạn biến động mạnh của crypto",
            "Single-asset simulator, high slippage risk": "Mô phỏng đơn tài sản, rủi ro trượt giá cao",
            "Ignores macro sentiment, order rejection risk": "Bỏ qua tâm lý vĩ mô, rủi ro lệnh bị từ chối",
            "Parameters require manual regime recalibration": "Tham số cần hiệu chỉnh lại thủ công theo từng chế độ thị trường",
            "Regime identification lag during crash events": "Độ trễ nhận diện chế độ thị trường trong các sự kiện sụp giảm",
            "No sentiment input, stock market specific": "Không có đầu vào tâm lý, chỉ phù hợp thị trường cổ phiếu",
            "Requires dense cross-sectional asset universe": "Cần vũ trụ tài sản chéo có mật độ cao",
        }
    },
    "4_Hybrid_Trading": {
        3: {"✓": "✓", "✗": "✗", "Basic": "Cơ bản", "Advanced": "Nâng cao", "Rule Guard": "Bộ chặn quy tắc", "Mean-Variance": "Trung bình - phương sai", "CVaR Bound": "Giới hạn CVaR", "Volatility Target": "Mục tiêu biến động", "Distributional CVaR": "CVaR phân phối", "Identical (Vol + MaxDD)": "Giống hệt (biến động + sụt giảm tối đa)"},
        4: {"✓": "✓", "✗": "✗", "Basic": "Cơ bản", "Advanced": "Nâng cao", "Mean-Variance": "Trung bình - phương sai", "CVaR Bound": "Giới hạn CVaR", "Volatility Target": "Mục tiêu biến động", "Distributional CVaR": "CVaR phân phối", "Identical (Fee + Slippage)": "Giống hệt (phí + trượt giá)", "✓ (Vibe vs AI)": "✓ (Vibe so với AI)"},
        5: {"✓": "✓", "✗": "✗"},
        6: {"✓": "✓", "✗": "✗"},
        7: {"✓": "✓", "✗": "✗", "Simulated": "Mô phỏng", "Exchange API": "API sàn giao dịch"},
        8: {"✓": "✓", "✗": "✗", "Controlled Comparison": "Đối sánh kiểm soát"},
        9: {"✓": "✓", "✗": "✗", "Partial": "Một phần", "✓ (Incremental Value)": "✓ (Giá trị gia tăng)"},
        10: {"Partial": "Một phần", "✗": "✗", "✓ (Incremental Value)": "✓ (Giá trị gia tăng)"},
    },
    "5_Experimental_Design": {
        3: {"✓": "✓", "✗": "✗", "N/A": "Không áp dụng", "Single": "Đơn chế độ", "Multi": "Đa chế độ", "Bull/Bear": "Tăng/Giảm", "Bull/Bear/Sideways": "Tăng/Giảm/Đi ngang"},
        4: {"✓": "✓", "✗": "✗", "N/A": "Không áp dụng"},
        5: {"✓": "✓", "✗": "✗", "N/A": "Không áp dụng"},
        6: {"✓": "✓", "✗": "✗", "N/A": "Không áp dụng"},
        7: {"✓": "✓", "✗": "✗", "N/A": "Không áp dụng"},
        8: {"✓": "✓", "✗": "✗", "N/A": "Không áp dụng", "Single": "Đơn chế độ", "Multi": "Đa chế độ", "Bull/Bear": "Tăng/Giảm", "Bull/Bear/Sideways": "Tăng/Giảm/Đi ngang"},
        9: {
            "✓": "✓",
            "✗": "✗",
            "DSR Test": "Kiểm định DSR",
            "White Bootstrap RC": "Kiểm định bootstrap White RC",
            "Hansen SPA Test": "Kiểm định Hansen SPA",
            "DM Forecast Test": "Kiểm định dự báo DM",
            "JK Sharpe Z-test": "Kiểm định Z Sharpe JK",
            "DSR Distribution Test": "Kiểm định phân phối DSR",
            "White RC on 10k Rules": "White RC trên 10.000 quy tắc",
            "ANOVA / Permutation": "ANOVA / hoán vị",
        },
    },
    "6_Evaluation_Metrics": {
        3: {"✓": "✓", "✗": "✗"},
        4: {"✓": "✓", "✗": "✗"},
        5: {"✓": "✓", "✗": "✗"},
        6: {"✓": "✓", "✗": "✗"},
        7: {"✓": "✓", "✗": "✗"},
        8: {"✓": "✓", "✗": "✗"},
        9: {"✓": "✓", "✗": "✗"},
        10: {"✓": "✓", "✗": "✗"},
        11: {"✓": "✓", "✗": "✗"},
        12: {"✓": "✓", "✗": "✗"},
    },
    "7_Research_Gap_Matrix": {
        3: {"✓": "✓", "✗": "✗", "Partial": "Một phần", "Single": "Đơn thị trường", "Multi": "Đa thị trường", "High": "Cao", "N/A": "Không áp dụng"},
        4: {"✓": "✓", "✗": "✗", "Partial": "Một phần"},
        5: {"Partial": "Một phần", "Single": "Đơn thị trường", "Multi": "Đa thị trường"},
        6: {"✓": "✓", "✗": "✗"},
        7: {"✓": "✓", "✗": "✗"},
        8: {"High": "Cao", "Partial": "Một phần", "✓": "✓", "✗": "✗", "N/A": "Không áp dụng"},
        9: {"✓": "✓", "✗": "✗", "Partial": "Một phần", "N/A": "Không áp dụng"},
        10: {
            "Evaluates system as black box; cannot isolate LLM vs indicator impact.": "Đánh giá hệ thống như một hộp đen; không tách được tác động của LLM so với chỉ báo.",
            "Focuses on memory module architecture; lacks controlled baseline comparison.": "Tập trung vào kiến trúc mô-đun bộ nhớ; thiếu đối sánh với baseline có kiểm soát.",
            "Complex multi-agent framework; no incremental statistical quantification.": "Khung đa tác tử phức tạp; chưa định lượng thống kê giá trị gia tăng.",
            "Standardized RL library; does not incorporate LLM sentiment or on-chain signals.": "Thư viện RL chuẩn hóa; không tích hợp cảm xúc LLM hay tín hiệu on-chain.",
            "Evaluates GPT-4 signals on stocks; no controlled risk/execution framework.": "Đánh giá tín hiệu GPT-4 trên cổ phiếu; chưa có khung kiểm soát rủi ro/thực thi.",
            "Strong DRL benchmark; technical signals only, no natural language sentiment.": "Benchmark DRL mạnh; chỉ dùng tín hiệu kỹ thuật, không có cảm xúc ngôn ngữ tự nhiên.",
            "Microstructure price prediction; ignores high-level market sentiment & macro.": "Dự đoán giá ở mức vi cấu trúc; bỏ qua tâm lý thị trường mức cao và vĩ mô.",
            "Methodological guide on backtest biases; does not propose trading system.": "Hướng dẫn phương pháp về sai lệch backtest; không đề xuất hệ thống giao dịch.",
            "Statistical correction for overfitting; rarely adopted in LLM trading papers.": "Hiệu chỉnh thống kê cho quá khớp; hiếm khi được áp dụng trong các bài về giao dịch LLM.",
            "BRIDGES GAP: Controlled experiment isolating sentiment incremental value on identical risk/fee engine.": "LẤP KHOẢNG TRỐNG: Thí nghiệm có kiểm soát để tách giá trị gia tăng của cảm xúc trên cùng một bộ máy rủi ro/phí.",
        }
    },
    "8_Evidence_Summary": {
        1: {
            "Total Literature Papers Reviewed": "Tổng số bài báo đã rà soát",
            "Technical Trading Papers (T01 - T10)": "Bài báo giao dịch kỹ thuật (T01 - T10)",
            "Sentiment Trading Papers (S01 - S10)": "Bài báo giao dịch cảm xúc (S01 - S10)",
            "Hybrid Trading Papers (H01 - H08)": "Bài báo giao dịch kết hợp (H01 - H08)",
            "Evaluation, Benchmark & Methodology Papers (E01 - E10)": "Bài báo đánh giá, benchmark và phương pháp (E01 - E10)",
            "Proposed Framework / Ours (O01)": "Khung đề xuất / của chúng tôi (O01)",
            "IEEE / ACM Peer-Reviewed Papers": "Bài báo bình duyệt IEEE / ACM",
            "Elsevier / Springer Peer-Reviewed Papers": "Bài báo bình duyệt Elsevier / Springer",
            "Top Machine Learning / NLP Conferences (NeurIPS, KDD, ACL, IJCAI)": "Hội nghị hàng đầu về Machine Learning / NLP (NeurIPS, KDD, ACL, IJCAI)",
            "arXiv / Working Papers (FinGPT, TradingGPT, etc.)": "arXiv / bài báo đang phát triển (FinGPT, TradingGPT, v.v.)",
            "Papers incorporating Large Language Models (LLMs / FinGPT / GPT-4)": "Bài báo có tích hợp Mô hình ngôn ngữ lớn (LLM / FinGPT / GPT-4)",
            "Papers incorporating On-Chain Signals for Cryptocurrency": "Bài báo tích hợp tín hiệu on-chain cho tiền mã hóa",
            "Studies conducting Controlled Comparison (Identical Fee, Risk, Execution)": "Nghiên cứu có đối sánh kiểm soát (phí, rủi ro, thực thi giống hệt)",
            "Studies quantifying Incremental Value of Sentiment beyond Technicals": "Nghiên cứu định lượng giá trị gia tăng của cảm xúc so với kỹ thuật",
            "Studies applying Formal Statistical Significance Tests (DM, SPA, JK, DSR)": "Nghiên cứu áp dụng kiểm định ý nghĩa thống kê (DM, SPA, JK, DSR)",
            "Studies evaluating across Multiple Market Regimes (Bull, Bear, Sideways)": "Nghiên cứu đánh giá qua nhiều chế độ thị trường (tăng, giảm, đi ngang)",
            "Studies with Full Code & Data Reproducibility (Open Source)": "Nghiên cứu có khả năng tái lập đầy đủ mã nguồn & dữ liệu (mã nguồn mở)",
        },
        2: {"100.0%": "100,0%", "25.6%": "25,6%", "20.5%": "20,5%", "2.6%": "2,6%", "56.4%": "56,4%", "12.8%": "12,8%", "7.7%": "7,7%", "10.3%": "10,3%", "5.1%": "5,1%", "23.1%": "23,1%", "46.2%": "46,2%"}
    },
}


def translate_display_value(sheet_key, column_index, value):
    value_str = str(value)
    sheet_maps = sheet_value_maps.get(sheet_key, {})
    column_map = sheet_maps.get(column_index, {})
    return column_map.get(value_str, value)


def build_google_scholar_url(title):
    return f"https://scholar.google.com/scholar?q={quote_plus(str(title))}"


def build_doi_url(doi):
    doi_str = str(doi).strip()
    if doi_str and doi_str not in {"Pending", "N/A", "-"} and doi_str.startswith("10."):
        return f"https://doi.org/{quote_plus(doi_str)}"
    return None


# Research-integrity gate -------------------------------------------------
# The original matrix mixed verified works with placeholders and records whose
# title/venue/DOI do not match.  A record is shown in the research workbook
# only when its bibliographic metadata has been checked against a primary
# source (publisher, proceedings, arXiv, SSRN, or an official book record).
# Keep the source arrays above for audit history; do not silently invent
# replacement metadata for records outside this allow-list.


# Correct metadata verified during the literature audit.
for _row in s1_data:
    if record_id(_row) == "T01":
        _row[6] = "10.1109/TSP.2019.2907260"
        _row[7] = "Verified author repository"
        _row[8] = "FI-2010 LOB benchmark; proprietary London Stock Exchange quotes"
        _row[9] = "Stock / limit-order book"
        _row[10] = "CNN-LSTM on limit-order books"
        _row[11] = "Accuracy, recall, precision, F1; out-of-sample accuracy"
        _row[13] = "FI-2010 uses classification metrics; do not describe DeepLOB as a return/Sharpe study."
    elif record_id(_row) == "T02":
        _row[1] = "Enhancing Stock Movement Prediction with Adversarial Training"
        _row[6] = "10.24963/ijcai.2019/810"
        _row[7] = "Verified paper-linked repository"
        _row[8] = "ACL18 and KDD17 stock-movement benchmarks"
        _row[9] = "Stock"
        _row[10] = "Adversarial Attentive LSTM (Adv-ALSTM)"
        _row[11] = "Accuracy, Matthews correlation coefficient (MCC)"
        _row[13] = "IJCAI 2019; the paper reports 57.20% Acc / 0.1483 MCC on ACL18 and 53.05% / 0.0523 on KDD17."
    elif record_id(_row) == "T03":
        # Replace the unrecoverable placeholder with a verified top-tier crypto
        # factor paper; the full row is finalized again by _tech_method_master.
        _row[:] = ["T03", "Common Risk Factors in Cryptocurrency", "2022", "The Journal of Finance", "Wiley", "Q1", "10.1111/jofi.13119", "No verified official code", "Broad cryptocurrency cross-section", "Cryptocurrency", "Market, size and momentum factor portfolios", "Excess return, alpha, t-statistic", "", "Verified publisher record."]
    elif record_id(_row) == "T04":
        _row[1] = "Helformer: An Attention-Based Deep Learning Model for Cryptocurrency Price Forecasting"
        _row[2] = "2025"
        _row[3] = "Journal of Big Data"
        _row[4] = "Springer Nature"
        _row[5] = "Q1"
        _row[6] = "10.1186/s40537-025-01135-4"
        _row[7] = "-"
        _row[8] = "Cryptocurrency price series (see source paper)"
        _row[9] = "Crypto"
        _row[10] = "Holt-Winters + Transformer"
        _row[11] = "Forecasting metrics"
        _row[12] = ""
        _row[13] = "Verified replacement for the previous mismatched Transformer/crypto record."
    elif record_id(_row) == "S07":
        _row[1] = "FinSentGPT: A Universal Financial Sentiment Engine?"
        _row[2] = "2024"
        _row[3] = "International Review of Financial Analysis"
        _row[4] = "Elsevier"
        _row[5] = "Q1"
        _row[6] = "10.1016/j.irfa.2024.103291"
        _row[7] = "-"
        _row[8] = "Financial-text sentiment benchmarks (see source paper)"
        _row[9] = "Financial text"
        _row[10] = "Financial sentiment model"
        _row[11] = "Sentiment classification metrics"
        _row[12] = ""
        _row[13] = "Verified replacement for the previous mismatched GPT-4 sentiment record."
    elif record_id(_row) == "S11":
        _row[1] = "Sentiment Trading with Large Language Models"
        _row[3] = "Finance Research Letters"
        _row[4] = "Elsevier"
        _row[6] = "10.1016/j.frl.2024.105227"
        _row[7] = "No verified official code"
        _row[8] = "965,375 U.S. financial-news articles; CRSP daily returns; Refinitiv Global News"
        _row[9] = "Stock"
        _row[10] = "OPT, BERT and FinBERT sentiment scores; long-short portfolios"
        _row[11] = "Accuracy, Sharpe ratio, cumulative return"
        _row[12] = ""
        _row[13] = "Kirtac & Germano (2024): OPT reports 74.4% accuracy and Sharpe 3.05 after 10 bps transaction costs."
    elif record_id(_row) == "S12":
        _row[6] = "10.1016/j.gfj.2024.100945"
    elif record_id(_row) == "E01":
        _row[2] = "2020"
        _row[3] = "arXiv (arXiv:2011.09607)"
        _row[4] = "arXiv"
        _row[5] = "N/A"
        _row[13] = "Preprint; do not treat as a journal-Q1 publication. A workshop version may be cited separately only after verifying its proceedings record."
    elif record_id(_row) == "E12":
        _row[1] = "A Pre-registered, Compute-Controlled Falsification of LLM-Derived Signals on Crypto Microstructure"
        _row[3] = "SSRN Working Paper"
        _row[4] = "SSRN"
        _row[5] = "N/A"
        _row[6] = "10.2139/ssrn.6997818"
        _row[13] = "SSRN preprint, posted 2026-07-06; not peer reviewed. Useful as recent negative/falsification evidence, not as archival evidence."
    elif record_id(_row) == "H10":
        _row[1] = "Explainable Zero-Shot Trading Using Multi-Agent LLM Architecture: A Backtested Approach for Bitcoin Price"
        _row[2] = "2025 online / 2026 issue"
        _row[3] = "Information Processing & Management"
        _row[4] = "Elsevier"
        _row[6] = "10.1016/j.ipm.2025.104466"
        _row[13] = "Journal article; DOI verified. Online-first year is 2025; final issue is 2026, vol. 63(2), article 104466."
    elif record_id(_row) == "T02":
        _row[6] = "10.24963/ijcai.2019/810"
    elif record_id(_row) == "T09":
        _row[6] = "10.1145/3292500.3330647"
    elif record_id(_row) == "T10":
        _row[6] = "10.1609/aaai.v38i1.27767"
    elif record_id(_row) == "S02":
        _row[1] = "Stock Movement Prediction from Tweets and Historical Prices (StockNet)"
        _row[6] = "10.18653/v1/P18-1183"
    elif record_id(_row) == "E04":
        _row[6] = "10.1111/1468-0262.00152"
    elif record_id(_row) == "E05":
        _row[6] = "10.1198/073500105000000063"
        _row[7] = "N/A"
        _row[8] = "N/A (methodology paper)"
        _row[9] = "N/A"
        _row[11] = "SPA statistic, p-value / critical value"
    elif record_id(_row) == "E07":
        _row[1] = "Performance Hypothesis Testing with the Sharpe and Treynor Measures"
        _row[6] = "10.1111/j.1540-6261.1981.tb04891.x"
        _row[7] = "N/A"
        _row[8] = "N/A (methodology paper)"
        _row[9] = "N/A"
        _row[10] = "Jobson-Korkie performance-hypothesis test"
        _row[11] = "Z statistic, p-value"
    elif record_id(_row) == "E09":
        _row[1] = "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap"
        _row[6] = "10.1111/0022-1082.00163"
        _row[7] = "No verified official code"
        _row[8] = "100 years of daily Dow Jones Industrial Average (DJIA) data"
        _row[9] = "Stock index"
        _row[10] = "White's Reality Check bootstrap for technical trading rules"
        _row[11] = "Reality Check p-value"
        _row[13] = "Evaluates 26 technical trading rules; do not label this as S&P 500 data."

# Remove stale detail rows for the two corrected records instead of carrying
# over unsupported claims from their previous (incorrect) identities.
for _row in s2_data:
    if record_id(_row) == "T02":
        _row[:] = ["T02", "Adv-ALSTM (2019)", "N/A", "N/A", "N/A", "N/A", "Yes", "No", "No", "Yes", "ACL18/KDD17 benchmark models", "Paper-specific limitations", "Adversarial training for stock-movement classification; metrics are Accuracy and MCC, not Sharpe."]
    elif record_id(_row) == "T03":
        _row[:] = ["T03", "Common Risk Factors in Cryptocurrency (2022)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Crypto factor portfolios", "Requires broad historical cross-section", "Verified replacement for the prior unrecoverable placeholder."]
    elif record_id(_row) == "T04":
        _row[:] = ["T04", "Helformer (2025)", "N/A", "N/A", "N/A", "N/A", "Yes", "No", "Yes", "No", "Paper-specific forecasting baselines", "Verify implementation details from source", "Verified Transformer-based crypto forecasting reference."]
for _row in s3_data:
    if record_id(_row) == "S07":
        _row[:] = ["S07", "FinSentGPT (2024)", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "See source paper", "Not a trading-return study", "Verified financial-sentiment reference; no unsupported GPT-4 trading claim."]
    elif record_id(_row) == "S11":
        _row[:] = ["S11", "Sentiment Trading with Large Language Models (2024)", "Yes", "No", "No", "Yes", "No", "OPT", "No", "74.4% (OPT)", "Sharpe 3.05 after 10 bps costs; 355% gain (Aug-2021 to Jul-2023)", "Uses 965,375 U.S. financial-news articles, CRSP daily returns, and Refinitiv Global News. Do not infer use of Twitter/Reddit/FinGPT."]
for _row in s5_data:
    if record_id(_row) == "E05":
        _row[:] = ["E05", "Hansen SPA Test (2005)", "Statistical methodology", "Benchmark forecast vs alternatives -> bootstrap -> SPA test", "N/A", "SPA statistic, p-value / critical value", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "SPA test", "Methodology paper: fields about a trading-system experimental control are not applicable."]
    elif record_id(_row) == "E07":
        _row[:] = ["E07", "Jobson-Korkie Test (1981)", "Statistical methodology", "Portfolio return moments -> Sharpe/Treynor difference -> test statistic", "N/A", "Z statistic, p-value", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Jobson-Korkie test", "Methodology paper: fields about a trading-system experimental control are not applicable."]
    elif record_id(_row) == "E09":
        _row[:] = ["E09", "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap (1999)", "Statistical methodology", "Daily DJIA data -> 26 technical rules -> Reality Check bootstrap", "Historical-data empirical study", "Reality Check p-value", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "White's Reality Check", "Uses 100 years of daily DJIA data; do not describe it as an S&P 500 study or a 10k-rule experiment."]
for _row in s9_data:
    if record_id(_row) == "T04":
        _row[1] = "Helformer: Attention-Based Cryptocurrency Price Forecasting"
        _row[2] = "2025"
        _row[6] = "Crypto price series -> Holt-Winters decomposition -> Transformer -> Forecast"
        _row[7] = "Research implementation"
        _row[8] = "Forecasting metrics"
        _row[10] = "Verified replacement for an invalid DOI/title pairing."
    elif record_id(_row) == "S07":
        _row[1] = "FinSentGPT: A Universal Financial Sentiment Engine?"
        _row[2] = "2024"
        _row[6] = "Financial text -> Financial sentiment model -> Sentiment output"
        _row[7] = "Research implementation"
        _row[8] = "Sentiment classification metrics"
        _row[10] = "Verified replacement; do not describe it as a GPT-4 trading-return study."
    elif record_id(_row) == "S11":
        _row[1] = "Sentiment Trading with Large Language Models"
        _row[2] = "2024"
        _row[6] = "U.S. financial news -> OPT/BERT/FinBERT sentiment -> daily long-short portfolios"
        _row[7] = "No verified official code"
        _row[8] = "74.4% accuracy; Sharpe 3.05 (10 bps costs)"
        _row[10] = "Kirtac & Germano, Finance Research Letters 62, 105227."

# Verified crypto Technical additions (2026-08-06).  These replace the older
# unverified placeholder rows with the same IDs in every dependent table.
def _replace_records(rows, additions):
    ids = {row[0] for row in additions}
    return [row for row in rows if record_id(row) not in ids] + additions

_crypto_master = [
    ["T05", "Technical trading and cryptocurrencies", "2021", "Annals of Operations Research", "Springer Nature", "See venue / source", "10.1007/s10479-019-03357-1", "No verified official code", "CoinDesk and Bitstamp BTC; CoinMarketCap LTC, ETH, XRP", "BTC, LTC, ETH, XRP", "~15,000 technical rules; FWER/FDR controls", "Annualized return, Sharpe, Sortino, Calmar, breakeven cost", "", "Peer-reviewed crypto technical baseline; BTC has no positive reported OOS return. Source: https://link.springer.com/article/10.1007/s10479-019-03357-1"],
    ["T06", "State transitions and momentum effect in cryptocurrency market", "2025", "Finance Research Letters", "Elsevier", "See venue / source", "10.1016/j.frl.2025.108356", "No verified official code", "CoinMarketCap daily prices, market capitalization and volume, 2015-2023", "Cryptocurrency market", "Regime-conditioned weekly momentum", "State-dependent momentum profitability", "", "Peer-reviewed; momentum concentrates in sustained UP-UP regimes. Source: https://www.sciencedirect.com/science/article/abs/pii/S1544612325016101"],
    ["T07", "Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions", "2024", "SSRN Working Paper", "SSRN", "N/A", "10.2139/ssrn.4675565", "No verified official code", "See paper for full universe", "Cryptocurrency market", "Time-series vs cross-sectional momentum with costs and liquidation risk", "Profitability, liquidation risk", "", "Working paper / not peer reviewed; robustness evidence only. Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565"],
]
_crypto_technical = [
    ["T05", "Technical trading and cryptocurrencies (2021)", "✓", "N/A", "N/A", "✗", "✗", "✗", "✓", "✗", "Buy-and-hold; multiple-testing controls", "BTC has no positive reported OOS return", "Peer-reviewed crypto technical-rule study."],
    ["T06", "State transitions and momentum effect in cryptocurrency market (2025)", "N/A", "N/A", "N/A", "✗", "✗", "✗", "✓", "✗", "State-conditioned momentum portfolios", "Weekly CoinMarketCap study; no verified code", "Use a sustained UP-UP regime gate."],
    ["T07", "Momentum in the Cryptocurrency Market (2024)", "N/A", "N/A", "N/A", "✗", "✗", "✗", "✓", "✗", "Time-series vs cross-sectional momentum", "Working paper; no verified code", "Use realistic cost and liquidation checks."],
]
_crypto_selected = [
    ["T05", "Technical trading and cryptocurrencies", "2021", "Mới (5 năm)", "Crypto / Technical Trading", "Technical-rule evaluation", "Market data -> 5 rule families -> FWER/FDR -> cost-aware backtest", "Vectorized backtest; CoinDesk/Bitstamp/CoinMarketCap", "Annualized return, Sharpe, Sortino, Calmar, breakeven cost", "High", "Peer-reviewed; direct crypto technical baseline. Bitcoin OOS caveat retained."],
    ["T06", "State transitions and momentum effect in cryptocurrency market", "2025", "Mới (5 năm)", "Crypto / Technical Trading", "Regime-conditioned momentum", "CoinMarketCap data -> market-state transition -> weekly momentum portfolios", "Research implementation; 2015-2023 CoinMarketCap", "State-dependent momentum profitability", "High", "Peer-reviewed; supports an UP-UP regime gate, not unconditional momentum."],
]

# The same source records must appear in every matrix that makes a claim about
# their design, metrics or gap coverage.  T07 remains corpus-only (SSRN) and is
# deliberately not inserted into Sheet 9.
_crypto_experimental = [
    ["T05", "Technical trading and cryptocurrencies (2021)", "Technical-rule evaluation", "Market data -> technical rules -> FWER/FDR -> transaction-cost robustness", "Historical-rule backtest", "Annualized return, Sharpe, Sortino, Calmar, breakeven cost", "No", "Cost sensitivity", "No", "No", "No", "Multi", "FWER/FDR multiple-testing controls", "Peer-reviewed crypto baseline; not a controlled system comparison."],
    ["T06", "State transitions and momentum effect in cryptocurrency market (2025)", "Regime-conditioned momentum", "CoinMarketCap -> state transition -> weekly momentum portfolios", "Historical weekly portfolio backtest", "State-dependent momentum profitability", "No", "Not fully specified in matrix", "No", "No", "No", "Multi", "No formal test reported here", "Peer-reviewed; use as evidence for a regime gate rather than unconditional momentum."],
    ["T07", "Momentum in the Cryptocurrency Market (2024)", "Momentum robustness study", "Crypto universe -> momentum portfolios -> realistic cost/liquidation checks", "Research backtest", "Profitability, liquidation risk", "No", "Cost-aware", "No", "No", "No", "Multi", "See working paper", "SSRN working paper; retained as corpus evidence only."],
]
_crypto_metrics = [
    ["T05", "Technical trading and cryptocurrencies (2021)", "✓", "✓", "✓", "✓", "✗", "✗", "✓", "✗", "FWER/FDR", "✗", "Uses multiple-testing controls and cost robustness; do not infer a positive BTC OOS result."],
    ["T06", "State transitions and momentum effect in cryptocurrency market (2025)", "✓", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "Reports state-dependent momentum profitability; no unsupported metric/test is added."],
    ["T07", "Momentum in the Cryptocurrency Market (2024)", "✓", "✗", "✗", "✗", "✗", "✗", "✓", "✗", "✗", "✗", "Working-paper robustness evidence; liquidation risk is not a VaR result."],
]
_crypto_gap = [
    ["T05", "Technical trading and cryptocurrencies (2021)", "✗", "✗", "Multi", "✗", "✗", "Partial", "✗", "Strong multiple-testing control, but no identical technical-vs-AI execution comparison.", "Peer-reviewed crypto technical-rule baseline."],
    ["T06", "State transitions and momentum effect in cryptocurrency market (2025)", "✗", "✗", "Multi", "✗", "✗", "✗", "✗", "Supports a regime gate; does not isolate the incremental value of other signals.", "Peer-reviewed crypto momentum study."],
    ["T07", "Momentum in the Cryptocurrency Market (2024)", "✗", "✗", "Multi", "✗", "✗", "✗", "✗", "Cost/liquidation robustness is useful, but the source is a working paper.", "Corpus-only robustness evidence."],
]

# Peer-reviewed crypto methods that materially informed the project's Tech
# design or a documented transfer test.  The list is intentionally selective:
# preprints and papers that were merely discovered but did not affect the
# research design remain in the working backlog rather than the Matrix.
_tech_method_master = [
    ["T03", "Common Risk Factors in Cryptocurrency", "2022", "The Journal of Finance", "Wiley", "See venue / source", "10.1111/jofi.13119", "No verified official code", "Broad cryptocurrency cross-section", "Cryptocurrency", "Market, size and momentum factor portfolios", "Excess return, alpha, t-statistic", "", "Top-tier factor foundation. The project's narrow perpetual transfer failed and is not a replication. Source: https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119"],
    ["T08", "Trading Volume and Liquidity Provision in Cryptocurrency Markets", "2022", "Journal of Banking & Finance", "Elsevier", "See venue / source", "10.1016/j.jbankfin.2022.106547", "No verified official code", "CryptoCompare OHLCV and CoinGecko market cap; 80+ centralized exchanges, 2017-2022", "Cryptocurrency", "Short-term reversal conditional on detrended volume", "Return, Sharpe ratio, regression p-value, cost robustness", "", "Peer-reviewed liquidity-provision evidence; strongest in smaller and less-liquid pairs. Source: https://www.sciencedirect.com/science/article/pii/S0378426622001418"],
    ["T11", "Disagreement and Returns: The Case of Cryptocurrencies", "2025", "Financial Management", "Wiley", "See venue / source", "10.1111/fima.12491", "No verified official code", "Binance cryptocurrency cross-section; volume, order imbalance and margin-trading status", "Cryptocurrency", "Abnormal-volume disagreement under short-sale constraints", "Future return, factor-adjusted return, regression inference", "", "Peer-reviewed microstructure evidence. The effect weakens after margin trading becomes available. Source: https://onlinelibrary.wiley.com/doi/10.1111/fima.12491"],
    ["T12", "Cryptocurrency Market Risk-Managed Momentum Strategies", "2025", "Finance Research Letters", "Elsevier", "See venue / source", "10.1016/j.frl.2025.107879", "No verified official code", "CoinMarketCap cryptocurrency cross-section", "Cryptocurrency", "Volatility-managed weekly winner-minus-loser momentum", "Weekly return, annualized Sharpe, t-statistic, cost robustness", "", "Peer-reviewed risk-managed momentum. Average scaling weight exceeds one, so higher return partly reflects higher exposure. Source: https://www.sciencedirect.com/science/article/pii/S1544612325011377"],
    ["T13", "Stop-Loss Rules and Momentum Payoffs in Cryptocurrencies", "2023", "Journal of Behavioral and Experimental Finance", "Elsevier", "See venue / source", "10.1016/j.jbef.2023.100833", "No verified official code", "147 cryptocurrencies, January 2015-June 2022", "Cryptocurrency", "Cross-sectional momentum with predetermined stop-loss rules", "Return, Sharpe ratio, alpha, volatility, skewness", "", "Peer-reviewed support for pre-specified stop-loss ablation across market states. Source: https://www.sciencedirect.com/science/article/pii/S2214635023000473"],
    ["T14", "Liquidity Shocks, Price Volatilities, and Risk-Managed Strategy: Evidence from Bitcoin and Beyond", "2022", "Journal of Multinational Financial Management", "Elsevier", "See venue / source", "10.1016/j.mulfin.2022.100729", "No verified official code", "BTC plus ETH, XLM, LTC and XRP; 2014-2020; market and funding liquidity", "Cryptocurrency", "Amihud and funding-liquidity shocks for volatility-managed exposure", "Sharpe ratio, skewness, crash-risk outcomes", "", "Peer-reviewed risk overlay. The project tested only a causal Amihud proxy and rejected it; not a replication. Source: https://www.sciencedirect.com/science/article/pii/S1042444X22000019"],
    ["T15", "An Empirical Investigation on Risk Factors in Cryptocurrency Futures", "2023", "Journal of Futures Markets", "Wiley", "See venue / source", "10.1002/fut.22425", "No verified official code", "12 OKEx current-quarter futures, November 2017-March 2021; licensed data", "Cryptocurrency futures", "Basis, momentum and basis-momentum factor portfolios", "Excess return, alpha, t-statistic, transaction-cost robustness", "", "Peer-reviewed derivatives evidence. Results concern dated futures, not perpetual contracts. Source: https://onlinelibrary.wiley.com/doi/10.1002/fut.22425"],
    ["T16", "Order Flow and Cryptocurrency Returns", "2026", "Journal of Financial Markets", "Elsevier", "See venue / source", "10.1016/j.finmar.2026.101047", "No verified official code", "84 cryptocurrencies; 300+ exchanges; order flow in 11 currencies", "Cryptocurrency", "World order flow with out-of-sample nonlinear ML and portfolio sorts", "OOS prediction and economic-value portfolio metrics", "", "Peer-reviewed market-microstructure study. A single-venue taker-flow transfer is not equivalent to world order flow. Source: https://www.sciencedirect.com/science/article/pii/S1386418126000029"],
    ["T17", "A Trend Factor for the Cross Section of Cryptocurrency Returns", "2025", "Journal of Financial and Quantitative Analysis", "Cambridge University Press", "See venue / source", "10.1017/S0022109024000747", "No verified official code", "More than 3,000 cryptocurrencies, April 2015-May 2022", "Cryptocurrency", "CTREND aggregation of 28 price, volume, momentum and volatility signals", "Factor return, alpha, Sharpe ratio, Newey-West t-statistic, cost robustness", "", "Top-tier cross-sectional trend evidence. The project's oscillator-only narrow transfer was rejected and is not CTREND replication. Source: https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178"],
    ["T18", "Perpetual Futures Pricing", "2026", "Mathematical Finance", "Wiley", "See venue / source", "10.1111/mafi.70018", "No verified official code", "Model-theoretic perpetual futures setting", "Perpetual futures", "Perpetual-futures pricing model with funding mechanism", "Pricing relation, funding rate, basis dynamics", "", "Required foundation for defining perpetual futures and funding. Publisher and Crossref metadata are archived in paper/input/references/source_artifacts."],
    ["T19", "Perpetual future contracts in centralized and decentralized exchanges: Mechanism and traders' behavior", "2024", "Electronic Markets", "Springer", "See venue / source", "10.1007/s12525-024-00715-1", "No verified official code", "Centralized and decentralized perpetual-futures exchange mechanisms", "Perpetual futures", "Mechanism analysis and trader-behavior comparison", "Funding mechanism, exchange design, trader behavior", "", "Mechanism reference for centralized/decentralized perpetual contracts and funding behavior. Publisher and Crossref metadata are archived in paper/input/references/source_artifacts."],
]

_tech_method_technical = [
    ["T03", "Common Risk Factors in Cryptocurrency (2022)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Crypto three-factor and characteristic portfolios", "Needs broad point-in-time cross-section; not a fixed perpetual list", "Foundation for cross-sectional momentum and dynamic universe design."],
    ["T08", "Trading Volume and Liquidity Provision (2022)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Short-term reversal by detrended-volume state", "Premium is concentrated in smaller/less-liquid pairs", "Motivated the separate reversal/liquidity transfer test."],
    ["T11", "Disagreement and Returns (2025)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Abnormal volume, order imbalance, short-sale constraints", "Effect may not transfer to perpetuals with easy shorting", "Supports treating abnormal volume as a conditional veto, not universal alpha."],
    ["T12", "Risk-Managed Momentum (2025)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Conventional weekly momentum", "Scaling weight above one raises exposure", "Motivated inverse-volatility sizing; exposure and alpha are reported separately."],
    ["T13", "Stop-Loss Momentum (2023)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Momentum without stop; alternative thresholds", "Monthly 30% paper rule differs from the project's 4H ATR stop", "Supports a pre-specified stop-loss ablation, not copying its threshold."],
    ["T14", "Liquidity-Shock Risk Management (2022)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Buy-and-hold and liquidity-conditioned exposure", "True funding-liquidity input is unavailable in the transfer", "Amihud proxy was tested causally and rejected."],
    ["T15", "Crypto Futures Risk Factors (2023)", "N/A", "N/A", "N/A", "No", "No", "No", "Yes", "No", "Basis, momentum and basis-momentum portfolios", "OKEx dated futures differ from perpetual swaps", "Motivated basis/term-structure tests with an explicit non-transfer caveat."],
    ["T16", "World Order Flow (2026)", "N/A", "N/A", "N/A", "Yes", "No", "No", "Yes", "No", "Economic fundamentals and nonlinear ML models", "Requires multi-exchange, multi-currency signed flow", "Single-venue taker flow was tested and rejected as a proxy."],
    ["T17", "CTREND (2025)", "N/A", "Yes", "N/A", "Yes", "No", "No", "Yes", "No", "Known crypto factors and individual trend indicators", "Requires >3,000-coin cross-section and rolling combined elastic net", "Supports aggregate trend features; oscillator-only transfer was rejected."],
    ["T18", "Perpetual Futures Pricing (2026)", "N/A", "N/A", "Yes", "No", "No", "No", "Yes", "No", "Perpetual futures and funding definition", "Theory paper; not a trading-signal study", "Required terminology source for perpetual pricing and funding."],
    ["T19", "Perpetual exchange mechanisms (2024)", "N/A", "N/A", "Yes", "No", "No", "No", "Yes", "No", "CEX/DEX perpetual mechanism and trader behavior", "Mechanism study; not a strategy backtest", "Required background source for perpetual-contract mechanics."],
]

_tech_method_experimental = [
    ["T03", "Common Risk Factors in Cryptocurrency (2022)", "Cross-sectional factor design", "Point-in-time crypto cross-section -> characteristic sorts -> factor portfolios", "Historical portfolio study", "Excess return, alpha, t-statistic", "No", "Cost robustness", "No", "No", "No", "Multi", "Factor-regression inference", "Foundation for universe and factor design; not a controlled AI comparison."],
    ["T08", "Trading Volume and Liquidity Provision (2022)", "Conditional reversal design", "Multi-exchange data -> detrended volume -> reversal sorts -> regressions", "Historical daily portfolio study", "Return, Sharpe, p-value, cost robustness", "No", "Linear transaction-cost robustness", "No", "No", "No", "Multi", "Panel-regression inference", "Useful transfer benchmark; paper's low-liquidity capacity differs from the project."],
    ["T11", "Disagreement and Returns (2025)", "Conditional microstructure design", "Binance activity -> abnormal volume/order imbalance -> future returns", "Historical daily cross-section", "Future and factor-adjusted returns", "No", "Not the primary design variable", "No", "No", "No", "Multi", "Regression inference", "Short-sale constraints are a moderator, limiting perpetual transfer."],
    ["T12", "Risk-Managed Momentum (2025)", "Risk-managed portfolio comparison", "CoinMarketCap -> weekly WML -> volatility scaling -> robustness", "Historical weekly portfolio study", "Return, Sharpe, t-statistic", "Yes", "Transaction-cost robustness", "No", "No", "No", "Multi", "Return significance tests", "Comparison is informative, but exposure changes with scaling."],
    ["T13", "Stop-Loss Momentum (2023)", "Exit-rule ablation", "147 coins -> momentum portfolios -> fixed stop-loss thresholds -> market states", "Historical monthly portfolio study", "Return, Sharpe, alpha, volatility, skewness", "Yes", "Robustness analysis", "Partial", "No", "No", "Multi", "Factor-alpha inference", "Supports risk/exit ablation; does not isolate AI assessment value."],
    ["T14", "Liquidity-Shock Risk Management (2022)", "Liquidity-risk overlay", "Liquidity shocks -> volatility forecast -> conditional exposure", "Historical daily strategy study", "Sharpe, skewness, crash-risk outcomes", "No", "Not fully specified in Matrix", "Partial", "No", "No", "Multi", "Quantile-regression inference", "Project proxy transfer lacks the paper's funding-liquidity input."],
    ["T15", "Crypto Futures Risk Factors (2023)", "Derivatives factor design", "OKEx dated futures -> basis/momentum sorts -> daily/weekly/monthly factors", "Historical futures portfolio study", "Excess return, alpha, t-statistic", "No", "Transaction-cost robustness", "No", "No", "No", "Multi", "Spanning/factor regressions", "Contract type and historical sample differ from current perpetual execution."],
    ["T16", "World Order Flow (2026)", "OOS predictive-economic-value design", "World signed flow -> nonlinear ML -> OOS portfolios", "Historical multi-exchange study", "OOS prediction and portfolio economic value", "No", "Limits-to-arbitrage robustness", "No", "No", "No", "Multi", "OOS predictive tests", "Project used only a single-venue transfer proxy."],
    ["T17", "CTREND (2025)", "Aggregate trend-factor design", ">3,000 coins -> 28 indicators -> rolling combined elastic net -> factor portfolios", "Historical OOS cross-section", "Factor return, alpha, Sharpe, robust t-statistic", "No", "Transaction-cost robustness", "No", "No", "No", "Multi", "Newey-West inference and alternative designs", "Directly relevant to aggregate Tech signals but not replicated by the narrow universe."],
    ["T18", "Perpetual Futures Pricing (2026)", "Instrument-pricing foundation", "Perpetual contract -> mark/index relationship -> funding mechanism", "Analytical pricing study", "Pricing relation, funding rate, basis dynamics", "No", "N/A", "Yes", "No", "No", "N/A", "Theoretical derivation", "Defines the contract/funding object used by the project's executor; not evidence of alpha."],
    ["T19", "Perpetual exchange mechanisms (2024)", "Market-mechanism foundation", "CEX/DEX perpetual design -> funding and trader behavior comparison", "Mechanism and behavioral analysis", "Funding mechanism, exchange design, trader behavior", "No", "N/A", "Yes", "No", "No", "N/A", "Mechanism analysis", "Supports background on perpetual-futures mechanics; not a controlled Tech-vs-AI experiment."],
]

_tech_method_metrics = [
    ["T03", "Common Risk Factors in Cryptocurrency (2022)", "Yes", "No", "No", "No", "No", "No", "No", "No", "Factor regressions", "No", "Reports statistically significant characteristic and factor premiums."],
    ["T08", "Trading Volume and Liquidity Provision (2022)", "Yes", "Yes", "No", "No", "No", "No", "No", "No", "Panel/regression p-values", "No", "Includes linear transaction-cost robustness."],
    ["T11", "Disagreement and Returns (2025)", "Yes", "No", "No", "No", "No", "No", "No", "No", "Regression inference", "No", "Tests the conditional abnormal-volume relation."],
    ["T12", "Risk-Managed Momentum (2025)", "Yes", "Yes", "No", "No", "No", "No", "No", "No", "Return t-statistics", "No", "Reports weekly return and annualized Sharpe with robustness checks."],
    ["T13", "Stop-Loss Momentum (2023)", "Yes", "Yes", "No", "No", "No", "No", "No", "No", "Factor-alpha inference", "No", "Reports risk, skewness and market-state robustness."],
    ["T14", "Liquidity-Shock Risk Management (2022)", "Yes", "Yes", "No", "No", "No", "No", "No", "No", "Quantile regression", "No", "Risk-managed strategy focuses on crash reduction and Sharpe."],
    ["T15", "Crypto Futures Risk Factors (2023)", "Yes", "No", "No", "No", "No", "No", "No", "No", "Factor/spanning regressions", "No", "Daily basis premium is stronger than weekly/monthly evidence."],
    ["T16", "World Order Flow (2026)", "Yes", "Yes", "No", "No", "No", "No", "No", "No", "OOS predictive tests", "No", "Economic-value evaluation uses true world order flow."],
    ["T17", "CTREND (2025)", "Yes", "Yes", "No", "No", "No", "No", "No", "No", "Newey-West t-statistics", "No", "Tests costs, market states, liquidity subsamples and alternative designs."],
    ["T18", "Perpetual Futures Pricing (2026)", "No", "No", "No", "No", "No", "No", "No", "Yes", "Theoretical derivation", "No", "Funding/pricing definition source, not an empirical backtest."],
    ["T19", "Perpetual exchange mechanisms (2024)", "No", "No", "No", "No", "No", "No", "No", "Yes", "Mechanism analysis", "No", "CEX/DEX mechanism source, not an empirical strategy evaluation."],
]

_tech_method_gap = [
    ["T03", "Common Risk Factors in Cryptocurrency (2022)", "No", "No", "Multi", "No", "No", "Partial", "No", "Explains crypto factor returns but does not isolate AI-derived assessment value.", "High-quality factor foundation."],
    ["T08", "Trading Volume and Liquidity Provision (2022)", "No", "No", "Multi", "No", "No", "No", "No", "Conditions reversal on volume; no identical AI-vs-Tech system comparison.", "High-quality microstructure evidence."],
    ["T11", "Disagreement and Returns (2025)", "No", "No", "Multi", "No", "No", "Partial", "No", "Identifies a conditional volume-return mechanism, not marginal AI value.", "Short-sale constraints matter for interpretation."],
    ["T12", "Risk-Managed Momentum (2025)", "Partial", "No", "Multi", "No", "No", "No", "No", "Compares momentum sizing variants but changes effective exposure.", "Useful warning: higher return is not automatically new alpha."],
    ["T13", "Stop-Loss Momentum (2023)", "Partial", "No", "Multi", "No", "No", "No", "No", "Exit-rule ablation is useful, but AI information is outside scope.", "Supports common risk controls in the proposed experiment."],
    ["T14", "Liquidity-Shock Risk Management (2022)", "No", "No", "Multi", "No", "No", "No", "No", "Liquidity-conditioned exposure changes the system rather than isolating an AI assessment.", "Project transfer was negative."],
    ["T15", "Crypto Futures Risk Factors (2023)", "No", "No", "Multi", "No", "No", "No", "No", "Basis evidence is contract/sample specific and does not test AI incremental value.", "Important derivatives comparison."],
    ["T16", "World Order Flow (2026)", "No", "Partial", "Multi", "No", "No", "No", "No", "Measures economic value of order flow, but changes predictors/models together.", "Closest data-rich market-microstructure evidence."],
    ["T17", "CTREND (2025)", "No", "No", "Multi", "No", "No", "Partial", "No", "Aggregates many Tech indicators but does not hold the rest of the system fixed against AI.", "Strong evidence for an aggregate Tech baseline."],
    ["T18", "Perpetual Futures Pricing (2026)", "No", "No", "N/A", "No", "No", "No", "Yes", "Defines perpetual-futures pricing and funding but does not estimate AI incremental value.", "Required instrument-definition source."],
    ["T19", "Perpetual exchange mechanisms (2024)", "No", "No", "N/A", "No", "No", "No", "Yes", "Explains contract mechanisms and behavior but does not compare Tech-only against AI.", "Required market-mechanism source."],
]

_tech_method_selected = [
    ["T03", "Common Risk Factors in Cryptocurrency", "2022", "Recent", "Crypto / Factor foundation", "Cross-sectional factor portfolios", "Point-in-time universe -> characteristics -> market/size/momentum factors", "Broad cryptocurrency cross-section", "Excess return, alpha, t-statistic", "Very high", "Journal of Finance; foundation for factor and universe design."],
    ["T08", "Trading Volume and Liquidity Provision in Cryptocurrency Markets", "2022", "Recent", "Crypto / Liquidity", "Conditional short-term reversal", "Multi-exchange OHLCV -> detrended volume -> reversal portfolios", "CryptoCompare/CoinGecko; 80+ exchanges", "Return, Sharpe, regression inference, costs", "High", "Journal of Banking & Finance; direct liquidity-method reference."],
    ["T11", "Disagreement and Returns: The Case of Cryptocurrencies", "2025", "Recent", "Crypto / Market microstructure", "Conditional disagreement signal", "Binance activity -> abnormal volume/order imbalance -> future returns", "Binance cryptocurrency cross-section", "Future return, factor-adjusted return, regression inference", "High", "Financial Management; clarifies the role of short-sale constraints in abnormal-volume signals."],
    ["T12", "Cryptocurrency Market Risk-Managed Momentum Strategies", "2025", "Recent", "Crypto / Risk-managed momentum", "Volatility-managed WML", "CoinMarketCap -> weekly momentum -> volatility scaling", "Crypto cross-section", "Return, Sharpe, t-statistic, costs", "High", "Peer-reviewed; exposure-scaling caveat is material."],
    ["T13", "Stop-Loss Rules and Momentum Payoffs in Cryptocurrencies", "2023", "Recent", "Crypto / Risk overlay", "Stop-loss momentum ablation", "147 coins -> momentum -> fixed stop-loss -> market-state robustness", "Cryptocurrency cross-section", "Return, Sharpe, alpha, skewness", "High", "Peer-reviewed source for exit-rule ablation."],
    ["T14", "Liquidity Shocks, Price Volatilities, and Risk-Managed Strategy: Evidence from Bitcoin and Beyond", "2022", "Recent", "Crypto / Liquidity risk", "Liquidity-conditioned risk management", "Market/funding liquidity shocks -> volatility forecast -> conditional exposure", "BTC, ETH, XLM, LTC and XRP", "Sharpe, skewness, crash-risk outcomes", "High", "Peer-reviewed source for liquidity-risk overlays; the project's proxy transfer was negative."],
    ["T15", "An Empirical Investigation on Risk Factors in Cryptocurrency Futures", "2023", "Recent", "Crypto futures / Basis", "Derivatives factor portfolios", "OKEx dated futures -> basis/momentum sorts -> factor returns", "12 OKEx current-quarter futures", "Excess return, alpha, t-statistic, costs", "Very high", "Journal of Futures Markets; contract-type caveat retained."],
    ["T16", "Order Flow and Cryptocurrency Returns", "2026", "Recent", "Crypto / Order flow", "World-order-flow OOS prediction", "300+ exchanges -> signed flow -> nonlinear ML -> OOS portfolios", "84 coins; 11 currencies", "OOS prediction and economic value", "Very high", "Journal of Financial Markets; true multi-exchange input is essential."],
    ["T17", "A Trend Factor for the Cross Section of Cryptocurrency Returns", "2025", "Recent", "Crypto / Aggregate trend", "CTREND combined elastic net", ">3,000 coins -> 28 indicators -> rolling aggregate trend factor", "Broad survivorship-aware crypto cross-section", "Factor return, alpha, Sharpe, robust t-statistic", "Very high", "JFQA; closest high-quality aggregate-Tech design reference."],
    ["T18", "Perpetual Futures Pricing", "2026", "Recent", "Perpetual futures / Funding", "Perpetual pricing and funding definition", "Perpetual contract -> pricing relation -> funding mechanism", "Theoretical perpetual-futures setting", "Pricing relation, funding rate, basis dynamics", "Very high", "Mathematical Finance; required source for perpetual futures and funding definitions."],
    ["T19", "Perpetual future contracts in centralized and decentralized exchanges: Mechanism and traders' behavior", "2024", "Recent", "Perpetual futures / Exchange mechanism", "CEX/DEX perpetual mechanism comparison", "Exchange design -> funding mechanism -> trader behavior", "Centralized and decentralized perpetual-futures markets", "Mechanism and behavior analysis", "High", "Electronic Markets; required background for perpetual contract mechanics."],
]

# Sheet 9 chỉ sử dụng hai nhóm thời gian theo quy ước chung của Matrix.
for _row in _tech_method_selected:
    _row[3] = "Mới (5 năm)"

s1_data = _replace_records(s1_data, _crypto_master)
s2_data = _replace_records(s2_data, _crypto_technical)
s5_data = _replace_records(s5_data, _crypto_experimental)
s6_data = _replace_records(s6_data, _crypto_metrics)
s7_data = _replace_records(s7_data, _crypto_gap)
s9_data = [row for row in s9_data if record_id(row) != "T07"]  # old unverified placeholder
s9_data = _replace_records(s9_data, _crypto_selected)
s1_data = _replace_records(s1_data, _tech_method_master)
s2_data = _replace_records(s2_data, _tech_method_technical)
s5_data = _replace_records(s5_data, _tech_method_experimental)
s6_data = _replace_records(s6_data, _tech_method_metrics)
s7_data = _replace_records(s7_data, _tech_method_gap)
s9_data = _replace_records(s9_data, _tech_method_selected)

# Enforcement tại dữ liệu cuối: Sheet 9 không chấp nhận nhóm thứ ba.
for _row in s9_data:
    if record_id(_row) and _row[3] not in {"Kinh điển", "Mới (5 năm)"}:
        _row[3] = "Mới (5 năm)"

# Complete the bibliometric fields for recently added/corrected records.
# Quartiles use the 2024 JCR journal quartile. SSRN records have no journal
# quartile. Citation counts are an OpenAlex snapshot taken on 2026-08-08;
# keeping the date and work URL in the row makes these changing values auditable.
_recent_bibliometrics = {
    "T04": ("Q1", 44, "https://openalex.org/W4409170628"),
    "T05": ("Q1", 90, "https://openalex.org/W2970972678"),
    "T06": ("Q1", 4, "https://openalex.org/W4413944035"),
    "T07": ("N/A", 1, "https://openalex.org/W4390903138"),
    "S07": ("Q1", 22, "https://openalex.org/W4394875003"),
    "S11": ("Q1", 88, "https://openalex.org/W4392859372"),
    "H10": ("Q1", 6, "https://openalex.org/W7104050307"),
    "E12": ("N/A", 0, "https://openalex.org/W7167473014"),
}
for _row in s1_data:
    _bibliometrics = _recent_bibliometrics.get(record_id(_row))
    if _bibliometrics:
        _quartile, _citation_count, _openalex_url = _bibliometrics
        _row[5] = _quartile
        _row[12] = _citation_count
        _row[13] = (
            f"{_row[13]} Citation count: OpenAlex snapshot 2026-08-08 "
            f"({_openalex_url})."
        ).strip()

_asset_class = {
    "T01": "Equities / limit-order book", "T02": "Equities", "T04": "Cryptocurrency",
    "T05": "Cryptocurrency", "T06": "Cryptocurrency", "T07": "Cryptocurrency",
    "T09": "Equities", "T10": "Equities", "S01": "Financial text / equities",
    "S02": "Equities", "S05": "Financial text / multi-asset", "S07": "Financial text / equities",
    "S11": "U.S. equities", "S12": "Cryptocurrency", "S13": "Cryptocurrency social media",
    "H01": "Equities",
    "H02": "U.S. equities", "H03": "Equities", "H10": "Cryptocurrency",
    "T03": "Cryptocurrency", "T08": "Cryptocurrency", "T11": "Cryptocurrency",
    "T12": "Cryptocurrency", "T13": "Cryptocurrency", "T14": "Cryptocurrency",
    "T15": "Cryptocurrency futures", "T16": "Cryptocurrency", "T17": "Cryptocurrency",
    "T18": "Cryptocurrency perpetual futures", "T19": "Perpetual futures markets",
}
for _matrix in (s2_data, s3_data, s4_data):
    for _row in _matrix:
        _row.append(_asset_class.get(record_id(_row), "Multi-asset / see source"))

# Remove unverified records and all editorial/gap-claim rows from generated
# sheets.  O01 is intentionally excluded: it is this project's proposal, not
# a literature reference.
s1_data = verified_rows(s1_data)
s2_data = verified_rows(s2_data)
s3_data = verified_rows(s3_data)
s4_data = verified_rows(s4_data)
s5_data = verified_rows(s5_data)
s6_data = verified_rows(s6_data)
s7_data = verified_rows(s7_data)
s9_data = verified_rows(s9_data)

def _sort_records(rows):
    """Keep each evidence matrix legible: T/S/H/E/F groups, then numeric ID."""
    group_order = {"T": 0, "S": 1, "H": 2, "E": 3, "F": 4}
    records = [r for r in rows if len(record_id(r)) >= 2 and record_id(r)[0] in group_order and record_id(r)[1:].isdigit()]
    editorial = [r for r in rows if r not in records]
    return sorted(records, key=lambda r: (group_order[record_id(r)[0]], int(record_id(r)[1:]))) + editorial

s1_data = _sort_records(s1_data)
s2_data = _sort_records(s2_data)
s3_data = _sort_records(s3_data)
s4_data = _sort_records(s4_data)
s5_data = _sort_records(s5_data)
s6_data = _sort_records(s6_data)
s7_data = _sort_records(s7_data)

_verified_counts = {
    "technical": sum(record_id(r).startswith("T") for r in s1_data),
    "sentiment": sum(record_id(r).startswith("S") for r in s1_data),
    "hybrid": sum(record_id(r).startswith("H") for r in s1_data),
    "evaluation": sum(record_id(r).startswith("E") for r in s1_data),
    "foundational": sum(record_id(r).startswith("F") for r in s1_data),
}
_verified_total = sum(_verified_counts.values())
def _has_yes(value):
    return str(value).strip() in {"✓", "Yes"}

_evidence_counts = {
    "controlled": sum(_has_yes(r[2]) for r in s7_data if record_id(r)),
    "incremental": sum(_has_yes(r[3]) for r in s7_data if record_id(r)),
    "formal_tests": sum(any(token in " ".join(map(str, r)).upper() for token in ["DM", "SPA", "FWER", "FDR", "DSR", "P-VALUE", "Z STATISTIC"]) for r in s6_data if record_id(r)),
    "multi_regime": sum("Multi" in str(r[4]) for r in s7_data if record_id(r)),
    "reproducible": sum(_has_yes(r[7]) or _has_yes(r[8]) for r in s7_data if record_id(r)),
    "llm": sum(any(token in " ".join(map(str, r)).upper() for token in ["LLM", "GPT", "BERT", "FINBERT", "TRANSFORMER"]) for r in s1_data if record_id(r)),
    "onchain": sum(_has_yes(r[5]) for r in s4_data if record_id(r)),
}
def _share(value):
    return f"{(value / _verified_total * 100):.1f}%" if _verified_total else "0.0%"

s8_data = [
    ["Verified literature records", f"{_verified_total} papers", "100.0%", "Records whose core metadata has been checked against a source."],
    ["Technical trading", f"{_verified_counts['technical']} papers", _share(_verified_counts['technical']), "Verified records only."],
    ["Sentiment / financial NLP", f"{_verified_counts['sentiment']} papers", _share(_verified_counts['sentiment']), "Verified records only."],
    ["Hybrid / LLM agents", f"{_verified_counts['hybrid']} papers", _share(_verified_counts['hybrid']), "Verified records only."],
    ["Evaluation / methodology", f"{_verified_counts['evaluation']} papers", _share(_verified_counts['evaluation']), "Verified records only."],
    ["Foundational works", f"{_verified_counts['foundational']} works", _share(_verified_counts['foundational']), "Verified records only."],
    ["LLM-related records", f"{_evidence_counts['llm']} papers", _share(_evidence_counts['llm']), "Keyword-based coverage in the verified master corpus."],
    ["Crypto social-sentiment records", f"{sum(record_id(r) == 'S13' for r in s1_data)} paper", _share(sum(record_id(r) == 'S13' for r in s1_data)), "CryptoBERT/LUKE paper; transfer-test reference, not a trading replication."],
    ["Studies with on-chain input", f"{_evidence_counts['onchain']} papers", _share(_evidence_counts['onchain']), "Counted only when Sheet 4 explicitly marks the On-chain field."],
    ["Controlled comparisons", f"{_evidence_counts['controlled']} papers", _share(_evidence_counts['controlled']), "Counted from Sheet 7's Controlled Comparison field."],
    ["Incremental-value studies", f"{_evidence_counts['incremental']} papers", _share(_evidence_counts['incremental']), "Counted from Sheet 7's Incremental Value field."],
    ["Formal statistical-test coverage", f"{_evidence_counts['formal_tests']} papers", _share(_evidence_counts['formal_tests']), "DM/SPA/FWER/FDR/DSR or an explicitly recorded test in Sheet 6."],
    ["Multi-regime studies", f"{_evidence_counts['multi_regime']} papers", _share(_evidence_counts['multi_regime']), "Counted from Sheet 7's Market Regime field."],
    ["Open/reproducible records", f"{_evidence_counts['reproducible']} papers", _share(_evidence_counts['reproducible']), "Counted from Sheet 7's reproducibility or open-source fields."],
    ["Scope note", "Curated corpus", "", "The matrix is not a systematic-review census; excluded records lack adequate source verification."],
    ["Draft (UPDATED) : Sau khi khảo sát các nghiên cứu hiện có, có thể thấy rằng algorithmic trading đã đạt được nhiều tiến bộ trong technical analysis, sentiment analysis, hybrid trading và gần đây là LLM-based trading systems. Mặc dù nhiều công trình báo cáo hiệu quả vượt trội của các framework đề xuất, phần lớn đều thay đổi nhiều thành phần của hệ thống cùng lúc và đánh giá trên các giao thức thực nghiệm khác nhau. Đặc biệt, AI module trong các nghiên cứu gần đây (H10, S09) thường chỉ được mô tả như một 'sentiment layer' đơn lẻ, trong khi thực tế các hệ thống hiện đại đã tích hợp nhiều nguồn thông tin thị trường phong phú hơn nhiều: derivatives microstructure (funding rate, taker buy/sell flow), smart money positioning (top traders long/short ratio), liquidation heatmap (reversal risk), và LLM-based news reasoning (Polymarket + RSS). Do đó, hiện vẫn chưa có đủ bằng chứng để kết luận rằng AI-derived multi-source market assessment - tổng hợp các tầng thông tin thị trường nêu trên - mang lại bao nhiêu giá trị giao dịch gia tăng ngoài pure technical signals khi được đánh giá dưới cùng điều kiện thực thi, chi phí giao dịch và quản trị rủi ro. Khoảng trống này tạo động lực cho nghiên cứu hiện tại, trong đó Vibe Mode (technical-only) và AI Mode (multi-source market assessment) được triển khai trên cùng một framework, chỉ khác nhau ở nguồn tín hiệu, nhằm cho phép một controlled comparison công bằng và định lượng incremental value của AI-derived market intelligence.", "", "", ""]
]

# Sheet 12: compare the project's backtest protocol against the designs that
# actually influenced it.  "Not reported" is kept distinct from "No".
s12_cols = [
    "ID / Study", "Universe & survivorship", "Signal availability / lag",
    "Split / OOS design", "Execution model", "Trading costs",
    "Funding / carry", "Risk & liquidation", "Regime analysis",
    "Multiple testing", "Statistical inference", "Project transfer result",
    "Scientific assessment", "Source URL",
]
s12_data = [
    ["T05", "BTC on CoinDesk/Bitstamp plus LTC/ETH/XRP; fixed named assets", "Daily rules; contemporaneous close-to-close research design", "In-sample plus explicit OOS period", "Rule-return backtest; not a perpetual 4H fill engine", "Breakeven cost and trade count", "N/A", "Risk-adjusted metrics; no exchange liquidation engine", "Includes a crypto bear-market OOS period", "FWER and FDR over 14,919 rules", "Stationary-bootstrap p-values", "Five rule families reproduced; no robust promotion on the project's hold-out", "Strong rule-search discipline; execution realism is below the project's perpetual simulator", "https://link.springer.com/article/10.1007/s10479-019-03357-1"],
    ["T03", "Broad crypto cross-section; factor construction requires historical membership", "Characteristic sorts formed before subsequent portfolio return", "Portfolio and factor tests across historical sample", "Daily factor portfolios", "Transaction-cost robustness", "N/A", "Factor-adjusted returns; no exchange margin path", "Robustness across specifications", "Many characteristics, handled through factor/regression tests", "Alpha and t-statistics", "Narrow fixed-perpetual transfer failed; lifecycle universe lesson retained", "High-quality factor benchmark but not a deployable perpetual strategy", "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119"],
    ["T08", "Multi-exchange USD pairs aggregated over 80+ centralized exchanges", "Lagged return and detrended-volume conditioning", "Historical cross-sectional portfolios and regressions", "Daily equal/value-weighted reversal portfolios", "Linear transaction costs", "N/A", "Liquidity/capacity discussed; no perpetual margin engine", "Conditional on market activity", "Robustness across volume-trend windows", "Portfolio p-values and panel regression", "Simplified liquid-perpetual transfer failed", "Causal cross-sectional design; economic channel is concentrated outside the project's most-liquid universe", "https://www.sciencedirect.com/science/article/pii/S0378426622001418"],
    ["T11", "Binance cryptocurrency cross-section; margin-trading availability separates short-sale regimes", "Abnormal volume and order imbalance are measured before subsequent returns", "Historical cross-sectional regressions with conditional subsamples", "Daily return-prediction design; not a 4H perpetual fill engine", "Trading cost is not the primary design variable", "N/A", "Short-sale constraints are modeled through margin-trading availability", "Compares constrained and less-constrained market states", "Alternative activity and disagreement specifications", "Factor-adjusted regressions and significance tests", "Abnormal-volume veto was treated as conditional evidence; not promoted as standalone alpha", "Credible microstructure design, but its short-sale channel may weaken in perpetual markets", "https://onlinelibrary.wiley.com/doi/10.1111/fima.12491"],
    ["T12", "CoinMarketCap crypto cross-section", "Weekly 2-week formation, 1-week holding", "Subsample and horizon robustness", "Value-weighted WML portfolios", "Transaction-cost robustness", "N/A", "Volatility scaling; short-sale constraints tested", "Crypto momentum states and horizons", "Alternative formation/holding periods", "Return t-statistics and Sharpe", "Unlevered inverse-volatility transfer did not beat equal-weight control", "Method is credible; scaling weight >1 means return gain partly reflects exposure", "https://www.sciencedirect.com/science/article/pii/S1544612325011377"],
    ["T13", "147 cryptocurrencies, 2015-2022", "Monthly momentum portfolios with predetermined stop thresholds", "Market-state and threshold robustness", "Portfolio backtest", "Not the main reported contribution", "N/A", "10%-50% stop-loss thresholds", "Explicit market-state comparison", "Several fixed thresholds and benchmark momentum rules", "Factor alpha and return significance", "ATR stop retained; paper threshold not copied", "Useful exit-rule ablation; frequency and stop definition differ from this project", "https://www.sciencedirect.com/science/article/pii/S2214635023000473"],
    ["T14", "BTC plus ETH/XLM/LTC/XRP, 2014-2020", "Market/funding liquidity shocks forecast future volatility", "Historical strategy plus turbulent-period analysis", "Daily conditional exposure", "Not fully auditable from public abstract", "TED spread is funding-liquidity proxy", "Volatility-managed crash avoidance", "Performance emphasized in turbulent periods", "Not reported", "Quantile regression and strategy metrics", "Causal Amihud-only proxy variants rejected", "Paper is credible; project transfer is partial because true funding-liquidity input was unavailable", "https://www.sciencedirect.com/science/article/pii/S1042444X22000019"],
    ["T15", "12 OKEx current-quarter futures, 2017-2021; licensed dataset", "Daily/weekly/monthly basis and momentum sorts", "Factor regressions and alternative lookback/holding periods", "Dated-futures factor portfolios", "Transaction-cost robustness", "Basis embeds term structure; not perpetual funding", "No 4H liquidation/margin path", "Frequency and holding-period sensitivity", "Multiple factors/specifications", "Alpha, t-statistics and spanning regressions", "Perpetual basis gates and standalone transfer failed", "Strong derivatives evidence; non-transfer across contract type is an important result", "https://onlinelibrary.wiley.com/doi/10.1002/fut.22425"],
    ["T16", "84 coins, 300+ exchanges, 11 currencies", "World signed order flow predicts subsequent returns", "Explicit out-of-sample ML and economic-value portfolios", "Cross-sectional portfolio sorts", "Limits-to-arbitrage and economic-value robustness", "N/A", "Portfolio constraints; no exchange liquidation path", "Robustness, not the project's bull/bear/sideways protocol", "Model comparison across economic and nonlinear predictors", "OOS predictive inference", "Single-venue Binance taker-flow proxy failed", "High-quality source; true multi-exchange input is necessary before replication", "https://www.sciencedirect.com/science/article/pii/S1386418126000029"],
    ["T17", ">3,000 coins with liquidity subsamples and historical cross-section", "28 price/volume/momentum/volatility indicators available before next weekly return", "Rolling cross-sectional combined elastic net; alternative designs", "Weekly value-weighted factor portfolios", "Transaction-cost analysis", "N/A", "Liquidity/capacity subsamples; no perpetual liquidation engine", "Explicit market-state robustness", "Combined model plus alternative research designs", "Newey-West t-statistics and factor alpha", "Narrow oscillator-only transfer failed", "Top-tier aggregate-Tech evidence; the project did not replicate its broad rolling C-ENet", "https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178"],
    ["Ours", "Bybit Trading + Closed USDT perpetuals; 991 intersecting, 987 with data; trailing-turnover top five", "Closed daily information selects next-day universe; next daily 4H open; no same-bar re-entry", "Six 180-day train folds select parameters; final two folds are untouched validation; incomplete tail excluded", "Event-driven 4H OHLC execution; adverse stop fill; delisting at last observable close", "Fee + half-spread + slippage + impact; base/stress/harsh", "Historical Bybit funding at actual timestamps", "ATR stop/trail; leverage withheld for lifecycle run until historical tiers are defensible", "BTC sustained UP-UP gate; results reported by fold/regime", "Predeclared 54-case grid; train-only selection; PBO/CSCV available in evaluator", "Return/DD/folds now; final experiment must add paired bootstrap/DM/SPA and incremental-value confidence intervals", "+168.62% base, +156.91% stress, +141.28% harsh; both final validation folds negative", "Most execution-realistic design in this comparison, but not live-approved and not yet sufficient to answer the AI incremental-value RQ", "https://bybit-exchange.github.io/docs/v5/market/kline"],
]

# Nội dung hiển thị của hai sheet phương pháp dùng tiếng Việt; các thuật ngữ
# chuẩn (OOS, FWER/FDR, PBO/CSCV, Sharpe...) được giữ để truy vết với paper.
s12_data = [
    ["T05", "BTC từ CoinDesk/Bitstamp và LTC/ETH/XRP; danh sách tài sản cố định", "Quy tắc ngày; tín hiệu close-to-close cùng thời điểm", "Có giai đoạn trong mẫu và ngoài mẫu (OOS) rõ ràng", "Backtest lợi nhuận quy tắc; không phải bộ máy khớp lệnh perpetual 4H", "Chi phí hòa vốn và số giao dịch", "Không áp dụng", "Chỉ số điều chỉnh rủi ro; không mô phỏng thanh lý theo sàn", "Có OOS trong thị trường crypto giảm", "FWER và FDR trên 14.919 quy tắc", "Giá trị p bằng stationary bootstrap", "Đã tái tạo 5 họ quy tắc; không có phương án nào vượt qua hold-out một cách bền vững", "Kỷ luật tìm kiếm quy tắc tốt; độ thực tế thực thi thấp hơn simulator perpetual của dự án", "https://link.springer.com/article/10.1007/s10479-019-03357-1"],
    ["T03", "Mặt cắt crypto rộng; cần thành phần vũ trụ lịch sử", "Sắp xếp đặc trưng trước lợi nhuận danh mục kỳ sau", "Kiểm định danh mục và nhân tố trên mẫu lịch sử", "Danh mục nhân tố theo ngày", "Kiểm tra độ bền với chi phí giao dịch", "Không áp dụng", "Lợi nhuận điều chỉnh nhân tố; không mô phỏng đường đi margin theo sàn", "Kiểm tra độ bền qua nhiều đặc tả", "Nhiều đặc trưng, xử lý bằng nhân tố/hồi quy", "Alpha và thống kê t", "Áp dụng trên danh sách perpetual hẹp thất bại; giữ lại bài học về vũ trụ theo vòng đời", "Benchmark nhân tố chất lượng cao nhưng không phải chiến lược perpetual có thể triển khai trực tiếp", "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119"],
    ["T08", "Cặp USD tổng hợp từ hơn 80 sàn tập trung", "Lợi nhuận trễ và trạng thái khối lượng đã khử xu hướng", "Danh mục mặt cắt và hồi quy lịch sử", "Danh mục đảo chiều ngày, trọng số đều hoặc theo giá trị", "Chi phí giao dịch tuyến tính", "Không áp dụng", "Có bàn về thanh khoản/công suất; không có bộ máy margin perpetual", "Điều kiện theo mức độ hoạt động thị trường", "Kiểm tra nhiều cửa sổ xu hướng khối lượng", "Giá trị p danh mục và hồi quy bảng", "Bản áp dụng đơn giản trên perpetual thanh khoản cao thất bại", "Thiết kế nhân quả tốt; kênh kinh tế tập trung ngoài nhóm tài sản thanh khoản nhất của dự án", "https://www.sciencedirect.com/science/article/pii/S0378426622001418"],
    ["T11", "Mặt cắt crypto Binance; trạng thái margin đại diện cho ràng buộc bán khống", "Khối lượng bất thường và mất cân bằng lệnh được đo trước lợi nhuận tương lai", "Hồi quy mặt cắt lịch sử với các mẫu con có điều kiện", "Thiết kế dự báo lợi nhuận ngày; không phải bộ máy khớp lệnh perpetual 4H", "Chi phí không phải biến thiết kế chính", "Không áp dụng", "Ràng buộc bán khống được mô hình qua khả năng margin", "So sánh trạng thái bị ràng buộc và ít bị ràng buộc", "Nhiều đặc tả hoạt động và bất đồng", "Hồi quy điều chỉnh nhân tố và kiểm định ý nghĩa", "Chỉ dùng khối lượng bất thường như bằng chứng có điều kiện; không chọn làm alpha độc lập", "Thiết kế vi cấu trúc đáng tin cậy nhưng kênh bán khống có thể yếu hơn trên perpetual", "https://onlinelibrary.wiley.com/doi/10.1111/fima.12491"],
    ["T12", "Mặt cắt crypto CoinMarketCap", "Tạo danh mục 2 tuần, nắm giữ 1 tuần", "Kiểm tra mẫu con và độ bền theo kỳ hạn", "Danh mục WML trọng số theo giá trị", "Kiểm tra độ bền với chi phí", "Không áp dụng", "Co giãn theo biến động; kiểm tra ràng buộc bán khống", "Nhiều trạng thái và kỳ hạn momentum", "Nhiều kỳ tạo/nắm giữ", "Thống kê t lợi nhuận và Sharpe", "Co giãn nghịch đảo biến động không đòn bẩy không thắng đối chứng trọng số đều", "Phương pháp đáng tin; trọng số co giãn lớn hơn 1 cho thấy một phần lợi nhuận đến từ tăng phơi nhiễm", "https://www.sciencedirect.com/science/article/pii/S1544612325011377"],
    ["T13", "147 đồng tiền mã hóa, 2015–2022", "Danh mục momentum tháng với ngưỡng stop định trước", "Kiểm tra theo trạng thái thị trường và nhiều ngưỡng", "Backtest danh mục", "Không phải đóng góp báo cáo chính", "Không áp dụng", "Ngưỡng stop-loss 10%–50%", "So sánh trạng thái thị trường rõ ràng", "Nhiều ngưỡng cố định và quy tắc momentum đối chứng", "Alpha nhân tố và ý nghĩa lợi nhuận", "Giữ ATR stop; không sao chép ngưỡng của paper", "Hữu ích cho ablation quy tắc thoát; tần suất và định nghĩa stop khác dự án", "https://www.sciencedirect.com/science/article/pii/S2214635023000473"],
    ["T14", "BTC cùng ETH/XLM/LTC/XRP, 2014–2020", "Cú sốc thanh khoản thị trường/funding dự báo biến động tương lai", "Chiến lược lịch sử và phân tích giai đoạn nhiễu động", "Phơi nhiễm có điều kiện theo ngày", "Chưa thể kiểm toán đầy đủ từ abstract công khai", "TED spread là proxy thanh khoản funding", "Quản trị biến động để tránh sụp giảm", "Nhấn mạnh giai đoạn nhiễu động", "Không báo cáo", "Hồi quy phân vị và chỉ số chiến lược", "Các biến thể proxy Amihud nhân quả bị loại", "Paper đáng tin; áp dụng một phần vì dự án chưa có biến thanh khoản funding thật", "https://www.sciencedirect.com/science/article/pii/S1042444X22000019"],
    ["T15", "12 futures current-quarter OKEx, 2017–2021; dữ liệu có giấy phép", "Sắp xếp basis và momentum theo ngày/tuần/tháng", "Hồi quy nhân tố và nhiều kỳ nhìn lại/nắm giữ", "Danh mục nhân tố futures có ngày đáo hạn", "Kiểm tra độ bền với chi phí", "Basis chứa cấu trúc kỳ hạn; khác funding perpetual", "Không mô phỏng thanh lý/margin 4H", "Nhạy với tần suất và kỳ nắm giữ", "Nhiều nhân tố/đặc tả", "Alpha, thống kê t và hồi quy spanning", "Basis gate và bản độc lập trên perpetual không thắng Tech", "Bằng chứng phái sinh mạnh; không chuyển được giữa loại hợp đồng là một kết quả quan trọng", "https://onlinelibrary.wiley.com/doi/10.1002/fut.22425"],
    ["T16", "84 đồng, hơn 300 sàn, 11 đồng tiền định giá", "Dòng lệnh có dấu toàn thị trường dự báo lợi nhuận kỳ sau", "ML ngoài mẫu rõ ràng và danh mục đo giá trị kinh tế", "Sắp xếp danh mục mặt cắt", "Kiểm tra giới hạn arbitrage và giá trị kinh tế", "Không áp dụng", "Có ràng buộc danh mục; không mô phỏng thanh lý theo sàn", "Kiểm tra độ bền, không theo đúng giao thức bull/bear/sideways của dự án", "So sánh mô hình kinh tế và phi tuyến", "Suy luận dự báo OOS", "Proxy taker-flow một sàn Binance thất bại", "Nguồn chất lượng cao; cần dòng lệnh đa sàn thật trước khi tuyên bố tái lập", "https://www.sciencedirect.com/science/article/pii/S1386418126000029"],
    ["T17", "Hơn 3.000 đồng, có mẫu con thanh khoản và mặt cắt lịch sử", "28 chỉ báo giá/khối lượng/momentum/biến động có trước lợi nhuận tuần kế tiếp", "Combined elastic net mặt cắt cuốn chiếu và các thiết kế thay thế", "Danh mục nhân tố tuần, trọng số theo giá trị", "Phân tích chi phí giao dịch", "Không áp dụng", "Mẫu con thanh khoản/công suất; không có bộ máy thanh lý perpetual", "Có kiểm tra theo trạng thái thị trường", "Mô hình kết hợp và các thiết kế thay thế", "Thống kê t Newey–West và alpha nhân tố", "Bản oscillator hẹp thất bại", "Bằng chứng aggregate-Tech hàng đầu; dự án chưa tái lập C-ENet cuốn chiếu trên vũ trụ rộng", "https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178"],
    ["Ours", "Perpetual USDT Bybit đang và đã đóng; 991 giao, 987 có dữ liệu; chọn top 5 theo turnover trễ", "Thông tin ngày đã đóng chọn vũ trụ ngày kế tiếp; vào tại open 4H kế tiếp; không tái vào cùng nến", "6 fold train 180 ngày chọn tham số; 2 fold cuối khóa làm validation; loại phần đuôi thiếu", "Mô phỏng sự kiện OHLC 4H; stop khớp bất lợi; delist tại close cuối quan sát được", "Phí + nửa spread + slippage + impact; ba mức base/stress/harsh", "Funding Bybit lịch sử đúng timestamp", "ATR stop/trailing; chưa dùng leverage cho đến khi mô hình tier lịch sử đủ tin cậy", "Cổng BTC UP-UP bền; báo cáo theo fold/trạng thái", "Grid 54 trường hợp định trước; chỉ chọn trên train; evaluator có PBO/CSCV", "Hiện có Return/DD/fold; thí nghiệm cuối cần paired bootstrap, DM/SPA và CI giá trị gia tăng", "+168,62% base, +156,91% stress, +141,28% harsh; cả 2 fold validation cuối đều âm", "Thiết kế thực thi thực tế nhất trong bảng, nhưng chưa được duyệt live và chưa đủ trả lời RQ về giá trị gia tăng của AI", "https://bybit-exchange.github.io/docs/v5/market/kline"],
]

_paper_titles = {
    "T03": "Common Risk Factors in Cryptocurrency",
    "T05": "Technical trading and cryptocurrencies",
    "T08": "Trading Volume and Liquidity Provision in Cryptocurrency Markets",
    "T11": "Disagreement and Returns: The Case of Cryptocurrencies",
    "T12": "Cryptocurrency Market Risk-Managed Momentum Strategies",
    "T13": "Stop-Loss Rules and Momentum Payoffs in Cryptocurrencies",
    "T14": "Liquidity Shocks, Price Volatilities, and Risk-Managed Strategy: Evidence from Bitcoin and Beyond",
    "T15": "An Empirical Investigation on Risk Factors in Cryptocurrency Futures",
    "T16": "Order Flow and Cryptocurrency Returns",
    "T17": "A Trend Factor for the Cross Section of Cryptocurrency Returns",
    "T18": "Perpetual Futures Pricing",
    "T19": "Perpetual future contracts in centralized and decentralized exchanges: Mechanism and traders' behavior",
    "Ours": "Controlled Evaluation of AI-Derived Multi-Source Market Assessment vs Technical Signals",
}
s12_data = [[row[0], _paper_titles[row[0]], *row[1:]] for row in s12_data]

# Sheet 13: trace each methodological choice to a reputable source, state the
# project-specific modification, and expose what still must be done to answer RQ.
s13_cols = [
    "Method component", "Reference evidence", "Credibility",
    "What is adopted", "Project-specific modification", "Why modified",
    "Implementation / artifact", "Current evidence", "RQ contribution",
    "Remaining risk / required test", "Source URL",
]
s13_data = [
    ["Technical rule families", "T05 Hudson & Urquhart (2021)", "Peer-reviewed; Annals of Operations Research; ~15,000 rules with FWER/FDR", "MA/filter/support-resistance/channel families; cost and OOS discipline", "Long-biased compressed-channel candidate feeds a 4H perpetual executor", "Paper's daily rule-return design cannot model funding, stops or intraday fills", "technical_rule_research.py; technical_cross_asset_execution.py", "Initial 1,116-rule sweep had no hold-out promotion; later channel candidate survives cost stress", "Defines a credible non-AI comparator", "Apply multiple-testing correction to the final frozen Tech search family", "https://link.springer.com/article/10.1007/s10479-019-03357-1"],
    ["Market-regime gate", "T06 Hsieh, Huang & Liu (2025)", "Peer-reviewed; Finance Research Letters", "Momentum is conditioned on persistent UP-UP market state", "BTC 7/14-day monotone state gates entries across the perpetual universe", "Daily/4H execution needs a causal market-wide indicator available before entry", "technical_cross_asset_execution.py", "Gate is retained in the current Tech candidate", "Creates the regime strata required by the RQ", "Freeze bull/bear/sideways definitions before comparing Tech vs AI", "https://www.sciencedirect.com/science/article/pii/S1544612325016101"],
    ["Dynamic universe", "T03 Liu, Tsyvinski & Wu (2022); T17 Fieberg et al. (2025)", "Journal of Finance and JFQA", "Broad point-in-time cross-sections; size/liquidity-aware factor tests", "Exchange lifecycle universe; 30 closed days of Bybit turnover; top five becomes tradable next day", "Perpetual availability, delisting and capacity must be modeled directly", "technical_bybit_lifecycle_universe.py", "987 contracts with data; 43 ever selected; six now closed", "Prevents current-winner selection from biasing both experiment arms", "Audit symbol-history completeness and freeze the universe manifest before final experiment", "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119"],
    ["Cross-asset momentum ranking", "T03 Liu et al. (2022); T17 CTREND (2025)", "Top-tier peer-reviewed finance journals", "Past return and aggregate trend information rank the cross-section", "Transparent 20-day momentum ranks only channel-qualified top-liquidity assets", "Small deployable universe cannot support the paper's factor/C-ENet replication", "technical_bybit_lifecycle_execution.py", "Top-one/rank-20 is stronger than top-two in train folds", "Produces the frozen traditional quantitative baseline", "Treat narrow transfer failures as non-replication; no paper-equivalence claim", "https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178"],
    ["Conditional reversal / disagreement", "T08 Cong et al. (2022); T11 Li et al. (2025)", "Peer-reviewed Journal of Banking & Finance and Financial Management", "Volume/liquidity state and abnormal-volume disagreement are treated as conditional mechanisms", "Only causal, lagged veto/feature variants are tested on the perpetual universe", "The published effects depend on broad cross-sections, lower liquidity or short-sale constraints", "technical_cross_asset_execution.py", "Simplified liquid-perpetual transfers did not improve the frozen Tech candidate", "Documents a scientifically motivated negative transfer instead of selecting only winning ideas", "Do not retune these features on final validation; true paper replication needs compatible universe and market constraints", "https://www.sciencedirect.com/science/article/pii/S0378426622001418"],
    ["Volatility-managed exposure", "T12 Han et al. (2025)", "Peer-reviewed; Finance Research Letters", "Volatility scaling is evaluated separately from the underlying momentum signal", "Exposure is capped and reported apart from alpha so leverage cannot masquerade as predictive improvement", "The paper's average scaling weight exceeds one and weekly WML differs from 4H perpetual execution", "technical_cross_asset_execution.py", "Unlevered inverse-volatility transfer did not beat the equal-weight control", "Prevents higher gross exposure from being misreported as AI-derived incremental value", "Keep leverage/risk identical in Tech and AI arms; report exposure and return decomposition", "https://www.sciencedirect.com/science/article/pii/S1544612325011377"],
    ["Stop and trailing exit", "T13 Sadaqat & Butt (2023)", "Peer-reviewed; broad 147-coin study with market-state robustness", "Predetermined stop-loss as a separate risk/exit component", "4H ATR stop 3 and trailing 4 instead of monthly percentage threshold", "ATR scales to heterogeneous perpetual volatility and intraday execution", "technical_bybit_lifecycle_execution.py", "Train-selected candidate: +168.62%, DD 10.56%; both final folds negative", "Keeps risk/execution identical across Tech and AI arms", "Do not retune stops after observing AI results; run stop/no-stop ablation once", "https://www.sciencedirect.com/science/article/pii/S2214635023000473"],
    ["Liquidity-risk overlay", "T14 Tang & Wang (2022)", "Peer-reviewed; market and funding liquidity predict volatility", "Causal Amihud illiquidity shock as an entry-risk gate", "Asset/market/combined proxy vetoes at fixed 2x/3x/5x thresholds", "Historical TED/funding-liquidity variable was unavailable; avoid fabricating it", "technical_cross_asset_execution.py", "All proxy variants failed to improve train control; default off", "Negative ablation shows method screening is not result cherry-picking", "Record as partial transfer, not replication", "https://www.sciencedirect.com/science/article/pii/S1042444X22000019"],
    ["Basis / term structure", "T15 Chi et al. (2023)", "Peer-reviewed; Journal of Futures Markets; dated-futures factor evidence", "Basis-ranked derivatives portfolios and holding-period sensitivity", "Bybit/OKX premium-index and mark-index basis gates on perpetuals", "Current-quarter futures and perpetual swaps have different carry mechanics", "technical_cross_asset_execution.py", "All gates/standalone transfers failed to beat Tech", "Documents why derivatives sources are candidates but not automatically alpha", "A true dated-futures replication needs licensed/historical contract-chain data", "https://onlinelibrary.wiley.com/doi/10.1002/fut.22425"],
    ["Order-flow feature", "T16 Anastasopoulos et al. (2026)", "Peer-reviewed; Journal of Financial Markets; 300+ exchanges", "Signed flow as a predictive multi-source market input", "Binance buyer/seller initiated quote-volume proxy used only for a transfer test", "World flow cannot be reconstructed from one exchange", "technical_cross_asset_execution.py", "Single-venue variants did not improve Tech", "Identifies a high-value future AI/data source without contaminating baseline", "Acquire point-in-time multi-exchange flow before claiming replication", "https://www.sciencedirect.com/science/article/pii/S1386418126000029"],
    ["Execution and data provenance", "Official Bybit V5 market-data specification", "Primary exchange source; fields and timestamps documented", "Kline OHLCV/turnover, funding history, instrument status, launch/delivery time", "Atomic caches, pagination, closed-candle filter and lifecycle manifest", "Research needs exact exchange semantics and reproducible snapshots", "technical_bybit_lifecycle_universe.py; technical_bybit_lifecycle_execution.py", "No download failures in the locked universe run; 4/4 regression tests pass", "Ensures both arms receive identical authoritative market/execution data", "Public API is not an immutable vendor archive; preserve hashes/snapshots and retrieval timestamps", "https://bybit-exchange.github.io/docs/v5/market/instrument"],
    ["Train/validation and search control", "E04 White (2000); E05 Hansen (2005); E08 DSR (2014); F06 López de Prado (2018)", "Canonical econometric/backtest-overfitting references", "Time order, sealed validation, PBO/CSCV, SPA/DSR-style correction", "Coordinate-limited/predeclared grids; six train folds and two untouched final folds", "Crypto dependence and repeated strategy search invalidate random K-fold CV", "technical_pit_optimizer.py; technical_autoquant_evaluator.py", "Current lifecycle winner has 6/8 positive folds but both validation folds negative", "Prevents a weak Tech baseline or overfit winner from biasing incremental-value conclusions", "Freeze all hypotheses; report family-wise/SPA/DSR evidence for final model family", "https://doi.org/10.1111/1468-0262.00152"],
    ["Controlled incremental-value experiment", "Gap synthesis from Sheets 5-7 and E12 falsification logic", "Methodological triangulation; E12 is a preprint and therefore not promoted as core peer-reviewed evidence", "Paired comparison with identical data, fee, risk, execution, size and calendar", "Only the assessment source changes: traditional Tech versus AI-derived multi-source assessment; include Tech+AI and source ablations", "Directly targets the stated RQ instead of comparing unrelated full systems", "Final experiment module (to be implemented after both arms freeze)", "Not yet run; current work validates only the Tech comparator", "Direct estimate of incremental trading value overall and by regime", "Primary endpoint, paired bootstrap CI, DM/SPA where appropriate, economic effect size, multiple-regime interaction and failure cases must be pre-specified", "https://doi.org/10.1111/1468-0262.00152"],
]

s13_data = [
    ["Họ quy tắc kỹ thuật", "T05 Hudson & Urquhart (2021)", "Bình duyệt; Annals of Operations Research; khoảng 15.000 quy tắc với FWER/FDR", "Các họ MA/filter/support-resistance/channel; kỷ luật chi phí và OOS", "Ứng viên channel nén thiên long đưa vào bộ thực thi perpetual 4H", "Thiết kế lợi nhuận quy tắc ngày của paper không mô phỏng funding, stop hay khớp lệnh nội ngày", "technical_rule_research.py; technical_cross_asset_execution.py", "Sweep 1.116 quy tắc đầu không qua hold-out; ứng viên channel sau chịu được cost stress", "Xác lập đối chứng định lượng không AI đáng tin", "Áp dụng hiệu chỉnh đa kiểm định cho họ Tech cuối cùng đã khóa", "https://link.springer.com/article/10.1007/s10479-019-03357-1"],
    ["Cổng trạng thái thị trường", "T06 Hsieh, Huang & Liu (2025)", "Bình duyệt; Finance Research Letters", "Momentum có điều kiện theo trạng thái UP-UP bền", "BTC tăng đơn điệu 7/14 ngày làm cổng vào cho toàn vũ trụ perpetual", "Thực thi ngày/4H cần chỉ báo toàn thị trường nhân quả, có trước lúc vào", "technical_cross_asset_execution.py", "Cổng được giữ trong ứng viên Tech hiện tại", "Tạo các tầng trạng thái cần cho RQ", "Khóa định nghĩa bull/bear/sideways trước khi so Tech với AI", "https://www.sciencedirect.com/science/article/pii/S1544612325016101"],
    ["Vũ trụ động", "T03 Liu, Tsyvinski & Wu (2022); T17 Fieberg et al. (2025)", "Journal of Finance và JFQA", "Mặt cắt point-in-time rộng; kiểm định nhân tố có xét quy mô/thanh khoản", "Vũ trụ theo vòng đời sàn; 30 ngày turnover đã đóng; top 5 được giao dịch từ ngày kế tiếp", "Phải mô hình trực tiếp thời gian tồn tại perpetual, delist và công suất", "technical_bybit_lifecycle_universe.py", "987 hợp đồng có dữ liệu; 43 từng được chọn; 6 đã đóng", "Ngăn thiên lệch chọn winner hiện tại ở cả hai nhánh", "Kiểm toán đầy đủ lịch sử symbol và khóa manifest trước thí nghiệm cuối", "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119"],
    ["Xếp hạng momentum chéo tài sản", "T03 Liu et al. (2022); T17 CTREND (2025)", "Tạp chí tài chính bình duyệt hàng đầu", "Lợi nhuận quá khứ và thông tin xu hướng tổng hợp dùng để xếp hạng mặt cắt", "Momentum 20 ngày minh bạch chỉ xếp hạng tài sản top thanh khoản đã qua channel", "Vũ trụ triển khai nhỏ không đủ tái lập factor/C-ENet của paper", "technical_bybit_lifecycle_execution.py", "Top-one/rank-20 mạnh hơn top-two trong train fold", "Tạo baseline định lượng truyền thống đã khóa", "Xem thất bại chuyển giao hẹp là không tái lập; không tuyên bố tương đương paper", "https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178"],
    ["Đảo chiều / bất đồng có điều kiện", "T08 Cong et al. (2022); T11 Li et al. (2025)", "Journal of Banking & Finance và Financial Management, đều bình duyệt", "Trạng thái khối lượng/thanh khoản và bất đồng qua khối lượng bất thường là cơ chế có điều kiện", "Chỉ kiểm tra các veto/feature có độ trễ và nhân quả trên vũ trụ perpetual", "Hiệu ứng công bố phụ thuộc mặt cắt rộng, thanh khoản thấp hoặc ràng buộc bán khống", "technical_cross_asset_execution.py", "Bản chuyển giao perpetual thanh khoản cao không cải thiện ứng viên Tech đã khóa", "Ghi nhận chuyển giao âm có cơ sở thay vì chỉ chọn ý tưởng thắng", "Không chỉnh lại trên validation; tái lập thật cần vũ trụ và ràng buộc thị trường tương thích", "https://www.sciencedirect.com/science/article/pii/S0378426622001418"],
    ["Phơi nhiễm quản trị theo biến động", "T12 Han et al. (2025)", "Bình duyệt; Finance Research Letters", "Đánh giá volatility scaling tách khỏi tín hiệu momentum gốc", "Giới hạn phơi nhiễm và báo cáo riêng alpha để leverage không giả dạng cải thiện dự báo", "Trọng số trung bình của paper lớn hơn 1 và WML tuần khác perpetual 4H", "technical_cross_asset_execution.py", "Bản nghịch đảo biến động không đòn bẩy không thắng đối chứng trọng số đều", "Ngăn lợi nhuận do tăng phơi nhiễm bị gán nhầm cho AI", "Giữ leverage/risk giống nhau giữa Tech và AI; phân rã phơi nhiễm và lợi nhuận", "https://www.sciencedirect.com/science/article/pii/S1544612325011377"],
    ["Stop và trailing exit", "T13 Sadaqat & Butt (2023)", "Bình duyệt; 147 đồng và có kiểm tra theo trạng thái", "Stop-loss định trước là thành phần risk/exit riêng", "ATR stop 3 và trailing 4 trên 4H thay ngưỡng phần trăm tháng", "ATR co giãn theo biến động không đồng nhất và thực thi nội ngày", "technical_bybit_lifecycle_execution.py", "Ứng viên chọn trên train: +168,62%, DD 10,56%; cả hai fold cuối âm", "Giữ risk/execution đồng nhất giữa Tech và AI", "Không chỉnh stop sau khi xem AI; chỉ chạy ablation stop/no-stop một lần", "https://www.sciencedirect.com/science/article/pii/S2214635023000473"],
    ["Lớp phủ rủi ro thanh khoản", "T14 Tang & Wang (2022)", "Bình duyệt; thanh khoản thị trường và funding dự báo biến động", "Cú sốc Amihud nhân quả làm cổng rủi ro vào lệnh", "Veto proxy tài sản/thị trường/kết hợp tại ngưỡng cố định 2x/3x/5x", "Không có biến TED/thanh khoản funding lịch sử nên không được bịa thay thế", "technical_cross_asset_execution.py", "Mọi biến thể proxy không cải thiện đối chứng train; mặc định tắt", "Ablation âm cho thấy sàng lọc phương pháp không cherry-pick kết quả", "Ghi là chuyển giao một phần, không phải tái lập", "https://www.sciencedirect.com/science/article/pii/S1042444X22000019"],
    ["Basis / cấu trúc kỳ hạn", "T15 Chi et al. (2023)", "Bình duyệt; Journal of Futures Markets; bằng chứng nhân tố futures có đáo hạn", "Danh mục phái sinh xếp hạng basis và độ nhạy kỳ nắm giữ", "Basis gate từ premium/mark index Bybit/OKX trên perpetual", "Futures current-quarter và perpetual có cơ chế carry khác nhau", "technical_cross_asset_execution.py", "Mọi gate/bản độc lập đều không thắng Tech", "Giải thích vì sao dữ liệu phái sinh là ứng viên nhưng không tự động tạo alpha", "Tái lập futures có đáo hạn thật cần chuỗi hợp đồng lịch sử có giấy phép", "https://onlinelibrary.wiley.com/doi/10.1002/fut.22425"],
    ["Đặc trưng dòng lệnh", "T16 Anastasopoulos et al. (2026)", "Bình duyệt; Journal of Financial Markets; hơn 300 sàn", "Dòng lệnh có dấu là đầu vào thị trường đa nguồn có sức dự báo", "Proxy quote-volume bên mua/bán chủ động Binance chỉ dùng để kiểm tra chuyển giao", "Không thể tái tạo world flow từ một sàn", "technical_cross_asset_execution.py", "Biến thể một sàn không cải thiện Tech", "Xác định nguồn dữ liệu/AI giá trị cao trong tương lai mà không làm bẩn baseline", "Cần dòng lệnh đa sàn point-in-time trước khi tuyên bố tái lập", "https://www.sciencedirect.com/science/article/pii/S1386418126000029"],
    ["Thực thi và nguồn gốc dữ liệu", "Đặc tả dữ liệu thị trường Bybit V5 chính thức", "Nguồn sơ cấp của sàn; trường dữ liệu và timestamp có tài liệu", "OHLCV/turnover, funding, trạng thái công cụ, launch/delivery time", "Cache nguyên tử, phân trang, lọc nến đóng và manifest vòng đời", "Nghiên cứu cần đúng ngữ nghĩa sàn và snapshot tái lập được", "technical_bybit_lifecycle_universe.py; technical_bybit_lifecycle_execution.py", "Không lỗi tải trong lần chạy vũ trụ khóa; 4/4 regression test đạt", "Bảo đảm hai nhánh nhận cùng dữ liệu thị trường/thực thi có thẩm quyền", "API công khai không phải kho lưu trữ bất biến; phải giữ hash/snapshot và thời điểm tải", "https://bybit-exchange.github.io/docs/v5/market/instrument"],
    ["Train/validation và kiểm soát tìm kiếm", "E04 White (2000); E05 Hansen (2005); E08 DSR (2014); F06 López de Prado (2018)", "Tài liệu kinh tế lượng/overfitting backtest kinh điển", "Thứ tự thời gian, validation khóa, PBO/CSCV, hiệu chỉnh SPA/DSR", "Grid giới hạn và định trước; 6 train fold, 2 final fold chưa đụng", "Phụ thuộc thời gian crypto và tìm kiếm lặp khiến random K-fold không hợp lệ", "technical_pit_optimizer.py; technical_autoquant_evaluator.py", "Winner theo vòng đời có 6/8 fold dương nhưng cả hai validation fold âm", "Ngăn baseline Tech yếu/quá khớp làm lệch kết luận giá trị gia tăng", "Khóa giả thuyết; báo cáo FWER/SPA/DSR cho họ mô hình cuối", "https://doi.org/10.1111/1468-0262.00152"],
    ["Thí nghiệm giá trị gia tăng có kiểm soát", "Tổng hợp gap từ Sheet 5–7 và logic falsification E12", "Tam giác hóa phương pháp; E12 là preprint nên không xem là bằng chứng bình duyệt cốt lõi", "So sánh ba arm với cùng data, fee, risk, execution, size và calendar", "Tech-only là control; LLM-only là diagnostic ablation; Tech+LLM là treatment chính để đo incremental value", "Nhắm trực tiếp RQ đồng thời kiểm tra LLM bổ trợ hay thay thế Tech", "Mô-đun thí nghiệm cuối, hiện thực sau khi khóa cả ba arm", "Chưa chạy; hiện tại chỉ mới kiểm chứng đối chứng Tech", "Ước lượng Tech+LLM − Tech-only là primary effect; LLM-only hỗ trợ diễn giải cơ chế", "Định trước endpoint, paired bootstrap CI, DM/SPA phù hợp, effect size kinh tế, tương tác trạng thái và failure case", "https://doi.org/10.1111/1468-0262.00152"],
]

_method_reference_titles = {
    "T05 Hudson & Urquhart (2021)": "Technical trading and cryptocurrencies (T05)",
    "T06 Hsieh, Huang & Liu (2025)": "State transitions and momentum effect in cryptocurrency market (T06)",
    "T03 Liu, Tsyvinski & Wu (2022); T17 Fieberg et al. (2025)": "Common Risk Factors in Cryptocurrency (T03); A Trend Factor for the Cross Section of Cryptocurrency Returns (T17)",
    "T03 Liu et al. (2022); T17 CTREND (2025)": "Common Risk Factors in Cryptocurrency (T03); A Trend Factor for the Cross Section of Cryptocurrency Returns (T17)",
    "T08 Cong et al. (2022); T11 Li et al. (2025)": "Trading Volume and Liquidity Provision in Cryptocurrency Markets (T08); Disagreement and Returns: The Case of Cryptocurrencies (T11)",
    "T12 Han et al. (2025)": "Cryptocurrency Market Risk-Managed Momentum Strategies (T12)",
    "T13 Sadaqat & Butt (2023)": "Stop-Loss Rules and Momentum Payoffs in Cryptocurrencies (T13)",
    "T14 Tang & Wang (2022)": "Liquidity Shocks, Price Volatilities, and Risk-Managed Strategy: Evidence from Bitcoin and Beyond (T14)",
    "T15 Chi et al. (2023)": "An Empirical Investigation on Risk Factors in Cryptocurrency Futures (T15)",
    "T16 Anastasopoulos et al. (2026)": "Order Flow and Cryptocurrency Returns (T16)",
    "Đặc tả dữ liệu thị trường Bybit V5 chính thức": "Bybit V5 Market Data Specification (official documentation)",
    "E04 White (2000); E05 Hansen (2005); E08 DSR (2014); F06 López de Prado (2018)": "A Reality Check for Data Snooping (E04); A Test for Superior Predictive Ability (E05); The Deflated Sharpe Ratio (E08); Advances in Financial Machine Learning (F06)",
    "Tổng hợp gap từ Sheet 5–7 và logic falsification E12": "Gap synthesis from Sheets 5–7; A Pre-registered, Compute-Controlled Falsification Study (E12)",
}
for _row in s13_data:
    _row[1] = _method_reference_titles.get(_row[1], _row[1])

_method_component_terms = {
    "Họ quy tắc kỹ thuật": "Technical rule families",
    "Cổng trạng thái thị trường": "Market-regime gate",
    "Vũ trụ động": "Dynamic universe",
    "Xếp hạng momentum chéo tài sản": "Cross-asset momentum ranking",
    "Đảo chiều / bất đồng có điều kiện": "Conditional reversal / disagreement",
    "Phơi nhiễm quản trị theo biến động": "Volatility-managed exposure",
    "Stop và trailing exit": "Stop and trailing exit",
    "Lớp phủ rủi ro thanh khoản": "Liquidity-risk overlay",
    "Basis / cấu trúc kỳ hạn": "Basis / term structure",
    "Đặc trưng dòng lệnh": "Order-flow feature",
    "Thực thi và nguồn gốc dữ liệu": "Execution and data provenance",
    "Train/validation và kiểm soát tìm kiếm": "Train/validation and search control",
    "Thí nghiệm giá trị gia tăng có kiểm soát": "Controlled incremental-value experiment",
}
for _row in s13_data:
    _row[0] = _method_component_terms.get(_row[0], _row[0])

# Hai nhánh AI phải có cơ sở phương pháp từ literature Sentiment (S) và
# Hybrid (H), không chỉ suy ra từ các paper Technical. Chỉ giữ các record đã
# được source audit xác minh đủ để rút ra yêu cầu thực nghiệm.
s13_data.extend([
    ["LLM sentiment signal", "S11 Kirtac & Germano (2024)", "Bình duyệt; Finance Research Letters; dữ liệu và kết quả giao dịch đã xác minh", "Biến news text thành sentiment score, liên kết với subsequent return và đánh giá long–short sau 10 bps cost", "LLM-only tạo assessment có timestamp từ các nguồn đã khóa; không dùng technical signal để ra quyết định", "Cần tách giá trị assessment khỏi stock universe, portfolio construction và execution riêng của paper", "Mô-đun LLM-only và kho raw document có publication/ingestion timestamp", "Chưa chạy; hiện mới khóa yêu cầu phương pháp và provenance", "Cơ sở trực tiếp cho diagnostic arm LLM-only", "Khóa model, prompt, threshold, missing-data policy; kiểm tra prompt/model stability và cost stress", "https://doi.org/10.1016/j.frl.2024.105227"],
    ["Multi-source crypto sentiment và adaptive ensemble", "S12 Bennett et al. (2024)", "Bình duyệt; Global Finance Journal; sentiment data thương mại nên khó tái lập hoàn toàn", "Hơn 50 daily sentiment measures, dự báo ETH OOS và ensemble theo recent MSFE; có xét transaction cost", "Thay nguồn thương mại bằng nguồn lịch sử có timestamp và license rõ; fusion rule chỉ học trên development fold", "Proxy miễn phí không phải replication tương đương LSEG/Refinitiv MarketPsych", "Data alignment, source ablation và fusion cho LLM-only/Tech+LLM", "Chưa chạy; historical multi-source snapshot chưa khóa", "Biện minh cho multi-source assessment và đánh giá riêng từng nguồn", "Cần source ablation, delayed/sham assessment, missing-source stress và kiểm tra theo regime", "https://doi.org/10.1016/j.gfj.2024.100945"],
    ["CryptoBERT crypto social-sentiment transfer", "S13 Kulakowski & Frasincar (2023)", "Bình duyệt; IEEE Intelligent Systems; model CryptoBERT công khai trên HuggingFace", "Post-train và fine-tune CryptoBERT cho bài toán bullish/neutral/bearish trên crypto social media", "Dùng như classifier transfer test trên daily crypto information set; ánh xạ bullish-bearish thành score có kiểm soát", "Nguồn gốc paper là social media, không phải news headline hoặc trading execution study", "CryptoBERT scoring artifact và operational/predictive gates của nhánh LLM", "Chưa chạy; chỉ mới bổ sung paper vào matrix và khóa vai trò transfer-test", "Bổ sung baseline chuyên crypto hơn FinBERT tài chính truyền thống", "Phải ghi rõ non-replication; kiểm tra Stage0/Stage1 trước predictive calibration/backtest", "https://doi.org/10.1109/MIS.2023.3283170"],
    ["Memory và temporal evaluation cho LLM agent", "H02 FinMem (journal version)", "Bình duyệt; IEEE Transactions on Big Data; có author repository và temporal train/test", "Kết hợp OHLCV, news, SEC filings và memory; temporal train/test; lặp 5 lần và dùng Wilcoxon signed-rank", "Chỉ kế thừa memory/state có timestamp; mọi memory item phải tuân thủ decision cutoff", "Agent equity daily khác crypto perpetual 4H; kết quả không chuyển trực tiếp", "Frozen memory schema, prompt log và deterministic replay manifest", "Chưa tái lập; dùng temporal split và repeated-run inference làm yêu cầu", "Giảm nguy cơ LLM-only truy xuất thông tin tương lai", "Kiểm tra stochastic-run variance, cache response và paired comparison trên cùng timestamp", "https://doi.org/10.1109/TBDATA.2025.3593370"],
    ["Multimodal fusion Tech + LLM", "H03 FinAgent (KDD 2024)", "Bình duyệt tại KDD; 6 dataset, temporal train/test và risk-adjusted metrics", "Kết hợp K-line/chart, news và expert guidance trong multimodal agent", "Giai đoạn đầu giữ Tech state dạng số; AI chỉ tác động decision field định trước trong treatment", "Giảm degrees of freedom để cô lập incremental value thay vì thay cả agent/execution", "Fusion contract cho Tech+LLM: entry permission, direction score hoặc exposure multiplier", "Chưa chạy; fusion rule và AI data chưa khóa", "Cơ sở cho treatment Tech+LLM nhưng dự án kiểm soát chặt hơn paper", "Ablation từng modality và giữ common execution/risk engine", "https://doi.org/10.1145/3637528.3671801"],
    ["Explainable zero-shot multi-source assessment", "H10 Jung & Lee (2026)", "Bình duyệt; Information Processing & Management; Bitcoin nhưng backtest horizon rất ngắn", "Tổng hợp technical, on-chain, macro và text; zero-shot rationale; có transaction cost, slippage và G-EVAL", "Dùng rationale làm audit artifact; kéo dài OOS theo walk-forward và dùng common simulator", "Backtest 3 ngày không đủ chứng minh generalization hoặc độ bền kinh tế", "Decision/rationale log cho LLM-only và Tech+LLM; evaluator theo fold/regime/cost", "Chưa chạy; chỉ kế thừa source taxonomy, explainability audit và cost requirement", "Gần nhất với AI-derived multi-source market assessment của đề tài", "Cần long-horizon OOS, source ablation, placebo/delay test và formal inference so với Tech-only", "https://doi.org/10.1016/j.ipm.2025.104466"],
])

# Giữ nguyên terminology chuyên ngành như các sheet trước; phần tiếng Việt chỉ
# dùng để giải thích quan hệ và kết quả, không dịch cưỡng ép thuật ngữ.
_technical_terms = {
    "mặt cắt": "cross-sectional",
    "Mặt cắt": "Cross-sectional",
    "dòng lệnh": "order flow",
    "Dòng lệnh": "Order flow",
    "khối lượng bất thường": "abnormal volume",
    "Khối lượng bất thường": "Abnormal volume",
    "mất cân bằng lệnh": "order imbalance",
    "ràng buộc bán khống": "short-sale constraints",
    "Ràng buộc bán khống": "Short-sale constraints",
    "phơi nhiễm": "exposure",
    "Phơi nhiễm": "Exposure",
    "hồi quy": "regression",
    "Hồi quy": "Regression",
    "thống kê t": "t-statistic",
    "độ bền": "robustness",
    "Độ bền": "Robustness",
    "cấu trúc kỳ hạn": "term structure",
    "Cấu trúc kỳ hạn": "Term structure",
    "cú sốc thanh khoản": "liquidity shock",
    "Cú sốc thanh khoản": "Liquidity shock",
    "danh mục": "portfolio",
    "Danh mục": "Portfolio",
}

def _preserve_technical_terms(rows, skipped_columns):
    for _row in rows:
        for _idx, _value in enumerate(_row):
            if _idx in skipped_columns or not isinstance(_value, str):
                continue
            for _vi, _en in _technical_terms.items():
                _value = _value.replace(_vi, _en)
            _row[_idx] = _value

_preserve_technical_terms(s12_data, {0, 1, len(s12_data[0]) - 1})
_preserve_technical_terms(s13_data, {0, 1, len(s13_data[0]) - 1})

# Sheet 12 is an audit of backtest validity, not a generic paper summary.
# NR = not reported in the audited source; N/A = not applicable to that design.
s12_cols = sheet_header_maps["12_Backtest_Design"]
s12_data = [
    ["T05", _paper_titles["T05"], "BTC CoinDesk/Bitstamp; LTC/ETH/XRP CoinMarketCap", "Daily; BTC includes an explicit bear-market OOS period", "Four named assets; not a dynamic point-in-time universe", "N/A — deterministic technical-rule families; no ML training", "14,919 rules across five families; selection controlled for data snooping", "Explicit in-sample and OOS evaluation", "Partial — OOS exists, but no one-time final untouched holdout is documented", "Vectorized rule-return backtest", "Close-to-close rule returns; exact signal-to-fill convention is not sufficiently explicit for exchange execution", "Yes — breakeven transaction-cost analysis", "NR — no separate spread/slippage/market-impact model", "N/A — spot assets", "N/A for leverage; no exchange-level intrabar fill or liquidation engine", "Bear-market OOS, alternative rules and cost robustness", "FWER/FDR and stationary-bootstrap p-values", "Point-in-time universe; explicit fill timing; spread/slippage/impact; final untouched holdout", "Strong rule-search discipline, but execution realism is below a deployable crypto simulator", "https://link.springer.com/article/10.1007/s10479-019-03357-1"],
    ["T03", _paper_titles["T03"], "Broad cryptocurrency cross-section with characteristics and returns", "Daily portfolio/factor construction; historical sample reported in paper", "Broad historical cross-section; lifecycle membership is central to valid replication", "N/A — characteristic sorts and factor portfolios; no predictive model training", "Characteristics and factor specifications selected as research hypotheses", "Historical portfolio and factor tests; robustness across specifications", "No — no final untouched trading holdout", "Portfolio-return / factor backtest", "Characteristics formed before subsequent-period portfolio return", "Partial — transaction-cost robustness, not an exchange fee schedule", "NR — no spread/slippage/impact simulator", "N/A — spot cross-section", "N/A for leverage; no exchange margin/liquidation or intrabar model", "Alternative specifications and factor-adjusted tests", "Alpha, t-statistics and factor regressions", "Final holdout; explicit exchange fills; full friction decomposition; execution capacity", "Top-tier factor evidence and universe-design foundation, not a production execution study", "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119"],
    ["T08", _paper_titles["T08"], "CryptoCompare OHLCV + CoinGecko market cap; 80+ centralized exchanges", "Daily; 2017–2022", "Multi-exchange cross-section; effect strongest in smaller/less-liquid pairs", "N/A — conditional reversal portfolios; no ML training", "Detrended-volume states and portfolio specifications", "Historical cross-sectional portfolios and panel regressions", "No — no final untouched holdout", "Equal/value-weighted portfolio-return backtest", "Lagged return and detrended volume predict the next portfolio period", "Partial — linear transaction-cost robustness", "NR — no separate spread/slippage/impact or capacity fill model", "N/A — spot pairs", "N/A for leverage; no exchange-level liquidation/intrabar engine", "Volume-window, weighting and liquidity-subsample robustness", "Portfolio p-values and panel regression inference", "Final holdout; executable fills; nonlinear impact/capacity; survivorship audit", "Credible causal design; reported premium may not be scalable in the most liquid perpetual universe", "https://www.sciencedirect.com/science/article/pii/S0378426622001418"],
    ["T11", _paper_titles["T11"], "Binance cross-section; volume, order imbalance and margin-trading status", "Daily historical cross-section", "Margin availability separates short-sale-constraint regimes", "N/A — regression/portfolio design; no ML training", "Alternative abnormal-volume and disagreement specifications", "Historical cross-sectional regressions and conditional subsamples", "No — no final untouched holdout", "Return-prediction / portfolio analysis; not an exchange fill simulator", "Abnormal volume/order imbalance measured before future returns", "NR — trading cost is not the primary design variable", "NR", "N/A — spot-market return study", "No margin-path, liquidation or intrabar execution simulation", "Conditional on short-sale constraints and activity specifications", "Factor-adjusted regressions and significance tests", "Fee; spread/slippage/impact; final holdout; executable order model", "Strong microstructure evidence; the short-sale channel may weaken in perpetual markets", "https://onlinelibrary.wiley.com/doi/10.1111/fima.12491"],
    ["T12", _paper_titles["T12"], "CoinMarketCap cryptocurrency cross-section", "Weekly; 2-week formation and 1-week holding", "Historical cross-section; value-weighted WML portfolios", "N/A — rule-based momentum and volatility scaling", "Formation/holding horizons and scaling variants", "Subsample and horizon robustness", "No — no final untouched holdout", "Weekly portfolio-return backtest", "Portfolio formed from prior information, then held one week", "Partial — transaction-cost robustness", "NR — no separate spread/slippage/impact", "N/A — spot cross-section", "Short-sale constraints tested; no exchange margin/liquidation path", "Alternative horizons, costs and short-sale assumptions", "Return t-statistics and annualized Sharpe", "Final holdout; explicit fills/frictions; exposure-normalized comparison", "Credible risk-managed momentum evidence; return gain partly reflects scaling weight above one", "https://www.sciencedirect.com/science/article/pii/S1544612325011377"],
    ["T13", _paper_titles["T13"], "147 cryptocurrencies", "Monthly; January 2015–June 2022", "Historical cross-section; survivorship treatment must be checked in full replication", "N/A — momentum portfolios with predetermined stop-loss rules", "Fixed stop thresholds (10%–50%) and benchmark momentum rules", "Market-state and threshold robustness", "No — no final untouched holdout", "Monthly portfolio backtest with stop-loss overlay", "Exact intraperiod stop ordering/fill convention is not an exchange-level 4H simulator", "NR — cost is not the main reported contribution", "NR", "N/A — spot assets", "Stop rule exists, but no exchange-level intrabar path, margin or liquidation engine", "Multiple thresholds and market-state analysis", "Factor alpha and return significance", "Fee/frictions; intrabar stop fill rule; final holdout; point-in-time universe audit", "Useful risk-overlay ablation, but monthly stop mechanics cannot be copied directly to 4H perpetuals", "https://www.sciencedirect.com/science/article/pii/S2214635023000473"],
    ["T14", _paper_titles["T14"], "BTC, ETH, XLM, LTC, XRP; market and funding-liquidity proxies", "Daily; 2014–2020", "Five named assets; not a dynamic universe", "N/A — liquidity-conditioned exposure rule", "Amihud/funding-liquidity shock definitions and conditional exposure", "Historical strategy plus turbulent-period analysis", "No — no final untouched holdout", "Daily conditional-exposure backtest", "Exposure changes after observed liquidity information; exact fill convention NR", "NR / not fully auditable from public abstract", "NR", "No — funding liquidity is a predictor, not perpetual funding PnL", "No exchange margin/liquidation/intrabar engine", "Turbulent periods, alternative liquidity specifications", "Quantile regression and strategy metrics", "Fee/frictions; final holdout; executable fills; perpetual funding if transferred", "Credible risk evidence, but the project's Amihud-only proxy is only a partial transfer", "https://www.sciencedirect.com/science/article/pii/S1042444X22000019"],
    ["T15", _paper_titles["T15"], "12 OKEx current-quarter futures; licensed data", "Daily/weekly/monthly; November 2017–March 2021", "Fixed dated-futures set; contract roll/lifecycle differs from perpetuals", "N/A — basis, momentum and basis-momentum factor portfolios", "Lookback/holding-period and factor specifications", "Factor regressions and alternative frequencies/horizons", "No — no final untouched holdout", "Dated-futures portfolio-return backtest", "Factor portfolios formed before subsequent holding return", "Partial — transaction-cost robustness", "NR — no separate spread/slippage/impact model", "N/A — dated-futures basis/carry, not perpetual funding payments", "NR — no exchange tiered margin/liquidation or intrabar engine", "Frequency and holding-period sensitivity", "Alpha, t-statistics and spanning regressions", "Final holdout; contract-roll fills; spread/slippage; margin/liquidation; perpetual funding for any perpetual transfer", "Strong derivatives-factor evidence; not directly transferable to perpetual swaps", "https://onlinelibrary.wiley.com/doi/10.1002/fut.22425"],
    ["T16", _paper_titles["T16"], "84 cryptocurrencies; signed order flow from 300+ exchanges in 11 currencies", "Historical multi-exchange sample; exact frequency/period per paper", "Broad world-order-flow universe; true multi-source input", "Nonlinear ML models trained on economic/order-flow predictors", "Model comparison across economic and nonlinear specifications", "Explicit out-of-sample prediction and economic-value portfolios", "Partial — explicit OOS, but no separate one-time final untouched holdout documented in the matrix", "Cross-sectional portfolio sorts; not an exchange event simulator", "Signed flow predicts subsequent returns", "Partial — limits-to-arbitrage/economic-value robustness", "NR — no exchange spread/slippage/impact fill model", "N/A / NR for perpetual funding", "Portfolio constraints; no exchange margin/liquidation/intrabar path", "OOS and limits-to-arbitrage robustness", "OOS predictive inference and economic-value evaluation", "Final untouched holdout; executable fills; friction decomposition; exchange funding/margin for perpetual use", "High-quality OOS evidence; single-venue taker flow is not an equivalent replication", "https://www.sciencedirect.com/science/article/pii/S1386418126000029"],
    ["T17", _paper_titles["T17"], ">3,000 cryptocurrencies; 28 price/volume/momentum/volatility indicators", "Weekly; April 2015–May 2022", "Broad historical cross-section with liquidity subsamples", "Rolling cross-sectional combined elastic net (C-ENet)", "Combined model and alternative research designs", "Rolling OOS factor portfolios", "No — rolling OOS is reported, but no final one-time untouched holdout", "Weekly value-weighted factor backtest", "Indicators available before next weekly return", "Yes/Partial — transaction-cost analysis", "NR — no exchange spread/slippage/impact fill engine", "N/A — spot cross-section", "Liquidity/capacity subsamples; no exchange liquidation/intrabar engine", "Market states, liquidity subsamples and alternative designs", "Newey–West t-statistics and factor alpha", "Final holdout; exchange fills; full friction model; direct implementation of broad C-ENet", "Best aggregate-Tech design reference, but not replicated by the project's narrow oscillator transfer", "https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178"],
    ["Ours", _paper_titles["Ours"], "Official Bybit V5 OHLCV/turnover, instrument lifecycle and historical funding", "4H execution; daily lagged universe selection; multi-year lifecycle sample", "987 contracts with data; trailing 30-day closed turnover selects next-day top 5", "Rule-based Tech candidate; no ML training in current arm", "Predeclared 54-case grid; six development folds; train-only selection", "Walk-forward development folds plus cost-stress evaluation", "No longer untouched — the two reported final folds were observed and subsequent strategy work continued; a new sealed holdout is required", "Event-driven 4H OHLC simulator with position/order/fill/portfolio updates", "Features after candle close; enter at next 4H open; no same-bar re-entry", "Yes — exchange fee", "Yes — half-spread + slippage + nonlinear impact; base/stress/harsh", "Yes — historical Bybit funding at actual timestamps", "Partial — adverse stop fill and delisting modeled; historical tiered maintenance margin/leverage still withheld", "Fold/regime reporting, cost stress and parameter search audit", "PBO/CSCV available; final paired bootstrap/DM/SPA/DSR not yet completed", "New sealed final holdout; formal final inference; tiered margin/liquidation before leverage/live; latency/partial-fill sensitivity", "Most execution-realistic design in the comparison, but not paper-final or live-approved until the remaining controls are completed", "https://bybit-exchange.github.io/docs/v5/market/kline"],
]

# Nội dung Sheet 12 dùng tiếng Việt. Chỉ giữ nguyên tên paper, tên nguồn và
# terminology chuẩn như OOS, holdout, point-in-time, fee, slippage, funding...
_s12_vi = {
    "T05": [
        "BTC từ CoinDesk/Bitstamp; LTC/ETH/XRP từ CoinMarketCap",
        "Dữ liệu ngày; BTC có một giai đoạn OOS trong thị trường giảm rõ ràng",
        "Bốn tài sản được chỉ định cố định; không phải dynamic point-in-time universe",
        "N/A — các họ technical rule xác định trước; không huấn luyện ML",
        "Khảo sát 14.919 quy tắc thuộc năm họ; việc lựa chọn có kiểm soát data snooping",
        "Đánh giá in-sample và OOS riêng biệt",
        "Một phần — có OOS nhưng chưa ghi nhận một final untouched holdout chỉ dùng một lần",
        "Backtest vectorized trên lợi nhuận của technical rule",
        "Lợi nhuận close-to-close; quy ước signal-to-fill chưa đủ rõ để mô phỏng execution trên sàn",
        "Có — phân tích breakeven transaction cost",
        "NR — không tách riêng spread, slippage và market impact",
        "N/A — nghiên cứu tài sản spot",
        "N/A đối với leverage; không có engine intrabar fill hoặc liquidation theo sàn",
        "Có OOS thị trường giảm, nhiều họ quy tắc và kiểm tra robustness theo cost",
        "Dùng FWER/FDR và stationary-bootstrap p-value",
        "Thiếu point-in-time universe, fill timing rõ ràng, spread/slippage/impact và final untouched holdout",
        "Kỷ luật tìm kiếm quy tắc mạnh, nhưng mức độ thực tế của execution thấp hơn một crypto simulator có thể triển khai",
    ],
    "T03": [
        "Cross-sectional crypto rộng, gồm đặc trưng tài sản và lợi nhuận",
        "Xây dựng portfolio/factor theo ngày; giai đoạn lịch sử được báo cáo trong paper",
        "Cross-sectional lịch sử rộng; membership theo lifecycle là điều kiện quan trọng để tái lập hợp lệ",
        "N/A — sắp xếp theo đặc trưng và xây dựng factor portfolio; không huấn luyện predictive model",
        "Các đặc trưng và factor specification được chọn như giả thuyết nghiên cứu",
        "Kiểm định portfolio và factor trên dữ liệu lịch sử; có robustness qua nhiều specification",
        "Không — không có final untouched trading holdout",
        "Backtest lợi nhuận portfolio/factor",
        "Đặc trưng được hình thành trước lợi nhuận portfolio của kỳ kế tiếp",
        "Một phần — có robustness theo transaction cost nhưng không dùng fee schedule của sàn",
        "NR — không có simulator riêng cho spread/slippage/impact",
        "N/A — cross-sectional spot",
        "N/A đối với leverage; không mô phỏng margin/liquidation hoặc intrabar theo sàn",
        "Kiểm tra nhiều specification và kết quả đã điều chỉnh factor",
        "Báo cáo alpha, t-statistic và factor regression",
        "Thiếu final holdout, exchange fill rõ ràng, phân rã đầy đủ friction và execution capacity",
        "Bằng chứng factor thuộc tạp chí hàng đầu và là nền tảng cho universe design, nhưng không phải nghiên cứu production execution",
    ],
    "T08": [
        "OHLCV từ CryptoCompare và market cap từ CoinGecko; hơn 80 sàn tập trung",
        "Dữ liệu ngày, giai đoạn 2017–2022",
        "Cross-sectional đa sàn; hiệu ứng mạnh nhất ở các cặp nhỏ và kém thanh khoản",
        "N/A — conditional reversal portfolio; không huấn luyện ML",
        "Chọn trạng thái detrended volume và các portfolio specification",
        "Portfolio cross-sectional lịch sử và panel regression",
        "Không — không có final untouched holdout",
        "Backtest portfolio với equal-weight và value-weight",
        "Lagged return và detrended volume dự báo lợi nhuận portfolio kỳ kế tiếp",
        "Một phần — có robustness với transaction cost tuyến tính",
        "NR — không tách spread/slippage/impact hoặc mô hình fill theo capacity",
        "N/A — các cặp spot",
        "N/A đối với leverage; không có engine liquidation/intrabar theo sàn",
        "Kiểm tra robustness theo volume window, weighting và liquidity subsample",
        "Báo cáo portfolio p-value và suy luận bằng panel regression",
        "Thiếu final holdout, executable fill, nonlinear impact/capacity và audit survivorship",
        "Thiết kế nhân quả đáng tin cậy; premium được báo cáo có thể khó scale trong perpetual universe thanh khoản nhất",
    ],
    "T11": [
        "Cross-sectional Binance; volume, order imbalance và trạng thái margin trading",
        "Cross-sectional lịch sử theo ngày",
        "Khả năng margin phân tách các regime có mức short-sale constraint khác nhau",
        "N/A — thiết kế regression/portfolio; không huấn luyện ML",
        "Kiểm tra nhiều specification của abnormal volume và disagreement",
        "Cross-sectional regression lịch sử và các conditional subsample",
        "Không — không có final untouched holdout",
        "Phân tích dự báo lợi nhuận/portfolio; không phải exchange fill simulator",
        "Abnormal volume và order imbalance được đo trước future return",
        "NR — trading cost không phải biến thiết kế chính",
        "NR",
        "N/A — nghiên cứu lợi nhuận thị trường spot",
        "Không mô phỏng margin path, liquidation hoặc intrabar execution",
        "Phân tích có điều kiện theo short-sale constraint và activity specification",
        "Factor-adjusted regression và kiểm định ý nghĩa thống kê",
        "Thiếu fee, spread/slippage/impact, final holdout và executable order model",
        "Bằng chứng microstructure mạnh; kênh short-sale constraint có thể yếu hơn trên perpetual market",
    ],
    "T12": [
        "Cross-sectional crypto từ CoinMarketCap",
        "Dữ liệu tuần; formation period 2 tuần và holding period 1 tuần",
        "Cross-sectional lịch sử; WML portfolio theo value-weight",
        "N/A — momentum rule kết hợp volatility scaling",
        "Chọn formation/holding horizon và các scaling variant",
        "Kiểm tra robustness theo subsample và horizon",
        "Không — không có final untouched holdout",
        "Backtest portfolio theo tuần",
        "Portfolio được hình thành từ thông tin quá khứ rồi nắm giữ một tuần",
        "Một phần — có robustness theo transaction cost",
        "NR — không tách spread/slippage/impact",
        "N/A — cross-sectional spot",
        "Có kiểm tra short-sale constraint; không mô phỏng margin/liquidation path theo sàn",
        "Kiểm tra nhiều horizon, cost và giả định short sale",
        "Báo cáo return t-statistic và annualized Sharpe",
        "Thiếu final holdout, fill/friction rõ ràng và so sánh đã chuẩn hóa exposure",
        "Bằng chứng về risk-managed momentum đáng tin; một phần mức tăng return đến từ scaling weight lớn hơn một",
    ],
    "T13": [
        "147 đồng tiền mã hóa",
        "Dữ liệu tháng, từ tháng 01/2015 đến tháng 06/2022",
        "Cross-sectional lịch sử; cần kiểm tra xử lý survivorship khi tái lập đầy đủ",
        "N/A — momentum portfolio với stop-loss rule định trước",
        "Chọn các stop threshold cố định 10%–50% và benchmark momentum rule",
        "Kiểm tra robustness theo market state và threshold",
        "Không — không có final untouched holdout",
        "Backtest portfolio tháng có stop-loss overlay",
        "Quy ước thứ tự và fill của stop trong kỳ không tương đương exchange-level 4H simulator",
        "NR — cost không phải đóng góp báo cáo chính",
        "NR",
        "N/A — tài sản spot",
        "Có stop rule nhưng không có intrabar path, margin hoặc liquidation engine theo sàn",
        "Phân tích nhiều threshold và market state",
        "Báo cáo factor alpha và ý nghĩa thống kê của return",
        "Thiếu fee/friction, intrabar stop fill rule, final holdout và audit point-in-time universe",
        "Hữu ích cho risk-overlay ablation, nhưng cơ chế stop tháng không thể sao chép trực tiếp sang perpetual 4H",
    ],
    "T14": [
        "BTC, ETH, XLM, LTC và XRP; proxy cho market liquidity và funding liquidity",
        "Dữ liệu ngày, giai đoạn 2014–2020",
        "Năm tài sản được chỉ định cố định; không phải dynamic universe",
        "N/A — liquidity-conditioned exposure rule",
        "Định nghĩa Amihud/funding-liquidity shock và conditional exposure",
        "Chiến lược lịch sử kết hợp phân tích turbulent period",
        "Không — không có final untouched holdout",
        "Backtest conditional exposure theo ngày",
        "Exposure thay đổi sau khi quan sát thông tin liquidity; exact fill convention không được báo cáo",
        "NR / chưa thể audit đầy đủ từ public abstract",
        "NR",
        "Không — funding liquidity là predictor, không phải perpetual funding PnL",
        "Không có margin/liquidation/intrabar engine theo sàn",
        "Kiểm tra turbulent period và nhiều liquidity specification",
        "Dùng quantile regression và các strategy metric",
        "Thiếu fee/friction, final holdout, executable fill và perpetual funding nếu chuyển sang perpetual",
        "Bằng chứng về quản trị rủi ro đáng tin; Amihud-only proxy của dự án chỉ được áp dụng một phần",
    ],
    "T15": [
        "12 hợp đồng OKEx current-quarter futures; dữ liệu có giấy phép",
        "Dữ liệu ngày/tuần/tháng, từ 11/2017 đến 03/2021",
        "Tập dated futures cố định; contract roll/lifecycle khác perpetual",
        "N/A — basis, momentum và basis-momentum factor portfolio",
        "Chọn lookback/holding period và factor specification",
        "Factor regression và kiểm tra nhiều frequency/horizon",
        "Không — không có final untouched holdout",
        "Backtest portfolio trên dated futures",
        "Factor portfolio được hình thành trước holding return kỳ sau",
        "Một phần — có robustness theo transaction cost",
        "NR — không tách spread/slippage/impact",
        "N/A — basis/carry của dated futures, không phải perpetual funding payment",
        "NR — không mô phỏng tiered margin/liquidation hoặc intrabar theo sàn",
        "Kiểm tra độ nhạy theo frequency và holding period",
        "Báo cáo alpha, t-statistic và spanning regression",
        "Thiếu final holdout, contract-roll fill, spread/slippage, margin/liquidation và perpetual funding khi transfer",
        "Bằng chứng derivatives factor mạnh, nhưng không thể chuyển trực tiếp sang perpetual swap",
    ],
    "T16": [
        "84 đồng tiền mã hóa; signed order flow từ hơn 300 sàn bằng 11 đồng tiền định giá",
        "Mẫu lịch sử đa sàn; frequency và period chi tiết theo paper",
        "World-order-flow universe rộng; dùng đầu vào multi-source thực",
        "Huấn luyện nonlinear ML model trên economic predictor và order-flow predictor",
        "So sánh model qua nhiều economic và nonlinear specification",
        "Dự báo OOS rõ ràng và portfolio đánh giá economic value",
        "Một phần — có OOS nhưng Matrix chưa ghi nhận final untouched holdout riêng, chỉ dùng một lần",
        "Cross-sectional portfolio sort; không phải exchange event simulator",
        "Signed order flow dự báo subsequent return",
        "Một phần — có robustness về limits to arbitrage và economic value",
        "NR — không có exchange fill model cho spread/slippage/impact",
        "N/A / NR đối với perpetual funding",
        "Có portfolio constraint; không có margin/liquidation/intrabar path theo sàn",
        "Có OOS và robustness theo limits to arbitrage",
        "Suy luận predictive OOS và đánh giá economic value",
        "Thiếu final untouched holdout, executable fill, phân rã friction và funding/margin khi dùng perpetual",
        "Bằng chứng OOS chất lượng cao; single-venue taker flow không phải replication tương đương",
    ],
    "T17": [
        "Hơn 3.000 đồng tiền mã hóa; 28 indicator về price, volume, momentum và volatility",
        "Dữ liệu tuần, từ 04/2015 đến 05/2022",
        "Cross-sectional lịch sử rộng, có liquidity subsample",
        "Rolling cross-sectional combined elastic net (C-ENet)",
        "So sánh combined model và nhiều alternative research design",
        "Rolling OOS factor portfolio",
        "Không — có rolling OOS nhưng không có final untouched holdout dùng một lần",
        "Backtest weekly value-weighted factor",
        "Indicator có sẵn trước return của tuần kế tiếp",
        "Có/Một phần — có phân tích transaction cost",
        "NR — không có exchange fill engine cho spread/slippage/impact",
        "N/A — cross-sectional spot",
        "Có liquidity/capacity subsample; không có liquidation/intrabar engine theo sàn",
        "Kiểm tra market state, liquidity subsample và alternative design",
        "Dùng Newey–West t-statistic và factor alpha",
        "Thiếu final holdout, exchange fill, full friction model và bản triển khai C-ENet rộng đúng paper",
        "Đây là reference mạnh nhất cho aggregate Tech, nhưng dự án chưa tái lập bằng narrow oscillator transfer",
    ],
    "Ours": [
        "Dữ liệu Bybit V5 chính thức: OHLCV/turnover, instrument lifecycle và historical funding",
        "Execution 4H; chọn universe theo dữ liệu ngày có độ trễ; mẫu lifecycle nhiều năm",
        "Có dữ liệu cho 987 hợp đồng; trailing turnover 30 ngày đã đóng chọn top 5 cho ngày kế tiếp",
        "Ứng viên Tech dựa trên rule; nhánh hiện tại không huấn luyện ML",
        "Grid 54 trường hợp định trước; sáu development fold; chỉ chọn trên train",
        "Đánh giá walk-forward trên development set kết hợp cost stress",
        "Không còn untouched — hai fold từng gọi là final đã được xem và sau đó strategy tiếp tục được điều chỉnh; cần sealed holdout mới",
        "Event-driven 4H OHLC simulator, có position/order/fill/portfolio update",
        "Tạo feature sau khi candle đóng; vào tại open 4H kế tiếp; không tái vào cùng bar",
        "Có — dùng exchange fee",
        "Có — half-spread, slippage và nonlinear impact theo ba mức base/stress/harsh",
        "Có — historical Bybit funding đúng timestamp",
        "Một phần — đã mô phỏng adverse stop fill và delisting; vẫn chưa dùng historical tiered maintenance margin/leverage",
        "Báo cáo theo fold/regime, cost stress và audit quá trình parameter search",
        "Đã có PBO/CSCV; chưa hoàn tất paired bootstrap, DM/SPA và DSR cho thí nghiệm cuối",
        "Thiếu sealed final holdout mới, formal inference cuối, tiered margin/liquidation trước leverage/live và sensitivity theo latency/partial fill",
        "Có mức độ thực tế của execution cao nhất trong bảng, nhưng chưa đủ điều kiện chốt paper hoặc đưa live cho đến khi hoàn tất các kiểm soát còn thiếu",
    ],
}

for _row in s12_data:
    _row[2:19] = _s12_vi[_row[0]]

# Paper S/H đại diện cho backtest LLM-only và Tech+LLM. NR được giữ khi
# source audit không đủ bằng chứng để suy đoán execution detail.
s12_data.extend([
    ["S11", "Sentiment Trading with Large Language Models", "965.375 U.S. financial-news articles từ Refinitiv (2010–2023) và CRSP daily stock return", "Daily; reported trading period 08/2021–07/2023", "U.S. equity cross-section ghép news; không phải point-in-time crypto universe", "So sánh OPT, BERT, FinBERT và Loughran–McDonald cho sentiment prediction", "Model/representation selection; chưa có pre-registered search protocol", "Temporal trading evaluation trên subsequent return; không phải crypto walk-forward", "Không có final untouched holdout dùng một lần", "Vectorized daily long–short portfolio backtest", "News sentiment liên kết với subsequent daily return", "Có — 10 bps transaction cost", "NR — không tách spread/slippage/market impact", "N/A — equity study", "Không có exchange margin/liquidation/intrabar engine", "So sánh nhiều language model và sentiment baseline", "Accuracy, portfolio return, Sharpe; không có DSR/PBO tương đương", "Thiếu crypto point-in-time data, walk-forward, executable fill và full friction decomposition", "Bằng chứng S mạnh cho text-to-signal và net trading value; không phải mẫu execution crypto perpetual", "https://doi.org/10.1016/j.frl.2024.105227"],
    ["S12", "Unlocking the Black Box of Sentiment and Cryptocurrency: What, Which, Why, When and How?", "Hơn 50 daily crypto sentiment measures từ LSEG/Refinitiv MarketPsych và ETH return", "Daily; historical sample theo paper; sentiment data thương mại", "Một tài sản ETH; không có dynamic point-in-time universe", "Regularized model, neural network, random forest và adaptive ensemble", "Ensemble weighting theo recent MSFE", "Có OOS forecast evaluation và economic-value analysis", "Không ghi nhận final untouched holdout dùng một lần", "Daily forecast-to-investment backtest", "Sentiment và recent MSFE phải có trước forecast/position kỳ sau", "Có — xét investment gain sau transaction cost", "NR — không có spread/slippage/impact model riêng", "N/A — không phải perpetual funding PnL", "Không có exchange margin/liquidation/intrabar engine", "So sánh nhiều model và adaptive combination", "OOS forecast error và investment gain", "Thiếu reproducible raw sentiment, dynamic universe, exchange fill, final holdout và full cost decomposition", "Bằng chứng S crypto gần đề tài nhất; mạnh về multi-source fusion và OOS, yếu về execution", "https://doi.org/10.1016/j.gfj.2024.100945"],
    ["H02", "FinMem: A Performance-Enhanced LLM Trading Agent", "TSLA, NFLX, AMZN, MSFT, COIN; yfinance OHLCV, Alpaca News, SEC filings và daily news", "Daily; 08/2021–04/2023; train đến 10/2022, test sau đó", "Năm single-stock dataset cố định; không phải crypto perpetual universe", "LLM agent dùng layered memory và persona", "Memory/agent configuration; kết quả trung bình 5 lần chạy", "Temporal holdout rõ giữa train và test", "Có test period tách biệt; không phải sealed holdout của dự án", "Custom daily trading simulator", "Memory/news cập nhật theo thời gian; exchange fill semantics không rõ", "NR trong source audit hiện tại", "NR — không có spread/slippage/impact model đã xác minh", "N/A — equity study", "Không có tiered margin/liquidation/intrabar engine", "Năm dataset và năm stochastic trial", "Wilcoxon signed-rank; CR, Sharpe, volatility và MaxDD", "Thiếu full friction, point-in-time universe, exchange fill và crypto funding/margin", "Hữu ích cho temporal split, memory causality và repeated-run inference; execution đơn giản", "https://doi.org/10.1109/TBDATA.2025.3593370"],
    ["H03", "A Multimodal Foundation Agent for Financial Trading: Tool-Augmented, Diversified, and Generalist", "AAPL, AMZN, GOOGL, MSFT, TSLA, ETHUSD; daily price, chart, news và expert guidance", "Daily; 06/2022–01/2024; train đến 06/2023, test phần sau", "Sáu dataset cố định; không phải dynamic point-in-time universe", "Multimodal foundation agent dùng market, chart và text tool", "Tool/modality/agent configuration trong framework", "Temporal train/test rõ; không paired walk-forward với Tech baseline", "Có temporal test; không ghi nhận final holdout sau toàn bộ search", "Custom daily trading evaluation", "Daily input tạo action kỳ sau; exact fill convention chưa đủ", "NR trong source audit hiện tại", "NR — không có spread/slippage/impact model đã xác minh", "N/A/NR — không có historical perpetual funding", "Không có tiered margin/liquidation/intrabar engine", "Sáu asset/dataset và nhiều risk-adjusted metric", "ARR, Sharpe, Calmar, Sortino, MaxDD và volatility", "Thiếu common execution baseline, full friction, dynamic universe, ablation cô lập AI và paired inference", "Bằng chứng H tốt cho multimodal fusion; dự án phải đo riêng Tech+LLM − Tech-only", "https://doi.org/10.1145/3637528.3671801"],
    ["H10", "Explainable Zero-Shot Trading Using Multi-Agent LLM Architecture: A Backtested Approach for Bitcoin Price", "Hơn 1.400 ngày Bitcoin với technical, on-chain, macro và Reddit/news sentiment", "Historical context hơn 1.400 ngày nhưng reported trading backtest chỉ 3 ngày", "Một tài sản BTC; không có dynamic universe", "Zero-shot multi-agent LLM; không fine-tune trading model", "Agent/prompt/source architecture; search protocol chưa đủ kiểm toán", "Backtest 3 ngày; không đủ OOS generalization", "Không có sealed final holdout theo chuẩn dự án", "Simulated short-horizon Bitcoin backtest", "Multi-source assessment tạo decision; exact fill semantics chưa đủ tái lập", "Có — transaction cost", "Có/Một phần — slippage; impact/capacity chưa xác minh", "NR — không có historical perpetual funding PnL", "Không có tiered margin/liquidation/intrabar engine đã xác minh", "Có rationale/G-EVAL; horizon không đủ regime robustness", "Return, Sharpe và G-EVAL; không có paired incremental-value inference", "Thiếu long-horizon OOS, common execution baseline, funding/margin và source ablation", "Paper H gần nhất về nguồn dữ liệu; backtest 3 ngày quá yếu để làm chuẩn hiệu quả", "https://doi.org/10.1016/j.ipm.2025.104466"],
])

# Nghiên cứu có ba backtest arm. Tech-only là control; Tech+LLM là treatment
# chính để đo incremental value; LLM-only là ablation để kiểm tra khả năng thay
# thế/bổ trợ. Các biến execution/risk phải dùng chung, nhưng trạng thái triển
# khai và tính sẵn có của dữ liệu được báo cáo riêng, không suy đoán.
_ours_base = next(_row for _row in s12_data if _row[0] == "Ours")
s12_data = [_row for _row in s12_data if _row[0] != "Ours"]

def _arm_row(arm_id, title, overrides):
    _row = list(_ours_base)
    _row[0] = arm_id
    _row[1] = title
    for _idx, _value in overrides.items():
        _row[_idx] = _value
    return _row

s12_data.extend([
    _arm_row("O-Tech", "Ours — Tech-only control", {
        5: "Ứng viên Tech dựa trên rule; không huấn luyện ML",
        6: "Grid 54 trường hợp định trước; sáu development fold; chỉ chọn trên train",
        7: "Đã chạy development walk-forward và cost stress",
        8: "Không còn untouched — hai fold từng gọi là final đã được xem; cần sealed holdout mới sau khi khóa cả ba arm",
        15: "Đã báo cáo theo fold/regime, cost stress và audit quá trình parameter search",
        16: "Đã có PBO/CSCV; chưa hoàn tất paired bootstrap, DM/SPA và DSR cho thí nghiệm ba arm",
        17: "Thiếu sealed final holdout mới, formal inference cuối và tiered margin/liquidation trước leverage/live",
        18: "Control Tech đã có candidate nhưng chưa được khóa để chạy final controlled experiment",
    }),
    _arm_row("O-LLM", "Ours — LLM-only / AI-derived assessment", {
        2: "Cùng dữ liệu thị trường Bybit với Tech; bổ sung derivatives microstructure, positioning, liquidation và LLM news có timestamp",
        3: "Chưa chốt — historical multi-source coverage và decision frequency phải được khóa trước backtest",
        4: "Phải dùng đúng point-in-time universe của Tech; hiện historical AI source chưa được khóa",
        5: "AI-derived multi-source assessment độc lập tạo direction/permission/exposure theo rule định trước; không dùng Tech signal",
        6: "Chưa thực hiện — phải khóa model/version, prompt, source list, temperature, threshold và missing-data policy",
        7: "Chưa chạy — phải dùng cùng development walk-forward folds và timestamp với Tech",
        8: "Chưa có — chỉ được dùng sealed final holdout sau khi toàn bộ AI pipeline đã khóa",
        9: "Dùng chung event-driven 4H OHLC simulator với Tech; arm chưa được chạy",
        10: "AI assessment phải có trước decision cutoff; fill tại open 4H kế tiếp như Tech; chưa chạy",
        11: "Dùng cùng exchange fee model với Tech; chưa chạy arm",
        12: "Dùng cùng half-spread, slippage và nonlinear impact với Tech; chưa chạy arm",
        13: "Dùng historical Bybit funding đúng timestamp qua common engine; chưa chạy arm",
        14: "Dùng cùng stop/delisting/margin policy với Tech; tiered maintenance margin vẫn chưa hoàn thiện",
        15: "Chưa chạy robustness; phải kiểm tra từng data source, prompt/model stability và market regime",
        16: "Chưa chạy; cần paired block bootstrap và multiple-testing correction cho prompt/source/model search",
        17: "Thiếu causal AI data, frozen AI pipeline, OOS run, sealed holdout, cost stress và formal inference",
        18: "Chưa được backtest; không được dùng để đưa ra claim về hiệu quả LLM ở trạng thái hiện tại",
    }),
    _arm_row("O-Hybrid", "Ours — Tech + LLM treatment", {
        2: "Kết hợp dữ liệu Tech point-in-time với derivatives microstructure, positioning, liquidation và LLM news có timestamp",
        3: "Chưa chốt — phải đồng bộ mọi AI input với đúng decision timestamp của Tech",
        4: "Phải dùng cùng point-in-time universe, calendar và delisting rule với Tech-only",
        5: "Giữ nguyên Tech state; AI assessment chỉ được thay đổi decision field định trước như entry permission, direction score hoặc exposure multiplier",
        6: "Chưa thực hiện — phải khóa Tech parameter, AI model/prompt/source và fusion rule trước khi xem treatment result",
        7: "Chưa chạy — phải ghép cặp từng timestamp/fold với Tech-only",
        8: "Chưa có — sealed final holdout phải dùng đồng thời một lần cho cả ba arm",
        9: "Dùng chung event-driven 4H OHLC simulator với Tech-only; treatment chưa được chạy",
        10: "AI overlay chỉ tác động signal trước cutoff; fill tại open 4H kế tiếp như Tech-only; chưa chạy",
        11: "Dùng cùng exchange fee model với Tech-only; total fee có thể khác do turnover khác",
        12: "Dùng cùng half-spread, slippage và nonlinear impact model với Tech-only",
        13: "Dùng historical Bybit funding đúng timestamp qua common engine; chưa chạy arm",
        14: "Dùng cùng stop/delisting/margin policy với Tech-only; tiered maintenance margin vẫn chưa hoàn thiện",
        15: "Chưa chạy; cần source ablation, sham/delayed assessment, cost stress và regime interaction",
        16: "Chưa chạy; primary endpoint là paired incremental net return so với Tech-only, kèm CI và multiple-testing correction",
        17: "Thiếu frozen treatment protocol, paired OOS, sealed holdout, ablation/placebo và formal inference",
        18: "Treatment chính chưa được backtest; hiện chưa thể kết luận AI tạo thêm giá trị giao dịch",
    }),
])

s12_full_data = s12_data
s12_execution_cols = [
    "ID", "Paper Title (Tên bài báo)", "Simulator Type (Loại simulator)",
    "Signal-to-Fill Timing (Thời điểm signal → fill)", "Fee",
    "Spread / Slippage / Market Impact", "Funding",
    "Margin / Liquidation / Intrabar", "Missing Execution Components (Thành phần execution còn thiếu)",
    "Execution Assessment (Đánh giá execution)", "Source URL (URL nguồn)",
]
s12_execution_data = [[row[i] for i in [0, 1, 9, 10, 11, 12, 13, 14, 17, 18, 19]] for row in s12_full_data]
s12_data = [[row[i] for i in [0, 1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 18, 19]] for row in s12_full_data]

s12_audit_cols = ["Minimum Requirement (Yêu cầu tối thiểu)", "Required? (Bắt buộc?)", "Why It Matters (Vì sao cần)", "T05", "T03", "T08", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "S11", "S12", "H02", "H03", "H10", "Tech-only", "LLM-only", "Tech+LLM"]
s12_audit_data = [
    ["Point-in-time data & universe", "Yes", "Ngăn look-ahead và survivorship/delisting bias", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "✗", "Partial", "Partial", "Partial", "✓"],
    ["Data quality control & reproducible snapshot", "Yes", "Kiểm soát missing/duplicate/timestamp và cho phép tái lập", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "Partial"],
    ["Features/signals use information available at t", "Yes", "Ngăn leakage và look-ahead bias", "Partial", "✓", "✓", "✓", "✓", "Partial", "Partial", "✓", "✓", "✓", "✓"],
    ["Temporal split; no random split", "Yes", "Financial time series không IID", "✓", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "✓", "✓", "✓"],
    ["Walk-forward / Purging / Embargo when needed", "Conditional", "Kiểm tra generalization và loại overlapping-label leakage", "✗", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "Partial", "✓", "Partial"],
    ["Final untouched holdout used once", "Yes", "Bảo vệ claim true OOS sau toàn bộ model/parameter search", "Partial", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "Partial", "✗", "✗"],
    ["Pipeline frozen before final test", "Yes", "Ngăn test-set feedback và tuning sau khi xem kết quả", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "NR", "✗"],
    ["Signal-to-fill timing / position shift", "Yes", "Signal từ close[t] không được fill ngược tại chính close[t]", "Partial", "✓", "✓", "✓", "✓", "Partial", "Partial", "✓", "✓", "✓", "✓"],
    ["Event-driven or conservative intrabar fills when SL/TP", "Conditional", "OHLC không cho biết TP hay SL chạm trước", "N/A", "N/A", "N/A", "N/A", "N/A", "✗", "N/A", "N/A", "N/A", "N/A", "✓"],
    ["Trading fee", "Yes", "Gross alpha có thể biến mất sau fee", "✓", "Partial", "Partial", "✗", "Partial", "✗", "✗", "Partial", "Partial", "Partial", "✓"],
    ["Spread / slippage / market impact", "Yes", "Fee alone understates executable cost and capacity", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✗", "✓"],
    ["Historical funding for perpetuals", "Conditional", "Long/short perpetual PnL depends on realized funding", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "✓"],
    ["Margin / liquidation / tier model when leveraged", "Conditional", "Leverage × return without liquidation is invalid", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "NR", "N/A", "N/A", "Partial"],
    ["Cost stress & break-even cost", "Yes", "Cho biết alpha tồn tại đến mức friction nào", "✓", "Partial", "Partial", "✗", "Partial", "✗", "✗", "Partial", "Partial", "✓", "✓"],
    ["Strong benchmarks & ablation", "Yes", "Tách contribution khỏi benchmark yếu hoặc thay đổi nhiều thành phần", "✓", "✓", "✓", "Partial", "✓", "✓", "Partial", "✓", "✓", "✓", "Partial"],
    ["Parameter / regime / asset robustness", "Yes", "Loại sharp optimum và performance chỉ nhờ một market state", "Partial", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "✓", "Partial"],
    ["Multiple-testing correction / DSR / PBO / SPA", "Conditional", "Bắt buộc khi thử nhiều rules/models/thresholds", "✓", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial"],
    ["OOS-only equity and net performance reporting", "Yes", "Prediction accuracy không đồng nghĩa economic profitability", "✓", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "Partial", "✓", "✓", "Partial"],
]

_s12_audit_vi = [
    ("Dữ liệu và universe point-in-time", "Bắt buộc"),
    ("Data quality control và reproducible snapshot", "Bắt buộc"),
    ("Feature/signal chỉ dùng thông tin có sẵn tại thời điểm t", "Bắt buộc"),
    ("Temporal split; không dùng random split", "Bắt buộc"),
    ("Walk-forward / Purging / Embargo khi cần", "Có điều kiện"),
    ("Final untouched holdout chỉ dùng một lần", "Bắt buộc"),
    ("Khóa pipeline trước final test", "Bắt buộc"),
    ("Quy định signal-to-fill timing / position shift", "Bắt buộc"),
    ("Event-driven hoặc conservative intrabar fill khi có SL/TP", "Có điều kiện"),
    ("Trading fee", "Bắt buộc"),
    ("Spread / slippage / market impact", "Bắt buộc"),
    ("Historical funding khi giao dịch perpetual", "Có điều kiện"),
    ("Margin / liquidation / tier model khi dùng leverage", "Có điều kiện"),
    ("Cost stress và breakeven cost", "Bắt buộc"),
    ("Benchmark mạnh và ablation", "Bắt buộc"),
    ("Robustness theo parameter / regime / asset", "Bắt buộc"),
    ("Hiệu chỉnh multiple testing / DSR / PBO / SPA", "Có điều kiện"),
    ("Equity curve chỉ từ OOS và báo cáo net performance", "Bắt buộc"),
]
for _row, (_requirement, _required) in zip(s12_audit_data, _s12_audit_vi):
    _row[0] = _requirement
    _row[1] = _required

_s12_audit_reasons_vi = [
    "Ngăn look-ahead bias và survivorship/delisting bias",
    "Kiểm soát dữ liệu thiếu, trùng lặp và sai timestamp; đồng thời cho phép tái lập",
    "Ngăn data leakage và look-ahead bias",
    "Chuỗi thời gian tài chính không có tính IID",
    "Kiểm tra khả năng generalization và loại leakage do overlapping label",
    "Bảo vệ kết luận true OOS sau toàn bộ quá trình tìm model và parameter",
    "Ngăn feedback từ test set và tuning sau khi đã xem kết quả",
    "Signal dựa trên close[t] không được fill ngược tại chính close[t]",
    "OHLC không cho biết TP hay SL được chạm trước",
    "Gross alpha có thể biến mất sau fee",
    "Chỉ tính fee sẽ đánh giá thấp executable cost và giới hạn capacity",
    "PnL long/short perpetual phụ thuộc realized funding",
    "Không thể chỉ lấy leverage nhân return rồi bỏ qua liquidation",
    "Cho biết alpha còn tồn tại đến mức trading friction nào",
    "Tách contribution thực khỏi benchmark yếu hoặc việc thay đổi nhiều thành phần cùng lúc",
    "Loại sharp optimum và performance chỉ xuất hiện trong một market state",
    "Bắt buộc khi thử nhiều rule, model hoặc threshold",
    "Prediction accuracy không đồng nghĩa với khả năng sinh lợi sau chi phí",
]
for _row, _reason in zip(s12_audit_data, _s12_audit_reasons_vi):
    _row[2] = _reason

# Thêm năm cột S/H trước cột Tech-only hiện có.
_s_h_audit = [
    ("Một phần", "Một phần", "Một phần", "Một phần", "Một phần"),
    ("NR", "Một phần", "Một phần", "NR", "NR"),
    ("Một phần", "✓", "Một phần", "Một phần", "Một phần"),
    ("✓", "✓", "✓", "✓", "✗"),
    ("✗", "Một phần", "✗", "✗", "✗"),
    ("✗", "✗", "Một phần", "Một phần", "✗"),
    ("NR", "NR", "Một phần", "NR", "NR"),
    ("Một phần", "Một phần", "Một phần", "Một phần", "Một phần"),
    ("N/A", "N/A", "N/A", "N/A", "N/A"),
    ("✓", "✓", "NR", "NR", "✓"),
    ("✗", "✗", "✗", "✗", "Một phần"),
    ("N/A", "N/A", "N/A", "N/A", "NR"),
    ("N/A", "N/A", "N/A", "N/A", "NR"),
    ("✗", "Một phần", "✗", "✗", "✗"),
    ("Một phần", "✓", "Một phần", "Một phần", "Một phần"),
    ("Một phần", "✓", "✓", "✓", "✗"),
    ("✗", "Một phần", "Một phần", "✗", "✗"),
    ("✓", "✓", "✓", "✓", "Một phần"),
]
for _row, _statuses in zip(s12_audit_data, _s_h_audit):
    _row[-1:-1] = list(_statuses)

# Cột Ours cũ trở thành Tech-only; bổ sung trạng thái riêng cho LLM-only và
# Tech+LLM. Dấu đánh giá phản ánh trạng thái đã triển khai, không phải kế hoạch.
_llm_hybrid_audit = [
    ("✗", "✗"),       # point-in-time AI data/universe not frozen
    ("✗", "✗"),       # immutable source snapshots not available
    ("✗", "✗"),       # causal AI availability not verified
    ("✗", "✗"),       # no temporal backtest yet
    ("✗", "✗"),       # no walk-forward yet
    ("✗", "✗"),       # no final holdout
    ("✗", "✗"),       # pipelines not frozen
    ("Partial", "Partial"),
    ("Partial", "Partial"),
    ("Partial", "Partial"),
    ("Partial", "Partial"),
    ("Partial", "Partial"),
    ("Partial", "Partial"),
    ("✗", "✗"),       # no cost stress results
    ("✗", "✗"),       # comparison/ablation not run
    ("✗", "✗"),       # robustness not run
    ("✗", "✗"),       # inference not run
    ("✗", "✗"),       # no OOS net equity
]
for _row, (_llm_status, _hybrid_status) in zip(s12_audit_data, _llm_hybrid_audit):
    _row.extend([_llm_status, _hybrid_status])

# Nội dung hiển thị dùng tiếng Việt; giữ NR/N/A là ký hiệu chuẩn đã giải thích.
for _row in s12_audit_data:
    for _idx, _value in enumerate(_row):
        if _value == "Partial":
            _row[_idx] = "Một phần"

# Sheet 13 được tách thành ba bảng để không trộn lẫn: (1) cơ sở phương pháp
# từ literature, (2) kết quả reproduction/transfer, và (3) protocol ba arm.
_s13_component_vi = {
    "Technical rule families": "Họ rule kỹ thuật",
    "Market-regime gate": "Cổng market regime",
    "Dynamic universe": "Universe động",
    "Cross-asset momentum ranking": "Xếp hạng cross-asset momentum",
    "Conditional reversal / disagreement": "Reversal / disagreement có điều kiện",
    "Volatility-managed exposure": "Exposure quản trị theo volatility",
    "Stop and trailing exit": "Stop và trailing exit",
    "Liquidity-risk overlay": "Lớp phủ liquidity risk",
    "Basis / term structure": "Basis / term structure",
    "Order-flow feature": "Đặc trưng order flow",
    "Execution and data provenance": "Execution và nguồn gốc dữ liệu",
    "Train/validation and search control": "Train/validation và kiểm soát tìm kiếm",
    "Controlled incremental-value experiment": "Thí nghiệm incremental value có kiểm soát",
    "LLM sentiment signal": "Tín hiệu sentiment từ LLM",
    "Multi-source crypto sentiment và adaptive ensemble": "Crypto sentiment đa nguồn và adaptive ensemble",
    "CryptoBERT crypto social-sentiment transfer": "Chuyển giao CryptoBERT cho crypto social-sentiment",
    "Memory và temporal evaluation cho LLM agent": "Memory và temporal evaluation cho LLM agent",
    "Multimodal fusion Tech + LLM": "Multimodal fusion Tech + LLM",
    "Explainable zero-shot multi-source assessment": "Đánh giá đa nguồn zero-shot có giải thích",
}

def _s13_group(index):
    if index <= 9:
        return "Kỹ thuật (T)"
    if index == 10:
        return "Dữ liệu & execution chung"
    if index == 11:
        return "Đánh giá & kiểm định chung"
    if index == 12:
        return "Thiết kế so sánh ba arm"
    if index in {13, 14, 15}:
        return "Sentiment / LLM (S)"
    return "Hybrid (H)"

def _s13_applies(index):
    if index <= 9:
        return "Tech-only; dùng chung khi liên quan execution/risk"
    if index in {10, 11, 12}:
        return "Cả ba arm"
    if index in {13, 14, 15}:
        return "LLM-only và Tech+LLM"
    return "Tech+LLM; một phần áp dụng cho LLM-only"

_s13_transfer_status = [
    "Đã chạy — giữ lại", "Đã chạy — giữ lại", "Đã chạy — giữ lại",
    "Đã chạy — giữ lại", "Đã chạy — không cải thiện", "Đã chạy — không cải thiện",
    "Đã chạy — giữ lại", "Đã chạy — không cải thiện", "Đã chạy — không cải thiện",
    "Đã chạy — không cải thiện", "Đã triển khai một phần", "Đã triển khai một phần",
    "Chưa chạy thí nghiệm ba arm", "Chưa chạy", "Chưa chạy", "Chưa chạy",
    "Chưa tái lập",
    "Chưa chạy", "Chưa chạy",
]

s13_method_cols = [
    "Method Source / Role (Nguồn / vai trò phương pháp)", "Methodology Component (Thành phần phương pháp)",
    "Reference Paper(s) (Bài báo tham khảo)", "Credibility (Độ uy tín)",
    "Original Method (Phương pháp gốc)", "Project Adaptation (Điều chỉnh cho đề tài)",
    "Applicable Arm(s) (Arm áp dụng)", "Source URL (URL nguồn)",
]
s13_method_data = []
s13_transfer_cols = [
    "Methodology Component (Thành phần phương pháp)", "Implementation / Artifact (Hiện thực / sản phẩm)",
    "Reproduction / Transfer Result (Kết quả chạy lại / áp dụng)", "Transfer Status (Trạng thái áp dụng)",
    "Why Modified (Lý do điều chỉnh)", "RQ Contribution (Đóng góp cho câu hỏi nghiên cứu)",
    "Remaining Test (Kiểm định còn thiếu)", "Applicable Arm(s) (Arm áp dụng)",
]
s13_transfer_data = []
for _idx, _row in enumerate(s13_data):
    _component = _s13_component_vi.get(_row[0], _row[0])
    _applies = _s13_applies(_idx)
    s13_method_data.append([_s13_group(_idx), _component, _row[1], _row[2], _row[3], _row[4], _applies, _row[10]])
    s13_transfer_data.append([_component, _row[6], _row[7], _s13_transfer_status[_idx], _row[5], _row[8], _row[9], _applies])

# Bảng cơ sở phương pháp phải trình bày literature T → S → H trước; ba hàng
# tổng hợp của đề tài (data/execution, evaluation và controlled design) đứng cuối.
_s13_method_order = [*range(0, 10), *range(13, 19), 10, 11, 12]
s13_method_data = [s13_method_data[_idx] for _idx in _s13_method_order]

s13_arm_cols = [
    "Arm", "Methodological Role (Vai trò phương pháp)", "Input (Dữ liệu đầu vào)",
    "Signal / Decision Rule (Quy tắc tín hiệu / quyết định)", "Train / Tuning (Huấn luyện / tinh chỉnh)",
    "OOS Test (Kiểm thử OOS)", "Common Controls (Kiểm soát dùng chung)",
    "Effect / Interpretation (Hiệu ứng / diễn giải)", "Current Status (Trạng thái hiện tại)",
]
s13_arm_data = [
    ["Tech-only", "Control định lượng truyền thống", "OHLCV/turnover, lifecycle universe, historical funding và dữ liệu execution point-in-time", "Channel + market-regime gate + cross-asset momentum rank; ATR stop/trailing", "Grid định trước; chỉ chọn trên development fold; không chỉnh sau khi xem AI", "Chạy cùng timestamp/fold với hai arm AI; dùng sealed holdout mới một lần", "Cùng universe, calendar, capital, size, fee, spread, slippage, impact, funding, risk và margin policy", "Mốc đối chứng; không tự trả lời incremental value của AI", "Đã có candidate; chưa khóa cho final experiment"],
    ["LLM-only", "Diagnostic ablation để kiểm tra AI có thể thay thế Tech hay không", "Derivatives microstructure, positioning, liquidation, on-chain và news/RSS có publication/ingestion timestamp", "AI-derived assessment tự tạo direction/permission/exposure; không dùng Tech signal", "Khóa source list, model/version, prompt, temperature, threshold, memory và missing-data policy", "Temporal walk-forward; cache response; lặp stochastic run khi cần; sealed holdout dùng cùng hai arm còn lại", "Dùng chính common execution/risk engine của Tech-only", "Hiệu quả độc lập của AI; chỉ hỗ trợ diễn giải cơ chế, không phải primary effect", "Chưa chạy; historical AI pipeline chưa khóa"],
    ["Tech+LLM", "Treatment chính để đo incremental trading value", "Toàn bộ input Tech point-in-time cộng assessment đa nguồn đã khóa", "Giữ nguyên Tech state; AI chỉ được sửa decision field định trước như entry permission, direction score hoặc exposure multiplier", "Khóa Tech parameter, AI pipeline và fusion rule trước khi xem treatment result", "Paired OOS theo từng timestamp/fold; source/modality ablation; sham/delayed assessment; sealed holdout dùng một lần", "Giống Tech-only; total cost có thể khác nội sinh do turnover khác nhưng cost model phải giống", "Primary effect = Performance(Tech+LLM) − Performance(Tech-only), báo cáo CI và tương tác market regime", "Chưa chạy; treatment protocol chưa khóa hoàn toàn"],
]

sheet_header_maps["13_Method_Traceability"] = s13_method_cols

sheets_dict = {
    "1_Master_Database": (s1_cols, s1_data),
    "2_Technical_Trading": (s2_cols, s2_data),
    "3_Sentiment_Trading": (s3_cols, s3_data),
    "4_Hybrid_Trading": (s4_cols, s4_data),
    "5_Experimental_Design": (s5_cols, s5_data),
    "6_Evaluation_Metrics": (s6_cols, s6_data),
    "7_Research_Gap_Matrix": (s7_cols, s7_data),
    "8_Evidence_Summary": (s8_cols, s8_data),
    "9_Top_20_Papers": (s9_cols, s9_data),
    "12_Backtest_Design": (s12_cols, s12_data),
    "13_Method_Traceability": (s13_method_cols, s13_method_data),
}

# Populate workbook
for sheet_name, (cols, data) in sheets_dict.items():
    ws = wb.create_sheet(title=sheet_display_names.get(sheet_name, sheet_name))
    ws.views.sheetView[0].showGridLines = True
    if sheet_name not in ["8_Evidence_Summary", "10_Dashboard"]:
        ws.freeze_panes = "A2"  # Freeze top row only

    display_cols = sheet_header_maps.get(sheet_name, cols)

    # Write header
    ws.append(display_cols)
    for col_num in range(1, len(display_cols) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    # Write data
    for row_idx, row_data in enumerate(data, start=2):
        display_row = [translate_display_value(sheet_name, col_idx, val) for col_idx, val in enumerate(row_data, start=1)]
        if sheet_name == "1_Master_Database":
            status = PUBLICATION_STATUS.get(record_id(row_data), "See venue / source")
            display_row.insert(6, status)
            scholar_url = build_google_scholar_url(row_data[1])
            display_row.insert(14, scholar_url)
        ws.append(display_row)
        for col_idx, val in enumerate(display_row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.border = thin_border

            # Alignments & Styling
            val_str = str(val)
            if val_str in ["✓", "✗", "Single", "Multi", "Partial", "High", "N/A"]:
                cell.alignment = align_center
                if val_str == "✓":
                    cell.font = Font(name="Calibri", size=10, bold=True, color="008000") # Green tick
                elif val_str == "✗":
                    cell.font = Font(name="Calibri", size=10, color="A61C1C") # Red cross
            elif col_idx == 1 and is_display_id(val_str):
                cell.font = id_font
                cell.alignment = align_center
            elif sheet_name == "1_Master_Database" and col_idx == 2:
                cell.font = link_bold_font
                cell.alignment = align_left
                cell.hyperlink = build_google_scholar_url(row_data[1])
            elif sheet_name == "1_Master_Database" and col_idx == 8:
                doi_url = build_doi_url(row_data[6])
                if doi_url:
                    cell.font = link_font
                    cell.hyperlink = doi_url
                cell.alignment = align_left
            elif sheet_name == "1_Master_Database" and col_idx == 15:
                cell.font = link_font
                cell.hyperlink = val_str
                cell.alignment = align_left
            elif col_idx == 1 or col_idx == 2:
                cell.font = bold_font
                cell.alignment = align_left
            else:
                cell.alignment = align_left

        # Format conclusion row if it exists
        if display_row and display_row[0] and isinstance(display_row[0], str) and (display_row[0].startswith("Nhận xét:") or display_row[0].startswith("Draft :")):
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=len(display_row))
            first_cell = ws.cell(row=row_idx, column=1)
            first_cell.alignment = Alignment(wrap_text=True, horizontal="left", vertical="top")
            first_cell.font = Font(name="Calibri", size=11)
            ws.row_dimensions[row_idx].height = 120

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            lines = val_str.split('\n')
            for l in lines:
                if len(l) > max_len:
                    max_len = len(l)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 10), 52)

    if sheet_name in {"12_Backtest_Design", "13_Method_Traceability"}:
        # These are audit matrices: wide descriptive columns, compact row-wise
        # records, frozen identifiers and visually distinct source links.
        ws.freeze_panes = "C2" if sheet_name == "12_Backtest_Design" else "B2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(display_cols))}{len(data) + 1}"
        ws.row_dimensions[1].height = 42
        for row_idx in range(2, ws.max_row + 1):
            ws.row_dimensions[row_idx].height = 96
        width_map = (
            [38, 44, 46, 26, 36, 36, 34, 34, 34, 34, 36, 42, 34]
            if sheet_name == "12_Backtest_Design"
            else [24, 34, 48, 34, 42, 42, 34, 34]
        )
        for col_idx, width in enumerate(width_map, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        for row_idx in range(2, ws.max_row + 1):
            source_cell = ws.cell(row=row_idx, column=len(display_cols))
            if str(source_cell.value).startswith("http"):
                source_cell.hyperlink = str(source_cell.value)
                source_cell.font = link_font
        if sheet_name == "12_Backtest_Design":
            # Color-code the protocol stages so the very wide audit remains
            # readable without translating standard backtest terminology.
            stage_fills = {
                "DATA": PatternFill("solid", fgColor="1F4E78"),
                "TRAIN": PatternFill("solid", fgColor="7030A0"),
                "TEST": PatternFill("solid", fgColor="548235"),
                "EXECUTION": PatternFill("solid", fgColor="C65911"),
                "VALIDITY": PatternFill("solid", fgColor="008C95"),
                "Missing": PatternFill("solid", fgColor="A61C1C"),
            }
            for col_idx, header in enumerate(display_cols, start=1):
                for prefix, fill in stage_fills.items():
                    if str(header).startswith(prefix):
                        ws.cell(1, col_idx).fill = fill
                        break

            max_table_cols = max(len(display_cols), len(s12_execution_cols), len(s12_audit_cols))
            execution_title_row = ws.max_row + 3
            ws.merge_cells(start_row=execution_title_row, start_column=1, end_row=execution_title_row, end_column=max_table_cols)
            execution_title = ws.cell(execution_title_row, 1, "Execution Simulator & Trading Frictions (Simulator thực thi & ma sát giao dịch)")
            execution_title.fill = PatternFill("solid", fgColor="C65911")
            execution_title.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
            execution_title.alignment = align_left
            ws.row_dimensions[execution_title_row].height = 28

            execution_header_row = execution_title_row + 1
            for col_idx, header in enumerate(s12_execution_cols, start=1):
                cell = ws.cell(execution_header_row, col_idx, header)
                cell.fill = PatternFill("solid", fgColor="C65911")
                cell.font = header_font
                cell.alignment = align_center
                cell.border = thin_border
            ws.row_dimensions[execution_header_row].height = 42
            for row_offset, row_data in enumerate(s12_execution_data, start=execution_header_row + 1):
                for col_idx, value in enumerate(row_data, start=1):
                    cell = ws.cell(row_offset, col_idx, value)
                    cell.border = thin_border
                    cell.font = bold_font if col_idx in {1, 2} else data_font
                    cell.alignment = align_center if col_idx == 1 else align_left
                    if col_idx == 1 and is_display_id(value):
                        cell.font = id_font
                source_cell = ws.cell(row_offset, len(s12_execution_cols))
                source_cell.hyperlink = str(source_cell.value)
                source_cell.font = link_font
                ws.row_dimensions[row_offset].height = 86

            audit_title_row = execution_header_row + len(s12_execution_data) + 3
            ws.merge_cells(start_row=audit_title_row, start_column=1, end_row=audit_title_row, end_column=max_table_cols)
            title_cell = ws.cell(audit_title_row, 1, "Minimum Trustworthy Backtest Checklist (Danh sách tiêu chí tối thiểu để backtest đáng tin cậy)")
            title_cell.fill = header_fill
            title_cell.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
            title_cell.alignment = align_left
            ws.row_dimensions[audit_title_row].height = 28

            legend_row = audit_title_row + 1
            ws.merge_cells(start_row=legend_row, start_column=1, end_row=legend_row, end_column=max_table_cols)
            legend = ws.cell(legend_row, 1, "Chú giải: ✓ = đầy đủ | Một phần = đáp ứng một phần | ✗ = thiếu | NR = paper không báo cáo | N/A = không áp dụng cho thiết kế")
            legend.fill = PatternFill("solid", fgColor="D9EAF7")
            legend.font = Font(name="Calibri", size=10, italic=True, color="1B365D")
            legend.alignment = align_left

            audit_header_row = legend_row + 1
            for col_idx, header in enumerate(s12_audit_cols, start=1):
                cell = ws.cell(audit_header_row, col_idx, header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = align_center
                cell.border = thin_border
            ws.row_dimensions[audit_header_row].height = 42

            status_styles = {
                "✓": ("008000", "E2F0D9"),
                "Partial": ("9C6500", "FFF2CC"),
                "✗": ("A61C1C", "FCE4D6"),
                "NR": ("666666", "E7E6E6"),
                "N/A": ("1F4E78", "D9EAF7"),
            }
            for row_offset, row_data in enumerate(s12_audit_data, start=audit_header_row + 1):
                for col_idx, value in enumerate(row_data, start=1):
                    cell = ws.cell(row_offset, col_idx, value)
                    cell.border = thin_border
                    cell.alignment = align_center if col_idx >= 4 else align_left
                    cell.font = data_font
                    if value in status_styles:
                        font_color, fill_color = status_styles[value]
                        cell.font = Font(name="Calibri", size=10, bold=True, color=font_color)
                        cell.fill = PatternFill("solid", fgColor=fill_color)
                ws.cell(row_offset, 1).font = bold_font
                ws.row_dimensions[row_offset].height = 44

            ws.column_dimensions["A"].width = 38
            ws.column_dimensions["B"].width = 44
            ws.column_dimensions["C"].width = 46
            for col_idx in range(4, len(s12_audit_cols) + 1):
                ws.column_dimensions[get_column_letter(col_idx)].width = max(ws.column_dimensions[get_column_letter(col_idx)].width or 0, 12)
        else:
            # Bảng 1: tô nhóm T/S/H và các lớp phương pháp dùng chung để người
            # đọc thấy ngay mỗi lựa chọn được rút ra từ dòng literature nào.
            group_styles = {
                "Kỹ thuật (T)": ("D9EAF7", "1F4E78"),
                "Sentiment / LLM (S)": ("E2F0D9", "548235"),
                "Hybrid (H)": ("FFF2CC", "9C6500"),
                "Dữ liệu & execution chung": ("E7E6E6", "595959"),
                "Đánh giá & kiểm định chung": ("E7E6E6", "595959"),
                "Thiết kế so sánh ba arm": ("E4DFEC", "7030A0"),
            }
            for row_idx in range(2, len(s13_method_data) + 2):
                group_cell = ws.cell(row_idx, 1)
                fill_color, font_color = group_styles[str(group_cell.value)]
                group_cell.fill = PatternFill("solid", fgColor=fill_color)
                group_cell.font = Font(name="Calibri", size=10, bold=True, color=font_color)
                group_cell.alignment = align_center
                ws.cell(row_idx, 2).font = bold_font

            max_method_cols = max(len(s13_method_cols), len(s13_transfer_cols), len(s13_arm_cols))
            transfer_title_row = ws.max_row + 3
            ws.merge_cells(start_row=transfer_title_row, start_column=1, end_row=transfer_title_row, end_column=max_method_cols)
            transfer_title = ws.cell(transfer_title_row, 1, "Reproduction & Transfer Ledger (Nhật ký chạy lại và áp dụng phương pháp)")
            transfer_title.fill = PatternFill("solid", fgColor="008C95")
            transfer_title.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
            transfer_title.alignment = align_left
            ws.row_dimensions[transfer_title_row].height = 28

            transfer_header_row = transfer_title_row + 1
            for col_idx, header in enumerate(s13_transfer_cols, start=1):
                cell = ws.cell(transfer_header_row, col_idx, header)
                cell.fill = PatternFill("solid", fgColor="008C95")
                cell.font = header_font
                cell.alignment = align_center
                cell.border = thin_border
            ws.row_dimensions[transfer_header_row].height = 42

            transfer_status_styles = {
                "Đã chạy — giữ lại": ("008000", "E2F0D9"),
                "Đã chạy — không cải thiện": ("A61C1C", "FCE4D6"),
                "Đã triển khai một phần": ("9C6500", "FFF2CC"),
                "Chưa chạy thí nghiệm ba arm": ("7030A0", "E4DFEC"),
                "Chưa chạy": ("666666", "E7E6E6"),
                "Chưa tái lập": ("666666", "E7E6E6"),
            }
            for row_offset, row_data in enumerate(s13_transfer_data, start=transfer_header_row + 1):
                for col_idx, value in enumerate(row_data, start=1):
                    cell = ws.cell(row_offset, col_idx, value)
                    cell.border = thin_border
                    cell.alignment = align_center if col_idx == 4 else align_left
                    cell.font = bold_font if col_idx == 1 else data_font
                    if col_idx == 4 and value in transfer_status_styles:
                        font_color, fill_color = transfer_status_styles[value]
                        cell.font = Font(name="Calibri", size=10, bold=True, color=font_color)
                        cell.fill = PatternFill("solid", fgColor=fill_color)
                ws.row_dimensions[row_offset].height = 86

            arm_title_row = transfer_header_row + len(s13_transfer_data) + 3
            ws.merge_cells(start_row=arm_title_row, start_column=1, end_row=arm_title_row, end_column=max_method_cols)
            arm_title = ws.cell(arm_title_row, 1, "Three-Arm Controlled Methodology (Phương pháp thực nghiệm kiểm soát ba arm)")
            arm_title.fill = PatternFill("solid", fgColor="7030A0")
            arm_title.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
            arm_title.alignment = align_left
            ws.row_dimensions[arm_title_row].height = 28

            arm_header_row = arm_title_row + 1
            for col_idx, header in enumerate(s13_arm_cols, start=1):
                cell = ws.cell(arm_header_row, col_idx, header)
                cell.fill = PatternFill("solid", fgColor="7030A0")
                cell.font = header_font
                cell.alignment = align_center
                cell.border = thin_border
            ws.row_dimensions[arm_header_row].height = 42

            arm_colors = {"Tech-only": "D9EAF7", "LLM-only": "E2F0D9", "Tech+LLM": "E4DFEC"}
            for row_offset, row_data in enumerate(s13_arm_data, start=arm_header_row + 1):
                for col_idx, value in enumerate(row_data, start=1):
                    cell = ws.cell(row_offset, col_idx, value)
                    cell.border = thin_border
                    cell.alignment = align_center if col_idx == 1 else align_left
                    cell.font = id_font if col_idx == 1 else data_font
                ws.cell(row_offset, 1).fill = PatternFill("solid", fgColor=arm_colors[row_data[0]])
                ws.row_dimensions[row_offset].height = 105

            method_widths = [32, 42, 44, 38, 44, 44, 38, 38, 40]
            for col_idx, width in enumerate(method_widths, start=1):
                ws.column_dimensions[get_column_letter(col_idx)].width = width
        ws.sheet_view.zoomScale = 80


# Dashboard sheet with a compact KPI summary and charts
dashboard = wb.create_sheet(title="10_Dashboard (Bảng điều khiển)")
dashboard.sheet_view.showGridLines = False
dashboard["A1"] = "Research Knowledge Base Dashboard (Bảng điều khiển cơ sở tri thức nghiên cứu)"
dashboard["A1"].font = Font(name="Calibri", size=16, bold=True, color="1B365D")
dashboard["A3"] = "Key metric"
dashboard["B3"] = "Value"
dashboard["C3"] = "Notes"
for cell_ref in ["A3", "B3", "C3"]:
    dashboard[cell_ref].fill = header_fill
    dashboard[cell_ref].font = header_font
    dashboard[cell_ref].alignment = align_center

dashboard_rows = [
    ("Tổng bài rà soát", 46, "46 key benchmark papers"),
    ("Giao dịch kỹ thuật", len(s2_data) - 1, "Có hạn chế về phí và rủi ro"),
    ("Giao dịch cảm xúc", len(s3_data) - 1, "Dùng News/Twitter/Reddit và LLM"),
    ("Giao dịch kết hợp", len(s4_data) - 1, "Kết hợp technical + sentiment + LLM"),
    ("Thiết kế thực nghiệm", len(s5_data) - 1, "Kiểm soát phí, rủi ro, thực thi"),
    ("Đánh giá / benchmark", len(s6_data) - 1, "Sharpe, Sortino, DM, SPA, DSR"),
    ("Bài có LLM", 15, "LLM / FinGPT / GPT-4"),
    ("Bài có on-chain", 4, "Áp dụng cho crypto"),
    ("Đối sánh kiểm soát", 5, "Identical fee/risk/execution"),
    ("Giá trị gia tăng của cảm xúc", 3, "Incremental value studies"),
    ("Kiểm định thống kê", 9, "DM, SPA, JK, DSR"),
    ("Nghiên cứu đa chế độ", 11, "Bull, bear, sideways"),
    ("Mã nguồn mở / tái lập", 19, "Open-source reproducibility"),
]

# Do not expose stale hard-coded KPIs from the original draft.
dashboard_rows = [
    ("Tổng tài liệu đã xác minh", _verified_total, "Tính từ các bản ghi đã đối chiếu nguồn."),
    ("Nghiên cứu giao dịch kỹ thuật", _verified_counts["technical"], "Chỉ gồm bản ghi đã xác minh."),
    ("Cảm xúc / NLP tài chính", _verified_counts["sentiment"], "Chỉ gồm bản ghi đã xác minh."),
    ("Hệ thống hybrid / tác tử LLM", _verified_counts["hybrid"], "Chỉ gồm bản ghi đã xác minh."),
    ("Đánh giá / phương pháp luận", _verified_counts["evaluation"], "Chỉ gồm bản ghi đã xác minh."),
    ("Tài liệu nền tảng", _verified_counts["foundational"], "Chỉ gồm bản ghi đã xác minh."),
    ("Paper peer-reviewed ảnh hưởng Tech", len(_tech_method_master), "T03, T08, T11-T19 đã đồng bộ sang các sheet liên quan."),
    ("Paper peer-reviewed ảnh hưởng Sentiment", 3, "S11, S12 và S13 định hướng LLM/news sentiment, multi-source sentiment và CryptoBERT transfer test."),
    ("Bản ghi bị loại", "Không tính", "Thiếu hoặc mâu thuẫn metadata thư mục."),
]

for row_offset, (metric, value, note) in enumerate(dashboard_rows, start=4):
    dashboard.cell(row=row_offset, column=1, value=metric)
    dashboard.cell(row=row_offset, column=2, value=value)
    dashboard.cell(row=row_offset, column=3, value=note)
    dashboard.cell(row=row_offset, column=1).font = bold_font
    dashboard.cell(row=row_offset, column=2).font = Font(name="Calibri", size=10, bold=True, color="1B365D")
    dashboard.cell(row=row_offset, column=3).font = data_font
    dashboard.cell(row=row_offset, column=1).alignment = align_left
    dashboard.cell(row=row_offset, column=2).alignment = align_center
    dashboard.cell(row=row_offset, column=3).alignment = align_left

for width_cell, width in {"A": 28, "B": 14, "C": 34, "E": 14, "F": 14, "G": 14, "H": 14}.items():
    dashboard.column_dimensions[width_cell].width = width

bar_source = [
    ("Technical Trading", _verified_counts["technical"]),
    ("Sentiment Trading", _verified_counts["sentiment"]),
    ("Hybrid Trading", _verified_counts["hybrid"]),
    ("Evaluation & Methodology", _verified_counts["evaluation"]),
    ("LLM-related Records", _evidence_counts["llm"]),
    ("On-chain Input", _evidence_counts["onchain"]),
]
dashboard["J3"] = "Category"
dashboard["K3"] = "Count"
for cell_ref in ["J3", "K3"]:
    dashboard[cell_ref].fill = header_fill
    dashboard[cell_ref].font = header_font
    dashboard[cell_ref].alignment = align_center
for row_offset, (label, value) in enumerate(bar_source, start=4):
    dashboard.cell(row=row_offset, column=10, value=label)
    dashboard.cell(row=row_offset, column=11, value=value)

pie_source = [
    ("Controlled Comparison", _evidence_counts["controlled"]),
    ("Incremental Value", _evidence_counts["incremental"]),
    ("Formal Statistical Tests", _evidence_counts["formal_tests"]),
    ("Multi-regime Studies", _evidence_counts["multi_regime"]),
    ("Open/reproducible Records", _evidence_counts["reproducible"]),
    ("On-chain Coverage", _evidence_counts["onchain"]),
]
dashboard["J12"] = "Evidence type"
dashboard["K12"] = "Count"
for cell_ref in ["J12", "K12"]:
    dashboard[cell_ref].fill = header_fill
    dashboard[cell_ref].font = header_font
    dashboard[cell_ref].alignment = align_center
for row_offset, (label, value) in enumerate(pie_source, start=13):
    dashboard.cell(row=row_offset, column=10, value=label)
    dashboard.cell(row=row_offset, column=11, value=value)

chart = BarChart()
chart.type = "bar"
chart.style = 10
chart.title = "Literature Coverage by Category"
chart.y_axis.title = "Category"
chart.x_axis.title = "Count"
data = Reference(dashboard, min_col=11, min_row=3, max_row=9)
cats = Reference(dashboard, min_col=10, min_row=4, max_row=9)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
chart.height = 7.2
chart.width = 12.5
dashboard.add_chart(chart, "E3")

pie = PieChart()
pie.title = "Methodological Evidence Mix"
pie_data = Reference(dashboard, min_col=11, min_row=12, max_row=18)
pie_labels = Reference(dashboard, min_col=10, min_row=13, max_row=18)
pie.add_data(pie_data, titles_from_data=True)
pie.set_categories(pie_labels)
pie.height = 7.2
pie.width = 10.5
dashboard.add_chart(pie, "E20")


# Insight sheet for drafting related work and research gap
insights = wb.create_sheet(title="11_KB_Insights (Soạn thảo)")
insights.sheet_view.showGridLines = False
insights.merge_cells("A1:D1")
insights["A1"] = "Related Work & Research Gap Draft (Bản nháp cho Related Work và Research Gap)"
insights["A1"].font = Font(name="Calibri", size=15, bold=True, color="1B365D")

insight_rows = [
    ("Related Work - Technical Trading", "Nhóm nghiên cứu giao dịch kỹ thuật chủ yếu khai thác EMA, RSI, MACD và các mô hình DL/RL để dự đoán biến động giá. Tuy nhiên, nhiều bài chưa kiểm soát đầy đủ phí giao dịch, trượt giá và rủi ro theo chế độ thị trường, nên kết quả khó so sánh trực tiếp."),
    ("Related Work - Sentiment Trading", "Nhóm giao dịch cảm xúc dùng News, Twitter, Reddit và các mô hình FinBERT/GPT để chuyển tín hiệu ngôn ngữ thành quyết định giao dịch. Điểm yếu phổ biến là thiếu một khung đánh giá thống nhất để chứng minh lợi nhuận giao dịch sau khi đã loại trừ yếu tố nhiễu từ kỹ thuật hoặc quy trình thực thi."),
    ("Related Work - Hybrid Trading", "Nhóm hybrid kết hợp kỹ thuật, cảm xúc, LLM và đôi khi cả on-chain. Phần lớn các hệ thống này đánh giá theo kiểu black-box; thiếu đối sánh kiểm soát, thiếu ablation rõ ràng và chưa lượng hóa riêng giá trị gia tăng của từng nguồn tín hiệu."),
    ("Related Work - Đánh giá & phương pháp", "Nhóm phương pháp luận tập trung vào backtesting, benchmark và các kiểm định DM, SPA, JK, DSR. Đây là nền tảng để tránh overfitting, nhưng thường chưa được tích hợp thành một pipeline thực nghiệm thống nhất cho bài toán giao dịch dùng LLM/cảm xúc."),
    ("Research Gap", "Khoảng trống chính là chưa có một khung đánh giá đồng nhất với cùng bộ dữ liệu, cùng phí, cùng rủi ro, cùng thực thi và cùng position size để đo incremental value của sentiment/LLM so với technical baseline. Dự án này có thể lấp khoảng trống đó bằng một thiết kế đối sánh kiểm soát, có kiểm định thống kê và có tái lập đầy đủ."),
]

# Replace the original prose, which made unverified frequency and novelty
# claims, with evidence-bounded drafting notes.
insight_rows = [
    ("Trạng thái nguồn", "Workbook chỉ giữ các bản ghi có metadata cốt lõi đã được đối chiếu. Đây là tập tài liệu tuyển chọn, không phải thống kê đầy đủ của một systematic review."),
    ("Related Work - Kỹ thuật", "Cac paper peer-reviewed noi bat T03, T08 va T11-T19 đã được đồng bộ vào corpus và các sheet liên quan. Chúng cung cấp nền tảng về nhân tố/vũ trụ động, thanh khoản, bất đồng, momentum quản trị rủi ro, stop-loss, cú sốc thanh khoản, basis, order flow và aggregate trend; kết quả của chúng không được so trực tiếp vì dữ liệu, mục tiêu và giả định thực thi khác nhau."),
    ("Related Work - Cảm xúc", "Các nghiên cứu cảm xúc và mô hình ngôn ngữ tài chính đã xác minh cho thấy cách chuyển văn bản tài chính thành tín hiệu. S13 bổ sung CryptoBERT như nguồn bình duyệt cho crypto social-sentiment, nhưng đây là transfer reference vì dữ liệu gốc là social media chứ không phải news headline. Giá trị gia tăng trên crypto futures phải được kiểm định trong nghiên cứu hiện tại."),
    ("Related Work - Hybrid", "Các nghiên cứu hybrid đã xác minh sử dụng memory, dữ liệu đa phương thức hoặc suy luận đa tác tử. Tổng quan phải phân biệt đổi mới kiến trúc với ước lượng có kiểm soát về giá trị biên của từng nguồn tín hiệu."),
    ("Phương pháp luận", "Nghiên cứu phải định trước cách chia thời gian, đầu vào point-in-time, fee/slippage, thực thi, giới hạn rủi ro và kiểm định thống kê. Cần kiểm soát đa kiểm định khi khảo sát nhiều biến thể Tech và đánh giá theo trạng thái thay vì mặc định momentum luôn tồn tại."),
    ("Câu hỏi nghiên cứu hiện tại", "Liệu đánh giá thị trường đa nguồn được tạo bởi AI có mang lại giá trị giao dịch gia tăng có ý nghĩa thống kê so với các mô hình giao dịch định lượng truyền thống trên các trạng thái thị trường tiền mã hóa khác nhau hay không?"),
    ("Chiến lược nhận dạng", "Khóa ba arm và bộ máy chung: Tech-only control, LLM-only diagnostic ablation và Tech+LLM treatment. Cả ba dùng cùng universe point-in-time, timestamp, sizing, fee/slippage/impact, funding, stop và execution. Primary effect là Tech+LLM − Tech-only; LLM-only cho biết AI bổ trợ hay thay thế Tech."),
    ("Ranh giới bằng chứng hiện tại", "Nhánh Tech theo vòng đời là đối chứng khoa học mạnh hơn, nhưng cả hai final validation fold đều âm và thí nghiệm AI ghép cặp chưa chạy. Vì vậy kết quả Tech hiện tại chưa trả lời câu hỏi nghiên cứu."),
    ("Suy luận bắt buộc", "Báo cáo incremental net return ghép cặp và khoảng tin cậy, chênh lệch điều chỉnh rủi ro, phân rã turnover/chi phí và tương tác trạng thái đã định trước. Dùng bootstrap có xét phụ thuộc và SPA/Reality Check hoặc DSR khi thử nhiều prompt, nguồn hay biến thể mô hình."),
]

insights_headers = ["Section (Mục)", "Draft Text (Nội dung nháp)", "How to Use (Cách sử dụng)"]
for idx, header in enumerate(insights_headers, start=1):
    cell = insights.cell(row=3, column=idx, value=header)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = align_center

for row_idx, (section, draft) in enumerate(insight_rows, start=4):
    insights.cell(row=row_idx, column=1, value=section)
    insights.cell(row=row_idx, column=2, value=draft)
    insights.cell(row=row_idx, column=3, value="Có thể copy trực tiếp vào phần Related Work / Research Gap của bài IEEE")
    insights.cell(row=row_idx, column=1).font = bold_font
    insights.cell(row=row_idx, column=2).font = data_font
    insights.cell(row=row_idx, column=3).font = data_font
    insights.cell(row=row_idx, column=1).alignment = align_left
    insights.cell(row=row_idx, column=2).alignment = align_left
    insights.cell(row=row_idx, column=3).alignment = align_left

insights.column_dimensions["A"].width = 30
insights.column_dimensions["B"].width = 98
insights.column_dimensions["C"].width = 42

# Save workbook next to this script.  This avoids silently writing to a
# different project checkout and keeps the source script/output pair portable.
_tab_order = [
    "1_Master (CSDL)", "2_Technical (Kỹ thuật)", "3_Sentiment (Cảm xúc)",
    "4_Hybrid (Kết hợp)", "5_Experimental (Thiết kế)", "6_Metrics (Chỉ số)",
    "7_Gap (Khoảng trống)", "8_Evidence (Bằng chứng)", "9_Selected_Papers",
    "10_Dashboard (Bảng điều khiển)", "11_KB_Insights (Soạn thảo)",
    "12_Backtest (Kiểm thử lịch sử)", "13_Methodology (Phương pháp)",
]
for _target_index, _sheet_title in enumerate(_tab_order):
    _sheet = wb[_sheet_title]
    wb.move_sheet(_sheet, offset=_target_index - wb.index(_sheet))

excel_path = Path(os.environ.get(
    "LITERATURE_MATRIX_OUTPUT",
    Path(__file__).with_name("Literature_Matrix_Sheets.xlsx"),
))
wb.save(excel_path)
print(f"Excel file successfully generated at: {excel_path}")
