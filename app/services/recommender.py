"""在线推荐服务：在线层只做查表 + 融合 + 冷启动兜底，不跑模型。

三条取数路径
------------
1. 热用户 → 直接读离线预计算的 `recommendations` 表（最快）
2. 新用户 / 无预计算 → 内容画像召回（按点击过的类型偏好加权）
3. 完全冷启动 → 热度榜兜底

这种"离线训练 + 在线查表 + 冷启动兜底"的分层是工业推荐系统的标准形态，
也让单台 2C4G 云服务器足以支撑演示与上线。
"""
from __future__ import annotations

from collections import Counter
import re

from sqlalchemy import func, select

from ..extensions import db
from ..models import Item, ItemSimilarity, Rating, Recommendation

# Goodreads 的 tag 里混有大量"个人书架"标签（想读/在读/收藏/拥有），
# 直接展示会把 to-read 当成题材。这里做一层展示清洗，数据库原始标签保留。
_SHELF_TAGS = {
    "to-read", "currently-reading", "read", "favorites", "favourites",
    "owned", "books-i-own", "owned-books", "default", "kindle",
    "kindle-unlimited", "ebook", "audiobook", "library", "re-read",
    "book-club", "school", "series", "ya", "novels", "books", "shelf",
}


def _clean_genres(dataset: str, genres: str | None, limit: int = 4) -> str:
    """把原始类型/标签整理成适合展示的短列表（用 | 连接）。"""
    if not genres:
        return ""
    parts = [p.strip().lower() for p in re.split(r"[| ]+", genres) if p.strip()]
    if dataset != "goodbooks":
        return "|".join(parts)
    out: list[str] = []
    for p in parts:
        if p in _SHELF_TAGS or p.startswith("read-in-"):
            continue
        if p not in out:
            out.append(p)
        if len(out) >= limit:
            break
    return "|".join(out)


def _item_dict(it: Item) -> dict:
    return {
        "id": it.id,
        "title": it.title,
        "genres": _clean_genres(it.dataset, it.genres),
        "year": it.year,
        "avg_rating": round(it.avg_rating or 0, 3),
        "n_ratings": it.n_ratings,
        "popularity": round(it.popularity or 0, 6),
        "image_url": it.image_url or "",
        "description": (it.description or "")[:300],
    }


def popular_items(dataset: str, k: int = 20, genre: str | None = None) -> list[dict]:
    """热度榜（冷启动兜底 + 首页默认内容）。"""
    stmt = select(Item).where(Item.dataset == dataset)
    if genre:
        stmt = stmt.where(Item.genres.ilike(f"%{genre}%"))
    stmt = stmt.order_by(Item.popularity.desc()).limit(k)
    return [_item_dict(x) for x in db.session.scalars(stmt)]


def precomputed_recs(
    user_id: int, dataset: str, algo: str, k: int = 20
) -> list[dict]:
    """读离线预计算推荐结果，并联表补全物品信息。"""
    stmt = (
        select(Recommendation, Item)
        .join(Item, Item.id == Recommendation.item_id)
        .where(
            Recommendation.user_id == user_id,
            Recommendation.dataset == dataset,
            Recommendation.algo == algo,
            Item.dataset == dataset,
        )
        .order_by(Recommendation.rank)
        .limit(k)
    )
    out = []
    for rec, item in db.session.execute(stmt):
        d = _item_dict(item)
        d["score"] = round(rec.score or 0, 6)
        d["reason"] = rec.reason or ""
        out.append(d)
    return out


def content_based_recs(user_id: int, dataset: str, k: int = 20) -> list[dict]:
    """内容画像召回：用该用户高分物品的类型分布做加权偏好。"""
    rows = db.session.execute(
        select(Rating.item_id, Rating.rating)
        .where(Rating.user_id == user_id, Rating.dataset == dataset)
        .order_by(Rating.rating.desc())
        .limit(50)
    ).all()
    if not rows:
        return popular_items(dataset, k)

    rated_ids = {r[0] for r in rows}
    # 统计用户偏好的类型
    genres: Counter[str] = Counter()
    items = db.session.scalars(
        select(Item).where(Item.dataset == dataset, Item.id.in_(list(rated_ids)))
    ).all()
    for it in items:
        if not it.genres:
            continue
        w = 2.0 if (it.avg_rating or 0) >= 4 else 1.0
        for g in _clean_genres(dataset, it.genres, limit=8).split("|"):
            g = g.strip()
            if g:
                genres[g] += w

    top_genres = [g for g, _ in genres.most_common(4)]
    if not top_genres:
        return popular_items(dataset, k)

    # 用最喜欢的类型 + 高评分 + 热度排序，排除已看过的
    # 关键：必须过滤评分人数过少的物品，否则会把"1 人打 5 分"的冷门长尾
    # 推给用户——这是内容推荐的常见陷阱，也最能暴露"只看均分"的缺陷。
    stmt = select(Item).where(Item.dataset == dataset)
    stmt = stmt.where(Item.genres.ilike(f"%{top_genres[0]}%"))
    stmt = stmt.where(Item.n_ratings >= 10)
    if rated_ids:
        stmt = stmt.where(Item.id.notin_(list(rated_ids)))
    stmt = stmt.order_by(
        (Item.avg_rating * db.func.log(Item.n_ratings + 1)).desc()
    ).limit(k)

    out = []
    for it in db.session.scalars(stmt):
        d = _item_dict(it)
        hit = [g for g in top_genres if g.lower() in (it.genres or "").lower()]
        d["score"] = round(float(it.avg_rating or 0) / 5.0, 4)
        d["reason"] = (
            f"你偏好的类型是「{'、'.join(top_genres[:2])}」，"
            f"该物品同属「{'、'.join(hit) or top_genres[0]}」，且评分 {it.avg_rating:.1f}"
        )
        out.append(d)
    return out


def similar_items(item_id: int, dataset: str, k: int = 12) -> list[dict]:
    """基于内容特征近邻的"相似物品"。"""
    stmt = (
        select(ItemSimilarity, Item)
        .join(Item, Item.id == ItemSimilarity.dst_id)
        .where(
            ItemSimilarity.src_id == item_id,
            ItemSimilarity.dataset == dataset,
            Item.dataset == dataset,
        )
        .order_by(ItemSimilarity.score.desc())
        .limit(k)
    )
    out = []
    for sim, item in db.session.execute(stmt):
        d = _item_dict(item)
        d["score"] = round(sim.score or 0, 4)
        d["reason"] = f"内容相似度 {sim.score:.2f}"
        out.append(d)
    return out


def recommend(
    user_id: int,
    dataset: str,
    algo: str = "hybrid",
    k: int = 20,
    genre: str | None = None,
) -> dict:
    """统一推荐入口。

    algo:
      - pop     纯热度
      - content 内容画像
      - hybrid  预计算 + 内容补足 + MMR 多样性重排（默认，线上用这个）
      - 其他    按模型名直接读预计算表

    重排层为什么在这里：离线模型只优化相关性，Top-N 往往同一题材刷屏。
    工业系统在排序后还有一层重排，这里用 MMR 在相关性与多样性之间取平衡，
    候选池取 3 倍，重排后再截断到 k。
    """
    rerank_mode = "none"
    if algo == "pop":
        items = popular_items(dataset, k, genre)
        source = "popularity"
    elif algo == "content":
        items = content_based_recs(user_id, dataset, k)
        source = "content"
    else:
        pool = max(k, min(3 * k, 60)) if algo == "hybrid" else k
        items = precomputed_recs(user_id, dataset, algo, pool)
        source = f"precomputed:{algo}"
        had_precomputed = bool(items)
        if len(items) < pool:
            seen = {x["id"] for x in items}
            for x in content_based_recs(user_id, dataset, pool * 2):
                if x["id"] not in seen:
                    items.append(x)
                if len(items) >= pool:
                    break
            if items:
                source = (f"precomputed:{algo}+content_fill"
                          if had_precomputed else "content_fallback")
            else:
                items = popular_items(dataset, k, genre)
                source = "popularity_fallback"

    if genre:
        items = [x for x in items if genre.lower() in (x["genres"] or "").lower()][:k]
        if not items:
            items = popular_items(dataset, k, genre)
            source = "popularity_fallback"
    elif algo == "hybrid" and len(items) > 3:
        # MMR 重排：λ=0.6 在相关性（权重 0.6）与题材多样性（权重 0.4）之间取平衡。
        # 离线已存 60 条候选，线上选出 20 条，MMR 才能真的"换掉"同质化物品，
        # 而不只是把同一批物品重新排序。
        from recsys.llm_rerank import rerank as mmr_rerank

        items = mmr_rerank(items, dataset, k=k, lam=0.6)
        rerank_mode = "mmr"

    return {"user_id": user_id, "dataset": dataset, "algo": algo,
            "source": source, "rerank": rerank_mode, "items": items[:k]}


def dataset_overview(dataset: str) -> dict:
    n_items = db.session.scalar(
        select(func.count()).select_from(Item).where(Item.dataset == dataset)
    )
    n_users = db.session.scalar(
        select(func.count(func.distinct(Rating.user_id))).where(
            Rating.dataset == dataset
        )
    )
    n_ratings = db.session.scalar(
        select(func.count()).select_from(Rating).where(Rating.dataset == dataset)
    )
    return {"dataset": dataset, "n_items": n_items or 0,
            "n_users": n_users or 0, "n_ratings": n_ratings or 0}


def top_genres(dataset: str, k: int = 12) -> list[str]:
    rows = db.session.scalars(
        select(Item.genres).where(
            Item.dataset == dataset, Item.genres.isnot(None), Item.genres != ""
        ).limit(3000)
    )
    c: Counter[str] = Counter()
    for g in rows:
        for part in _clean_genres(dataset, g).split("|"):
            if part:
                c[part] += 1
    return [g for g, _ in c.most_common(k)]
