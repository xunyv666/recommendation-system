"""构建在线服务数据库（SQLite / MySQL）。

用法:
    python scripts/03_build_db.py                # 全部数据集
    python scripts/03_build_db.py --dataset movielens
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from app import create_app
from app.extensions import db
from app.models import AlgorithmMetric, Item, ItemSimilarity, Rating, User

# Book-Crossing 有 93 万交互，全量入库会让 SQLite 体积过大。
# 应用演示只需覆盖活跃用户，因此只导入交互数前 N 的用户。
MAX_USERS_APP = {"movielens": None, "goodbooks": 4000, "bookcrossing": 4000}


def _domain_of(dataset: str) -> str:
    return C.DATASETS[dataset]["domain"]


def load_items(dataset: str) -> pd.DataFrame:
    p = C.DATA_PROCESSED / dataset / "items.parquet"
    df = pd.read_parquet(p)
    df["item_id"] = df["item_id"].astype(int)
    return df


def build_dataset(dataset: str) -> dict:
    print(f"[DB] ===== {dataset} =====", flush=True)
    items = load_items(dataset)
    ratings = pd.read_parquet(C.DATA_PROCESSED / dataset / "ratings.parquet")

    # 交互量截断
    max_users = MAX_USERS_APP.get(dataset)
    if max_users:
        keep = (
            ratings.groupby("user_id").size()
            .sort_values(ascending=False).head(max_users).index
        )
        ratings = ratings[ratings["user_id"].isin(keep)]

    # 统计
    agg = ratings.groupby("item_id").agg(
        n_ratings=("rating", "size"), avg_rating=("rating", "mean")
    )
    items = items.merge(agg, left_on="item_id", right_index=True, how="left")
    items["n_ratings"] = items["n_ratings"].fillna(0).astype(int)
    items["avg_rating"] = items["avg_rating"].fillna(0.0)
    # 热度：贝叶斯平滑，避免 1 人打 5 分就冲上榜首
    global_mean = float(ratings["rating"].mean())
    m = 25.0
    items["popularity"] = (
        (items["n_ratings"] * items["avg_rating"] + m * global_mean)
        / (items["n_ratings"] + m)
        * (1 + items["n_ratings"].rank(pct=True))
    ).round(6)

    domain = _domain_of(dataset)

    # ---- items
    db.session.query(Item).filter(Item.dataset == dataset).delete()
    db.session.bulk_save_objects([
        Item(
            id=int(r.item_id), domain=domain, dataset=dataset,
            title=str(r.title)[:500],
            genres=str(r.genres or "")[:500],
            year=int(r.year) if pd.notna(r.year) else None,
            avg_rating=float(r.avg_rating), n_ratings=int(r.n_ratings),
            popularity=float(r.popularity),
            image_url=str(getattr(r, "image_url", "") or "")[:500],
        )
        for r in items.itertuples()
    ])
    db.session.commit()
    print(f"      items={len(items):,}", flush=True)

    # ---- users
    uagg = ratings.groupby("user_id").agg(
        n_ratings=("rating", "size"), avg_rating=("rating", "mean")
    )
    db.session.query(User).filter(User.dataset == dataset).delete()
    db.session.bulk_save_objects([
        User(id=int(uid), domain=domain, dataset=dataset,
             n_ratings=int(r.n_ratings), avg_rating=float(r.avg_rating))
        for uid, r in uagg.iterrows()
    ])
    db.session.commit()
    print(f"      users={len(uagg):,}", flush=True)

    # ---- ratings
    db.session.query(Rating).filter(Rating.dataset == dataset).delete()
    db.session.commit()
    batch = []
    for r in ratings.itertuples():
        batch.append(Rating(user_id=int(r.user_id), item_id=int(r.item_id),
                            dataset=dataset, rating=float(r.rating),
                            timestamp=int(r.timestamp)))
        if len(batch) >= 50000:
            db.session.bulk_save_objects(batch)
            db.session.commit()
            batch = []
    if batch:
        db.session.bulk_save_objects(batch)
        db.session.commit()
    print(f"      ratings={len(ratings):,}", flush=True)

    # ---- 物品相似度
    sim_path = C.DATA_PROCESSED / dataset / "item_similarity.parquet"
    db.session.query(ItemSimilarity).filter(ItemSimilarity.dataset == dataset).delete()
    db.session.commit()
    if sim_path.exists():
        sim = pd.read_parquet(sim_path)
        # 只保留入库物品之间的相似对
        valid = set(items["item_id"].astype(int))
        sim = sim[sim["src_id"].isin(valid) & sim["dst_id"].isin(valid)]
        batch = []
        for r in sim.itertuples():
            batch.append(ItemSimilarity(src_id=int(r.src_id), dst_id=int(r.dst_id),
                                        dataset=dataset, score=float(r.score)))
            if len(batch) >= 50000:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []
        if batch:
            db.session.bulk_save_objects(batch)
            db.session.commit()
        print(f"      similarity={len(sim):,}", flush=True)

    return {"dataset": dataset, "items": len(items), "users": len(uagg),
            "ratings": len(ratings)}


def load_metrics(dataset: str) -> int:
    """把基准实验结果写进 algorithm_metrics 表，供看板展示。"""
    p = C.RESULTS / f"benchmark_{dataset}.json"
    if not p.exists():
        print(f"[DB] 无评测结果文件 {p.name}，跳过指标导入")
        return 0
    rows = json.loads(p.read_text(encoding="utf-8"))
    db.session.query(AlgorithmMetric).filter(
        AlgorithmMetric.dataset == dataset
    ).delete()
    n = 0
    for r in rows:
        if "error" in r:
            continue
        for metric, value in (r.get("test") or {}).items():
            db.session.add(AlgorithmMetric(
                dataset=dataset, model=r["model"], metric=metric,
                value=float(value), train_seconds=float(r.get("train_seconds", 0)),
            ))
            n += 1
    db.session.commit()
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=None, choices=list(C.DATASETS))
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        db.create_all()
        targets = [args.dataset] if args.dataset else ["movielens", "goodbooks"]
        for ds in targets:
            try:
                build_dataset(ds)
                n = load_metrics(ds)
                print(f"      metrics={n}", flush=True)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                print(f"[DB] {ds} 失败: {e}", flush=True)

        # 体积报告
        size = C.INSTANCE / "recsys.db"
        if size.exists():
            print(f"\n[DB] SQLite 体积: {size.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
