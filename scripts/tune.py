"""超参搜索：为图模型找出合理的训练配置。

为什么需要
----------
RecBole 的默认超参是面向大数集聚类的，直接套到 MovieLens-small（610 用户）
会明显欠拟合或过拟合。论文实验必须保证各模型在**各自合理配置**下比较，
否则"某模型更优"的结论不成立。这里做小网格搜索，以验证集 NDCG@10 选最优。

用法:
    python scripts/tune.py --models LightGCN SGL --dataset movielens
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recsys.runner import run_one

GRIDS = {
    "LightGCN": {
        "learning_rate": [0.001, 0.003],
        "n_layers": [2, 3],
        "reg_weight": [1e-5, 1e-4],
        "embedding_size": [64],
    },
    "SGL": {
        "learning_rate": [0.001, 0.003],
        "n_layers": [2, 3],
        "reg_weight": [1e-5, 1e-4],
        "embedding_size": [64],
    },
    "NCL": {
        "learning_rate": [0.001],
        "n_layers": [2, 3],
        "reg_weight": [1e-5, 1e-4],
        "embedding_size": [64],
    },
    "FREEDOM": {
        "learning_rate": [0.001, 0.003],
        "n_layers": [2, 3],
        "reg_weight": [1e-5, 1e-4],
        "embedding_size": [64],
    },
}


def grid_of(model: str) -> list[dict]:
    g = GRIDS.get(model)
    if not g:
        return [{}]
    keys = list(g)
    return [dict(zip(keys, vals)) for vals in itertools.product(*[g[k] for k in keys])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=C.PRIMARY_DATASET)
    ap.add_argument("--models", nargs="+", default=["LightGCN", "SGL"])
    ap.add_argument("--epochs", type=int, default=200)
    args = ap.parse_args()

    out_path = C.RESULTS / f"tuning_{args.dataset}.json"
    best: dict[str, dict] = {}
    if out_path.exists():
        best = json.loads(out_path.read_text(encoding="utf-8"))
    all_runs: list[dict] = []

    for model in args.models:
        print(f"\n===== TUNING {model} =====", flush=True)
        cands = grid_of(model)
        model_best = None
        for i, cfg in enumerate(cands, 1):
            print(f"[{i}/{len(cands)}] {cfg}", flush=True)
            try:
                r = run_one(args.dataset, model, cfg, epochs=args.epochs)
                score = r["valid"].get("ndcg@10", 0)
                test_score = r["test"].get("ndcg@10", 0)
                print(f"    valid={score:.4f} test={test_score:.4f} "
                      f"({r['train_seconds']}s)", flush=True)
                all_runs.append({"model": model, "cfg": cfg,
                                 "valid": r["valid"], "test": r["test"],
                                 "seconds": r["train_seconds"]})
                if model_best is None or score > model_best[0]:
                    model_best = (score, cfg, r)
            except Exception as e:  # noqa: BLE001
                print(f"    FAIL {type(e).__name__}: {e}", flush=True)

        if model_best:
            best[model] = {
                "cfg": model_best[1],
                "valid_ndcg@10": model_best[0],
                "test": model_best[2]["test"],
            }
            print(f"  >>> BEST {model}: {model_best[1]} "
                  f"valid={model_best[0]:.4f}", flush=True)

        out_path.write_text(
            json.dumps({"best": best, "runs": all_runs},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
