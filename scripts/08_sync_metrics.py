"""把分段跑出来的基准结果合并成一张总表，并同步到数据库看板。

用法:
    python scripts/08_sync_metrics.py --dataset movielens
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from app import create_app
from app.extensions import db
from app.models import AlgorithmMetric

# 允许把多次运行的结果合并进主表（后跑的覆盖先跑的）
EXTRA_FILES = {
    "movielens": ["benchmark_movielens_final.json"],
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="movielens")
    args = ap.parse_args()

    main_path = C.RESULTS / f"benchmark_{args.dataset}.json"
    rows = json.loads(main_path.read_text(encoding="utf-8"))
    by_model = {r["model"]: r for r in rows}

    for name in EXTRA_FILES.get(args.dataset, []):
        p = C.RESULTS / name
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            if "error" in r:
                continue
            by_model[r["model"]] = r

    merged = list(by_model.values())
    main_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"[MERGE] {len(merged)} 个模型 -> {main_path.name}")

    app = create_app()
    with app.app_context():
        db.session.query(AlgorithmMetric).filter(
            AlgorithmMetric.dataset == args.dataset
        ).delete()
        n = 0
        for r in merged:
            if "error" in r:
                continue
            for metric, value in (r.get("test") or {}).items():
                db.session.add(AlgorithmMetric(
                    dataset=args.dataset, model=r["model"], metric=metric,
                    value=float(value),
                    train_seconds=float(r.get("train_seconds", 0)),
                ))
                n += 1
        db.session.commit()
        print(f"[MERGE] 已写入 {n} 条指标")


if __name__ == "__main__":
    main()
