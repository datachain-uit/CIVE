import unittest
from datetime import datetime, timezone

from build_fulltext_market_impact_panel_v5 import (
    btc_relevance,
    next_4h_open_ms,
    select_source_diverse,
)


class FulltextMarketImpactPanelV5Tests(unittest.TestCase):
    def test_next_open_is_strictly_after_publication(self):
        timestamp = datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(next_4h_open_ms(timestamp), int(datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc).timestamp() * 1000))

    def test_btc_category_has_priority(self):
        self.assertEqual(btc_relevance({"categories": "ETH|BTC"}, "", ""), 2)
        self.assertEqual(btc_relevance({}, "Bitcoin ETF", ""), 1)
        self.assertEqual(btc_relevance({}, "Ethereum", "staking"), 0)

    def test_selection_prioritizes_source_diversity(self):
        items = [
            {"btc_relevance": 2, "published_at": "1", "article_id": "a", "source": "x"},
            {"btc_relevance": 2, "published_at": "2", "article_id": "b", "source": "x"},
            {"btc_relevance": 1, "published_at": "3", "article_id": "c", "source": "y"},
        ]
        self.assertEqual([item["article_id"] for item in select_source_diverse(items, 2)], ["a", "c"])


if __name__ == "__main__":
    unittest.main()
