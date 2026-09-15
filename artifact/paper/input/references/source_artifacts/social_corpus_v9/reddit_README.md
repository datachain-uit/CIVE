---
license: mit
tags:
- dataset
- bitcoin
- text-classification
- sentiment-analysis
size_categories:
- 1K<n<10K
task_categories:
- text-classification
source_datasets:
  - myself
---
# Leveraging LLMs for Informed Bitcoin Trading Decisions: Prompting with Social and News Data Reveals Promising Predictive Abilities

The work was carried out by:

- [Danilo Corsi](https://github.com/CorsiDanilo)
- [Cesare Campagnano](https://github.com/caesar-one)

## Description
This project investigates the potential of leveraging Large Language Models (LLMs) to support Bitcoin traders. Specifically, we analyze the correlation between Bitcoin price movements and sentiment expressed in news headlines, posts, and comments on social media.
We build a novel, large-scale dataset that aggregates various features related to Bitcoin and its price over time, spanning from 2016 to 2024, and includes data from news outlets, social media posts, and comments.

## Dataset

The `merged` folder contains the raw dataset without annotation of LLMs (price data, blockchain, and sentiment indices)

The `annotated` folder contains the original dataset with the annotation of the respective LLMs.

## Merged Dataset Row Example

```
timestamp                        2021-07-02
open                             33519.467449
close                            33774.0
high                             33983.0
low                              33428.0
volume                           272.657315
blocks-size                      352740.54519
avg-block-size                   1.403917
n-transactions-total             652854116.0
n-transactions-per-block         2095.2
hash-rate                        89177797.479268
difficulty                       19932791027263.0
miners-revenue                   20787750.550889
transaction-fees-usd             2064573.722375
n-unique-addresses               532456.0
n-transactions                   188568.0
estimated-transaction-volume-usd 4454956968.426739
total-bitcoins                   18746131.25
market-cap                       619775218321.874878
fng_value                        0.21
fng_value_classification         0.0
fng_sentiment                    negative
cbbi_value                       0.61
cbbi_sentiment                   positive
cointelegraph                    [[68663, 'altcoin-roundup-...]]
bitcoin_news                     [[471442, '2021-07-02 23:...]]
reddit                           [['u/inevitable_username'...]]
avg_current_price                33676.116862
avg_next_price                   33690.25
pct_price_change                 0.041968
trend                            same
```

Where:
- `timestamp`: The specific date and time for the data entry
- `open`: The opening price of Bitcoin at the beginning of the specified period
- `close`: The closing price of Bitcoin at the end of the specified period
- `high`: The highest price reached by Bitcoin during the specified period
- `low`: The lowest price reached by Bitcoin during the specified period
- `volume`: The total volume of Bitcoin traded during the specified period
- `blocks-size`: The total size of all blocks mined during the specified period
- `avg-block-size`: The average size of each block mined during the specified period
- `n-transactions-total`: The cumulative number of Bitcoin transactions ever conducted up to this point
- `n-transactions-per-block`: The average number of transactions included in each block during the specified period
- `hash-rate`: The total computational power used to mine Bitcoin during the specified period, measured in hashes per second
- `difficulty`: A measure of how difficult it is to mine a new block in the Bitcoin blockchain
- `miners-revenue`: The total revenue earned by Bitcoin miners during the specified period, measured in USD
- `transaction-fees-usd`: Total transaction fees paid by users to miners for processing transactions during the specified period
- `n-unique-addresses`: The number of unique Bitcoin addresses that participated in transactions during the specified period
- `n-transactions`: The total number of Bitcoin transactions conducted during the specified period
- `estimated-transaction-volume-usd`: The estimated total value of all Bitcoin transactions conducted during the specified period, measured in USD
- `total-bitcoins`: The total number of Bitcoins that have been mined and are in circulation up to this point
- `market-cap`: The total market capitalization of Bitcoin at the end of the specified period
- `fng_value`: Fear and Greed Index value for Bitcoin on a scale from 0 ("Extreme Fear") to 1 ("Extreme Greed")
- `fng_value_classification`: Classification of the Fear and Greed Index value on a scale from 0 to 4 (0 - "Extreme Fear", 1 - "Fear", 2 - "Neutral", 3 - "Greed", 4 - "Extreme Greed")
- `fng_sentiment`: Sentiment analysis based on the Fear and Greed Index classified as 'positive' if FNG Value ranges from 60 and up, 'negative' if FNG Value ranges from 40 and below, 'neutral' otherwise
- `cbbi_value`: Crypto Bull & Bear Index value on a scale from 0 ("negative") to 1 ("positive")
- `cbbi_sentiment`: Sentiment analysis based on the Crypto Bull & Bear Index classified as 'positive' if CBBI Value ranges from 60 and up, 'negative' if CBBI Value ranges from 40 and below, 'neutral' otherwise
- `cointelegraph`: A list containing news items related to Bitcoin from Cointelegraph
- `bitcoin_news`: A list containing news items related to Bitcoin from Bitcoin News
- `reddit`: A list containing Reddit posts and comments related to Bitcoin
- `avg_current_price`: the average between the opening, closing high and low price of that day
- `avg_next_price`: The value of Avg. Current Price shifted by one position, indicating the average price for the next day
- `pct_price_change`: Percentage of (average) price change of the next day from the previous day (calculated by the difference between Avg. Next Price and Avg. Current Price)
- `trend`: Price trend on the next day compared with the previous day (based on Pct. Price Change), "up" if Pct. Price Change > 2%, "same" if Pct. Price Change <= 2% and Pct. Price Change >= -2%, "down" if Pct. Price Change < -2%

## Annotated Dataset Row Example

```
... <same merged dataset fields> ...
reasoning_text                   The news about Bitcoin's halving...
sentiment_class                  positive
action_class                     buy
action_score                     8.0
```

Where:
- `reasoning_text`: Provides a short explanation, usually a couple of sentences, outlining the reasoning behind the sentiment and trading action decisions made by the model
- `sentiment_class`: Captures the sentiment of the input data, categorized into three possible values: ’positive’, ’neutral’, or ’negative’
- `action_class`: Contains the recommended trading action based on the data, with possible values being ’buy’, ’hold’, or ’sell’
- `action_score`: Indicates the model’s confidence level regarding the suggested action, on a scale from 1 to 10 (where 1 means no confidence, and 10 means extremely confident)

## Use

This dataset is used in the following [GitHub Repository](https://github.com/CorsiDanilo/Leveraging-LLMs-for-Informed-Bitcoin-Trading-Decisions).