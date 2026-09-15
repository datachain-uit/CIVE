import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from run_minilm_external_impact_v4 import (
    aggregate_article_embeddings,
    auc,
    date_cluster_bootstrap,
    load_external_articles,
    ridge_apply,
    ridge_fit,
)


class ExternalImpactV4Tests(unittest.TestCase):
    def test_article_regroup_dedupes_and_caps_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["datetime", "text", "url", "label"])
                writer.writeheader()
                for text in ("title", "paragraph", "paragraph", "tail"):
                    writer.writerow({"datetime": "2023-01-01", "text": text, "url": "https://x/a/", "label": 1})
            records = load_external_articles(path, 2)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["chunks"], ["title", "paragraph"])
        self.assertEqual(records[0]["available_unique_chunks"], 3)

    def test_article_embedding_is_mean_then_normalize(self):
        articles = [{"chunks": ["a", "b"]}, {"chunks": ["c"]}]
        chunks = np.asarray([[1.0, 0.0], [0.0, 1.0], [2.0, 0.0]])
        result = aggregate_article_embeddings(articles, chunks)
        self.assertTrue(np.allclose(result[0], [2 ** -0.5, 2 ** -0.5]))
        self.assertTrue(np.allclose(result[1], [1.0, 0.0]))

    def test_auc_handles_ties(self):
        y = np.asarray([0, 0, 1, 1])
        score = np.asarray([0.0, 0.5, 0.5, 1.0])
        self.assertAlmostEqual(auc(y, score), 0.875)

    def test_ridge_is_train_only(self):
        x = np.asarray([[0.0], [1.0], [2.0]])
        y = np.asarray([0.0, 0.0, 1.0])
        model = ridge_fit(x, y, 1.0)
        first = ridge_apply(model, np.asarray([[3.0]]))
        second = ridge_apply(model, np.asarray([[3.0], [3000.0]]))
        self.assertAlmostEqual(first[0], second[0])

    def test_date_cluster_bootstrap_is_seeded(self):
        folds = [[
            {"information_date": "2023-01-01", "label": 0, "prediction": 0.0},
            {"information_date": "2023-01-02", "label": 1, "prediction": 1.0},
            {"information_date": "2023-01-03", "label": 0, "prediction": 0.0},
            {"information_date": "2023-01-04", "label": 1, "prediction": 1.0},
        ]]
        left = date_cluster_bootstrap(folds, 100, 9)
        right = date_cluster_bootstrap(folds, 100, 9)
        self.assertEqual(left, right)
        self.assertGreater(left["auc_95_ci"][0], 0.5)


if __name__ == "__main__":
    unittest.main()
