"""构建物品内容特征与内容相似图（ETL 之后的第二步）。

产出（data/processed/<dataset>/）：
    item_features.npy          L2 归一化后的多视图物品特征
    item_ids.json              特征行对应的原始 item_id
    item_similarity.parquet    Top-50 物品内容近邻

用法:
    python scripts/01_build_features.py
    python scripts/01_build_features.py --datasets movielens goodbooks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recsys.features import save_features


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasets", nargs="*", default=["movielens", "goodbooks"])
    args = ap.parse_args()

    for ds in args.datasets:
        try:
            stats = save_features(ds)
            print(f"[FEAT] {ds:12s} items={stats['n_items']:>7} "
                  f"dim={stats['dim']:>4} sim_pairs={stats['n_sim_pairs']:>9,}")
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f"[FEAT] {ds} FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
