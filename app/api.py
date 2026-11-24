"""REST API 蓝图。

接口设计遵循"前端只拉数据、渲染交给模板/JS"的原则，
方便同一套 API 同时服务 Flask 模板和部署在 Cloudflare Pages 的静态前端。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from .extensions import db
from .models import AlgorithmMetric, FeedbackLog, Item, Rating
from .services import recommender as R

api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/health")
def health():
    return jsonify({"status": "ok", "service": "recsys-course-project"})


@api.get("/overview")
def overview():
    ds = request.args.get("dataset", "movielens")
    data = R.dataset_overview(ds)
    data["top_genres"] = R.top_genres(ds)
    data["datasets"] = ["movielens", "bookcrossing", "goodbooks"]
    return jsonify(data)


@api.get("/items")
def items():
    ds = request.args.get("dataset", "movielens")
    page = max(1, int(request.args.get("page", 1)))
    size = min(60, max(1, int(request.args.get("size", 20))))
    genre = request.args.get("genre")
    q = request.args.get("q")

    stmt = db.select(Item).where(Item.dataset == ds)
    if genre:
        stmt = stmt.where(Item.genres.ilike(f"%{genre}%"))
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Item.popularity.desc())

    total = db.session.scalar(
        db.select(db.func.count()).select_from(stmt.subquery())
    )
    rows = db.session.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return jsonify({
        "total": total or 0, "page": page, "size": size,
        "items": [R._item_dict(x) for x in rows],
    })


@api.get("/items/<int:item_id>")
def item_detail(item_id: int):
    ds = request.args.get("dataset", "movielens")
    it = db.session.scalars(
        db.select(Item).where(Item.dataset == ds, Item.id == item_id)
    ).first()
    if not it:
        return jsonify({"error": "item not found"}), 404
    d = R._item_dict(it)
    d["similar"] = R.similar_items(item_id, ds, 12)
    stats = db.session.execute(
        db.select(
            db.func.count(Rating.id),
            db.func.avg(Rating.rating),
        ).where(Rating.item_id == item_id, Rating.dataset == ds)
    ).one()
    d["rating_count"], d["rating_avg"] = int(stats[0] or 0), round(stats[1] or 0, 3)
    return jsonify(d)


@api.get("/users")
def users():
    ds = request.args.get("dataset", "movielens")
    limit = min(200, int(request.args.get("limit", 50)))
    rows = db.session.execute(
        db.select(Rating.user_id, db.func.count(Rating.id).label("n"))
        .where(Rating.dataset == ds)
        .group_by(Rating.user_id)
        .order_by(Rating.user_id)
        .limit(limit)
    ).all()
    return jsonify({"users": [{"user_id": r[0], "n_ratings": r[1]} for r in rows]})


@api.get("/history/<int:user_id>")
def history(user_id: int):
    """用户真实历史行为（按评分与时间排序），用于推荐页对照。"""
    ds = request.args.get("dataset", "movielens")
    limit = min(40, int(request.args.get("limit", 12)))
    rows = db.session.execute(
        db.select(Rating, Item)
        .join(Item, (Item.id == Rating.item_id) & (Item.dataset == Rating.dataset))
        .where(Rating.user_id == user_id, Rating.dataset == ds)
        .order_by(Rating.rating.desc(), Rating.timestamp.desc())
        .limit(limit)
    ).all()
    return jsonify({
        "user_id": user_id,
        "items": [
            {**R._item_dict(item), "user_rating": float(rating.rating),
             "timestamp": int(rating.timestamp or 0)}
            for rating, item in rows
        ],
    })


@api.get("/recommend/<int:user_id>")
def recommend(user_id: int):
    ds = request.args.get("dataset", "movielens")
    algo = request.args.get("algo", "hybrid")
    k = min(50, int(request.args.get("k", 12)))
    genre = request.args.get("genre")
    return jsonify(R.recommend(user_id, ds, algo, k, genre))


@api.get("/popular")
def popular():
    ds = request.args.get("dataset", "movielens")
    k = min(50, int(request.args.get("k", 12)))
    genre = request.args.get("genre")
    return jsonify({"items": R.popular_items(ds, k, genre)})


@api.get("/search")
def search():
    ds = request.args.get("dataset", "movielens")
    q = request.args.get("q", "")
    k = min(120, int(request.args.get("k", 48)))
    items = R.search_items(ds, q, k)
    return jsonify({"query": q, "dataset": ds, "total": len(items), "items": items})


@api.get("/similar/<int:item_id>")
def similar(item_id: int):
    ds = request.args.get("dataset", "movielens")
    return jsonify({"items": R.similar_items(item_id, ds, 12)})


@api.get("/metrics")
def metrics():
    ds = request.args.get("dataset", "movielens")
    rows = db.session.scalars(
        db.select(AlgorithmMetric).where(AlgorithmMetric.dataset == ds)
    ).all()
    table: dict[str, dict] = {}
    for r in rows:
        table.setdefault(r.model, {})[r.metric] = r.value
        table[r.model]["train_seconds"] = r.train_seconds
    return jsonify({"dataset": ds, "metrics": table})


@api.post("/feedback")
def feedback():
    data = request.get_json(silent=True) or {}
    log = FeedbackLog(
        user_id=int(data.get("user_id", 0)),
        item_id=int(data.get("item_id", 0)),
        action=str(data.get("action", "view"))[:32],
        algo=str(data.get("algo", ""))[:32],
        position=int(data.get("position", 0)),
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({"ok": True, "id": log.id})
