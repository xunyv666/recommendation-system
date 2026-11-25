"""管理后台蓝图（/admin）。

课程演示用的轻量后台：登录 → 数据总览 / 物品 / 用户 / 推荐结果 / 行为日志 /
算法指标 / 中文译名维护。与前台共用同一个 SQLite 数据库和同一套 ORM 模型，
不需要额外服务；生产环境请务必通过环境变量设置 ADMIN_PASSWORD。
"""
from __future__ import annotations

import functools
import json
import os

from flask import (
    Blueprint, abort, flash, redirect, render_template, request,
    session, url_for,
)

import config as C
from .extensions import db
from .models import (
    AlgorithmMetric, FeedbackLog, Item, ItemSimilarity, Rating,
    Recommendation, User,
)

admin = Blueprint("admin", __name__, url_prefix="/admin")

DEFAULT_PASSWORD = "recsys2026"
DATASETS = ["movielens", "goodbooks", "bookcrossing"]
ALGOS = ["hybrid", "content", "pop", "lightgcn", "itemknn", "freedom"]


def _password() -> str:
    return os.environ.get("ADMIN_PASSWORD", DEFAULT_PASSWORD)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def _pagination(total: int, page: int, size: int) -> dict:
    pages = max(1, (total + size - 1) // size)
    return {"page": page, "size": size, "total": total,
            "pages": pages, "prev": max(1, page - 1),
            "next": min(pages, page + 1)}


def _page_arg() -> int:
    try:
        return max(1, int(request.args.get("page", 1)))
    except ValueError:
        return 1


def _dataset_arg(default: str = "movielens") -> str:
    ds = request.args.get("dataset", default)
    return ds if ds in DATASETS else default


def _title_map() -> dict:
    path = C.ROOT / "data" / "processed" / "titles_zh.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_title_map(data: dict) -> None:
    path = C.ROOT / "data" / "processed" / "titles_zh.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    site = C.ROOT / "site" / "data" / "titles_zh.json"
    if site.parent.exists():
        site.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@admin.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        if request.form.get("password", "") == _password():
            session["admin"] = True
            nxt = request.form.get("next", "")
            # 只允许站内相对路径跳转
            return redirect(nxt if nxt.startswith("/admin/") else url_for("admin.dashboard"))
        err = "密码错误，请重试"
    return render_template("admin/login.html", err=err,
                           next=request.args.get("next", ""))


@admin.post("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin.login"))


@admin.get("/")
@login_required
def dashboard():
    counts = {
        "n_items": db.session.scalar(db.select(db.func.count()).select_from(Item)) or 0,
        "n_users": db.session.scalar(db.select(db.func.count()).select_from(User)) or 0,
        "n_ratings": db.session.scalar(db.select(db.func.count()).select_from(Rating)) or 0,
        "n_recs": db.session.scalar(db.select(db.func.count()).select_from(Recommendation)) or 0,
        "n_feedback": db.session.scalar(db.select(db.func.count()).select_from(FeedbackLog)) or 0,
        "n_metrics": db.session.scalar(db.select(db.func.count()).select_from(AlgorithmMetric)) or 0,
    }
    by_ds = db.session.execute(
        db.select(Item.dataset, db.func.count(Item.id)).group_by(Item.dataset)
    ).all()
    recent = db.session.scalars(
        db.select(FeedbackLog).order_by(FeedbackLog.id.desc()).limit(8)
    ).all()
    zh = _title_map()
    zh_counts = {ds: len(v) for ds, v in zh.items()}
    return render_template("admin/dashboard.html", counts=counts, by_ds=by_ds,
                           recent=recent, zh_counts=zh_counts, page="dashboard")


@admin.get("/items")
@login_required
def items():
    ds = _dataset_arg()
    q = (request.args.get("q") or "").strip()
    page, size = _page_arg(), 30
    stmt = db.select(Item).where(Item.dataset == ds)
    if q:
        stmt = stmt.where(db.or_(Item.title.ilike(f"%{q}%"),
                                 Item.genres.ilike(f"%{q}%")))
    total = db.session.scalar(
        db.select(db.func.count()).select_from(stmt.subquery())) or 0
    rows = db.session.scalars(
        stmt.order_by(Item.popularity.desc()).offset((page - 1) * size).limit(size)
    ).all()
    zh = _title_map().get(ds, {})
    return render_template("admin/items.html", rows=rows, zh=zh, ds=ds, q=q,
                           pager=_pagination(total, page, size), page="items")


@admin.get("/items/<dataset>/<int:item_id>")
@login_required
def item_detail(dataset: str, item_id: int):
    it = db.session.scalars(
        db.select(Item).where(Item.dataset == dataset, Item.id == item_id)
    ).first()
    if not it:
        abort(404)
    stat = db.session.execute(
        db.select(db.func.count(Rating.id), db.func.avg(Rating.rating))
        .where(Rating.dataset == dataset, Rating.item_id == item_id)
    ).one()
    sims = db.session.execute(
        db.select(ItemSimilarity, Item)
        .join(Item, (Item.id == ItemSimilarity.dst_id)
              & (Item.dataset == ItemSimilarity.dataset))
        .where(ItemSimilarity.dataset == dataset,
               ItemSimilarity.src_id == item_id)
        .order_by(ItemSimilarity.score.desc()).limit(10)
    ).all()
    zh = _title_map().get(dataset, {}).get(str(item_id), "")
    return render_template("admin/item_detail.html", it=it,
                           n_ratings=int(stat[0] or 0),
                           rating_avg=round(stat[1] or 0, 3),
                           sims=sims, zh=zh, page="items")


@admin.get("/users")
@login_required
def users():
    ds = _dataset_arg()
    q = (request.args.get("q") or "").strip()
    page, size = _page_arg(), 30
    stmt = db.select(User).where(User.dataset == ds)
    if q and q.isdigit():
        stmt = stmt.where(User.id == int(q))
    total = db.session.scalar(
        db.select(db.func.count()).select_from(stmt.subquery())) or 0
    rows = db.session.scalars(
        stmt.order_by(User.id).offset((page - 1) * size).limit(size)
    ).all()
    return render_template("admin/users.html", rows=rows, ds=ds, q=q,
                           pager=_pagination(total, page, size), page="users")


@admin.get("/recommendations")
@login_required
def recommendations():
    ds = _dataset_arg()
    try:
        uid = int(request.args.get("user_id", 1))
    except ValueError:
        uid = 1
    algo = request.args.get("algo", "hybrid")
    rows = db.session.execute(
        db.select(Recommendation, Item)
        .join(Item, (Item.id == Recommendation.item_id)
              & (Item.dataset == Recommendation.dataset))
        .where(Recommendation.dataset == ds, Recommendation.user_id == uid,
               Recommendation.algo == algo)
        .order_by(Recommendation.rank).limit(30)
    ).all()
    users = db.session.scalars(
        db.select(User).where(User.dataset == ds).order_by(User.id).limit(200)
    ).all()
    return render_template("admin/recommendations.html", rows=rows, ds=ds,
                           uid=uid, algo=algo, algos=ALGOS, users=users,
                           page="recommendations")


@admin.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        fid = request.form.get("id", "")
        if fid.isdigit():
            db.session.delete(db.session.get(FeedbackLog, int(fid)))
            db.session.commit()
            flash(f"已删除日志 #{fid}")
        return redirect(url_for("admin.feedback", dataset=request.form.get("dataset", "")))
    ds = request.args.get("dataset", "")
    page, size = _page_arg(), 30
    stmt = db.select(FeedbackLog)
    total = db.session.scalar(
        db.select(db.func.count()).select_from(stmt.subquery())) or 0
    rows = db.session.scalars(
        stmt.order_by(FeedbackLog.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return render_template("admin/feedback.html", rows=rows, ds=ds,
                           pager=_pagination(total, page, size), page="feedback")


@admin.get("/metrics")
@login_required
def metrics():
    rows = db.session.scalars(
        db.select(AlgorithmMetric).order_by(AlgorithmMetric.dataset,
                                            AlgorithmMetric.model,
                                            AlgorithmMetric.metric)
    ).all()
    table: dict[str, dict[str, dict]] = {}
    for r in rows:
        d = table.setdefault(r.dataset, {}).setdefault(r.model, {})
        d[r.metric] = r.value
        d["train_seconds"] = r.train_seconds
    return render_template("admin/metrics.html", table=table, page="metrics")


@admin.route("/translations", methods=["GET", "POST"])
@login_required
def translations():
    if request.method == "POST":
        ds = request.form.get("dataset", "")
        iid = request.form.get("item_id", "")
        zh = (request.form.get("title_zh") or "").strip()
        if ds in DATASETS and iid.isdigit():
            data = _title_map()
            table = data.setdefault(ds, {})
            if zh:
                table[str(int(iid))] = zh
            else:
                table.pop(str(int(iid)), None)
            _save_title_map(data)
            flash(f"已保存 {ds} #{iid} 的中文译名")
        return redirect(url_for("admin.translations", dataset=ds,
                                q=request.form.get("q", "")))

    ds = _dataset_arg()
    q = (request.args.get("q") or "").strip()
    page, size = _page_arg(), 30
    zh = _title_map().get(ds, {})
    # 只列出尚未翻译的条目（q 非空时全局搜索，便于补译）
    stmt = db.select(Item).where(Item.dataset == ds)
    if q:
        conds = [Item.title.ilike(f"%{q}%")]
        if q.isdigit():
            conds.append(Item.id == int(q))
        stmt = stmt.where(db.or_(*conds))
    page_items = db.session.scalars(
        stmt.order_by(Item.popularity.desc()).offset((page - 1) * size).limit(size)
    ).all()
    total = db.session.scalar(
        db.select(db.func.count()).select_from(
            db.select(Item).where(Item.dataset == ds).subquery())) or 0
    return render_template("admin/translations.html", rows=page_items, zh=zh,
                           ds=ds, q=q, coverage=len(zh), total=total,
                           pager=_pagination(total, page, size), page="translations")
