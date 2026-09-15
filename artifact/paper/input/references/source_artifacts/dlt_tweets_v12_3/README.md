---
language:
- en
license: cc-by-nc-4.0
size_categories:
- 10M<n<100M
task_categories:
- text-generation
pretty_name: Distributed Ledger Technology (DLT) / Blockchain Tweets
dataset_info:
  features:
  - name: timestamp
    dtype: large_string
  - name: tweet
    dtype: large_string
  - name: language
    dtype: string
  - name: total_tokens
    dtype: int64
  - name: sentiment_class
    list:
    - name: label
      dtype: string
    - name: score
      dtype: float64
  - name: sentiment_label
    dtype: string
  - name: sentiment_score
    dtype: float64
  - name: confidence_level
    dtype: string
  - name: year
    dtype: string
  splits:
  - name: train
    num_bytes: 6772592588.26901
    num_examples: 22033090
  download_size: 3584763878
  dataset_size: 6772592588.26901
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
tags:
- Blockchain
- DLT
- Cryptocurrencies
- Bitcoin
- Ethereum
- Crypto
---

# DLT-Tweets

<p align="center">
  <a href="https://huggingface.co/papers/2602.22045"><b>[Paper]</b></a> • 
  <a href="https://github.com/dlt-science/DLT-Corpus"><b>[Code]</b></a>
</p>

## Dataset Description

### Dataset Summary

DLT-Tweets is a large-scale corpus of social media posts related to Distributed Ledger Technology (DLT). This dataset is part of the larger DLT-Corpus collection, designed to support NLP research, social computing studies, and public discourse analysis in the DLT domain. It was introduced in the paper [DLT-Corpus: A Large-Scale Text Collection for the Distributed Ledger Technology Domain](https://huggingface.co/papers/2602.22045).

The dataset contains **22.03 million social media documents** with **1,120 million tokens** (1.12 billion tokens), spanning posts from **2013 to mid-2023**. All documents are in English and have been processed to protect user privacy.

This dataset is part of the DLT-Corpus collection. For the complete corpus including scientific literature and patent data, see: https://huggingface.co/collections/ExponentialScience/dlt-corpus-68e44e40d4e7a3bd7a224402

### Languages

English (en)

## Dataset Structure

### Data Fields

Each post in the dataset contains the following fields:

- **tweet**: Full text content of the social media post
- **timestamp**: Date and time when the post was created
- **year**: Year the post was created
- **language**: Language code (all entries are 'en' for English)
- **total_tokens**: Total number of tokens in the tweet
- **sentiment_class**: Classified sentiment category (e.g., positive, negative, neutral)
- **sentiment_label**: Detailed sentiment label
- **sentiment_score**: Numerical sentiment score
- **confidence_level**: Confidence level of the sentiment classification

**Privacy Protection:** All usernames have been removed from the tweet text to protect user privacy.

### Data Splits

This is a single corpus without predefined splits. Users should create their own train/validation/test splits based on their specific research needs. Consider temporal splits for time-series analyses or studying how discourse evolves over time.

## Dataset Creation

### Curation Rationale

DLT-Tweets was created to address the lack of large-scale social media corpora for studying public discourse, sentiment, and information diffusion in the Distributed Ledger Technology domain. Social media data provides unique insights into:

- Public perception and sentiment toward DLT technologies
- Real-time reactions to DLT events (market movements, hacks, regulations)
- Information spreading patterns and viral content
- Community dynamics and influencer networks
- The gap between technical development and public understanding

### Source Data

#### Data Collection

Social media posts were aggregated from:
1. **Previously published academic datasets** focused on cryptocurrency and blockchain topics
2. **Publicly available industry sources** that collected DLT-related social media data

All data was collected **before Twitter/X's 2023 API restrictions** that limited academic research access. The collection complies with platform Terms of Service that were in effect at the time of collection, which explicitly permitted academic research use.

#### Data Processing

The collection process involved:

1. **Aggregation**: Combining multiple sources while tracking provenance
2. **Username removal**: Removing all @username mentions to protect privacy
3. **Duplicate detection**: Identifying and removing duplicate posts
4. **Language filtering**: Filtering for English-language posts using language detection
5. **Sentiment analysis**: Adding sentiment labels using automated classification
6. **Quality filtering**: Removing extremely short posts
7. **Privacy protection**: Ensuring no identifying information remains

### Annotations

The dataset includes automated sentiment annotations generated using sentiment analysis models. These provide:
- Sentiment class (positive, negative, neutral)
- Sentiment scores and confidence levels

#### Annotation Process

Sentiment was determined using automated sentiment analysis models trained on social media text.

### Personal and Sensitive Information

**Privacy Measures:**

- **All usernames have been removed** from the text content
- No profile information, user IDs, or biographical data is included
- Only the text content and basic engagement metrics are retained
- Posts are not linkable back to specific individuals

**Residual Considerations:**

- Some posts may contain self-disclosed information in the text itself
- Famous individuals or organizations might be identifiable through context
- Users should not attempt to re-identify individuals from this dataset

## Considerations for Using the Data

### Social Impact of Dataset

This dataset can enable:

- **Positive impacts**: Understanding public discourse, detecting misinformation, studying information diffusion, analyzing sentiment trends, improving public communication about DLT
- **Potential negative impacts**: Could be misused for market manipulation, creating targeted misinformation campaigns, or developing manipulative trading systems

**Researchers should implement appropriate safeguards when working with this data.**

### Discussion of Biases

Potential biases include:

- **Platform bias**: Only Twitter/X data is included; other social platforms are not represented
- **User bias**: Social media users are not representative of the general population
- **Language bias**: Only English-language posts are included
- **Temporal bias**: More recent years have more posts due to platform growth and increased DLT interest
- **Topic bias**: Certain events (market crashes, hacks) may generate disproportionate discussion
- **Bot bias**: Despite filtering, some bot-generated content may remain
- **Geographic bias**: English-speaking regions are over-represented

### Other Known Limitations

- **Temporal gap**: No posts after mid-2023 due to platform API restrictions
- **Context loss**: Username removal eliminates ability to analyze user behavior or influence
- **Incomplete threads**: Some conversation threads may be incomplete due to filtering
- **Sarcasm and irony**: Social media posts often use language that is difficult for NLP models to interpret
- **Misinformation**: Dataset may contain false or misleading claims about DLT
- **Market sensitivity**: Discussions may reflect market manipulation or coordinated campaigns
- **Evolving terminology**: DLT terminology evolves rapidly; older posts may use outdated terms

## Additional Information

### Dataset Curators

Walter Hernandez Cruz, Peter Devine, Nikhil Vadgama, Paolo Tasca, Jiahua Xu

### Licensing Information

**CC-BY-NC 4.0** (Creative Commons Attribution-NonCommercial 4.0 International)

This dataset is released under CC-BY-NC 4.0 for **research purposes only**. 

**Key terms:**
- **Attribution required**: You must give appropriate credit to the dataset creators
- **Non-commercial use**: Commercial use is not permitted under this license
- **Academic research**: The dataset is intended for academic and non-profit research

**Legal basis:** Data was collected before changes in Twitter/X's Terms of Service in 2023, under terms that explicitly permitted academic research use. See:
- https://x.com/en/tos/previous/version_18
- https://x.com/en/tos/previous/version_17

For more information on CC-BY-NC 4.0, see: https://creativecommons.org/licenses/by-nc/4.0/

### Citation Information

```bibtex
@misc{hernandez2026dlt-corpus,
      title={DLT-Corpus: A Large-Scale Text Collection for the Distributed Ledger Technology Domain}, 
      author={Walter Hernandez Cruz and Peter Devine and Nikhil Vadgama and Paolo Tasca and Jiahua Xu},
      year={2026},
      eprint={2602.22045},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2602.22045}, 
}
```