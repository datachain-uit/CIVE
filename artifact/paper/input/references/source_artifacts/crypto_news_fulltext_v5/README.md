---
license: cc-by-nc-4.0
language:
- en
task_categories:
- text-classification
- text-generation
tags:
- finance
- cryptocurrency
- news
- bitcoin
- ethereum
- time-series
- academic
pretty_name: crypto-news-coindesk-2020-2025
size_categories:
- 10K<n<100K
---
# CoinDesk Cryptocurrency News Dataset (2020–2025)

This dataset contains cryptocurrency-related news articles sourced from **CoinDesk Data**, accessed programmatically via the CryptoCompare API. The dataset is curated and published for academic and research purposes, with a focus on analyzing the relationship between news and cryptocurrency market dynamics.

## Time Period
January 1, 2020 – January 1, 2025

## Content Overview
Each record in the dataset corresponds to a single news article and includes:
- Unique identifiers (e.g., `id`, `guid`)
- Publication timestamp
- Article title and body text
- Source and URL
- Tags and categories
- User engagement indicators (upvotes and downvotes)

The dataset primarily focuses on news related to major cryptocurrencies, including **Bitcoin** and **Ethereum**, while also covering broader cryptocurrency market developments.

## Data Source
- **Data Owner:** CoinDesk Data  
- **Access Method:** CryptoCompare API  

CryptoCompare was used solely as a data access layer. All news content originates from CoinDesk Data.

## Intended Use
This dataset is intended for:
- Academic research
- Cryptocurrency market analysis
- News impact modeling
- Financial time series and forecasting studies

The dataset is not intended for commercial redistribution or resale.

## License and Permissions
This dataset is shared with permission for academic and research use. Users must provide appropriate attribution to both the original data source and the dataset publication.

## Citation
If you use this dataset in your research or publications, please cite **both** of the following:

1. **Original data source**  
   > CoinDesk Data. *Cryptocurrency News Dataset (2020–2025)*. Accessed via the CryptoCompare API.

2. **This Hugging Face dataset**  
   > Fakhari, M. *CoinDesk Cryptocurrency News Dataset (2020–2025)*. Hugging Face Datasets.  
   > https://huggingface.co/datasets/maryamfakhari/coindesk-crypto-news-2020-2025

A formal academic citation (BibTeX) and related research publications will be added in future updates.

## Related Dataset

LLM-generated news-impact annotations derived from this dataset are available in the [CryptoNewsImpact](https://huggingface.co/datasets/maryamfakhari/CryptoNewsImpact) dataset. The annotations include structured information on the expected impact, direction, intensity, and timeframe of news events on cryptocurrency prices.

The two datasets can be linked using the shared `id` field, which enables the original news articles to be matched with their corresponding LLM-generated annotations.
