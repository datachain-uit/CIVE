from __future__ import annotations

import numpy as np

from eth_transfer_v17_common import block_indices, is_eth_event, ridge_predict


def main() -> None:
    assert is_eth_event({"affected_assets": ["Ethereum"]})
    assert is_eth_event({"affected_assets": ["ETH"]})
    assert is_eth_event({"affected_assets": ["Ether"]})
    assert not is_eth_event({"affected_assets": ["Bitcoin", "Crypto"]})
    x = np.arange(20, dtype=float).reshape(-1, 1)
    y = 2.0 * x[:, 0] + 1.0
    pred = ridge_predict(x[:15], y[:15], x[15:], alpha=0.1)
    assert pred.shape == (5,) and np.all(np.isfinite(pred))
    rng = np.random.default_rng(7)
    idx = block_indices(20, 7, rng)
    assert len(idx) == 20 and idx.min() >= 0 and idx.max() < 20
    print("ETH transfer v17 helper tests passed")


if __name__ == "__main__":
    main()
