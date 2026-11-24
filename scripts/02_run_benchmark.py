"""跑基线模型基准表。

用法:
    python scripts/02_run_benchmark.py --dataset movielens
    python scripts/02_run_benchmark.py --dataset bookcrossing --epochs 30
    python scripts/02_run_benchmark.py --dataset movielens --models LightGCN SGL NCL
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recsys.runner import run_benchmark


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=C.PRIMARY_DATASET,
                    choices=list(C.DATASETS))
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    pool = {m: (m, o) for m, _, _, o in C.BASELINE_MODELS}
    if args.models:
        models = [pool[m] for m in args.models if m in pool]
        missing = [m for m in args.models if m not in pool]
        if missing:
            print(f"[WARN] 未在配置中找到模型: {missing}")
    else:
        models = list(pool.values())

    res = run_benchmark(args.dataset, models, epochs=args.epochs, tag=args.tag)

    ok = [r for r in res if "error" not in r]
    print("\n" + "=" * 78)
    print(f"{'模型':<12}{'Recall@10':>12}{'NDCG@10':>12}{'MRR@10':>12}"
          f"{'Precision@10':>14}{'耗时(s)':>10}")
    print("-" * 78)
    for r in sorted(ok, key=lambda x: -x["test"].get("ndcg@10", 0)):
        t = r["test"]
        print(f"{r['model']:<12}{t.get('recall@10',0):>12.4f}"
              f"{t.get('ndcg@10',0):>12.4f}{t.get('mrr@10',0):>12.4f}"
              f"{t.get('precision@10',0):>14.4f}{r['train_seconds']:>10.1f}")
    print("=" * 78 + "\n")
    failed = [r for r in res if "error" in r]
    if failed:
        print("失败模型:", [(r["model"], r["error"][:60]) for r in failed])


if __name__ == "__main__":
    main()
