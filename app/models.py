"""ORM 模型：物品、用户、评分、预计算推荐、物品相似度、行为日志。

设计说明
--------
线上服务不实时跑模型，而是查 `recommendations` 表（离线预计算结果）。
这是推荐系统落地的标准做法：训练与 serving 解耦，在线延迟可控。
"""
from __future__ import annotations

from datetime import datetime

from .extensions import db


class Item(db.Model):
    """物品表。

    主键设计：不同数据集的 item_id 会重复（movie 的 1 号电影和 book 的 1 号书
    都是 1），因此不能用 item_id 作全局主键。这里用代理主键 pk，
    并在 (dataset, id) 上建唯一约束——业务代码仍然按 `Item.dataset + Item.id`
    查询，语义不变，也不会跨数据集串号。
    """

    __tablename__ = "items"

    pk = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id = db.Column(db.Integer, nullable=False)                    # 数据集内的原始 item_id
    domain = db.Column(db.String(16), index=True, nullable=False)  # movie / book
    dataset = db.Column(db.String(32), index=True, nullable=False)
    title = db.Column(db.String(512), nullable=False)
    genres = db.Column(db.String(512), default="")
    year = db.Column(db.Integer)
    avg_rating = db.Column(db.Float, default=0.0)
    n_ratings = db.Column(db.Integer, default=0)
    popularity = db.Column(db.Float, default=0.0)
    image_url = db.Column(db.String(512), default="")
    description = db.Column(db.Text, default="")

    __table_args__ = (
        db.UniqueConstraint("dataset", "id", name="uq_items_dataset_id"),
        db.Index("ix_items_domain_pop", "domain", "popularity"),
        db.Index("ix_items_dataset_pop", "dataset", "popularity"),
    )


class User(db.Model):
    """用户表：id 同样是数据集内编号，用 (dataset, id) 唯一约束。"""

    __tablename__ = "users"

    pk = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id = db.Column(db.Integer, nullable=False)
    domain = db.Column(db.String(16), index=True)
    dataset = db.Column(db.String(32), index=True)
    n_ratings = db.Column(db.Integer, default=0)
    avg_rating = db.Column(db.Float, default=0.0)

    __table_args__ = (
        db.UniqueConstraint("dataset", "id", name="uq_users_dataset_id"),
    )


class Rating(db.Model):
    __tablename__ = "ratings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    item_id = db.Column(db.Integer, index=True, nullable=False)
    dataset = db.Column(db.String(32), index=True)
    rating = db.Column(db.Float)
    timestamp = db.Column(db.Integer)


class Recommendation(db.Model):
    """离线预计算的 Top-N 推荐结果。"""

    __tablename__ = "recommendations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    dataset = db.Column(db.String(32), index=True, nullable=False)
    algo = db.Column(db.String(32), index=True, nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, index=True, nullable=False)
    score = db.Column(db.Float, default=0.0)
    reason = db.Column(db.String(512), default="")

    __table_args__ = (
        db.Index("ix_rec_user_algo", "user_id", "algo", "rank"),
    )


class ItemSimilarity(db.Model):
    __tablename__ = "item_similarity"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    src_id = db.Column(db.Integer, index=True, nullable=False)
    dst_id = db.Column(db.Integer, index=True, nullable=False)
    dataset = db.Column(db.String(32), index=True)
    score = db.Column(db.Float, default=0.0)


class FeedbackLog(db.Model):
    """在线行为日志：为后续增量训练 / 效果分析提供数据。"""

    __tablename__ = "feedback_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, index=True)
    item_id = db.Column(db.Integer, index=True)
    action = db.Column(db.String(32))          # view / click / like / dislike
    algo = db.Column(db.String(32), default="")
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AlgorithmMetric(db.Model):
    """各算法离线评测指标，供后台看板展示。"""

    __tablename__ = "algorithm_metrics"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dataset = db.Column(db.String(32), index=True)
    model = db.Column(db.String(32), index=True)
    metric = db.Column(db.String(32))
    value = db.Column(db.Float)
    train_seconds = db.Column(db.Float, default=0.0)
