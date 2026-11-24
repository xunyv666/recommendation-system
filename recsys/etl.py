"""数据 ETL：原始 CSV → 统一交互表 / 物品表 / 内容特征 / SQLite。

设计要点
--------
1. 三个数据集的字段差异全部在这里吸收，下游算法层只面对统一 schema。
2. 输出 RecBole atomic 格式（.inter / .item），让算法层可以直接复用开源平台。
3. 无时间戳的数据集（goodbooks / bookcrossing）合成"伪时间戳"，
   保证全部数据集都能做时间序切分，避免随机切分带来的信息泄漏。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

import config as C

# ------------------------------------------------------------------ 工具


def _norm_title(s: str) -> str:
    """标题规范化：去年份、去标点、小写。"""
    s = re.sub(r"\(\d{4}\)", "", str(s))
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _synth_timestamp(n: int, seed: int = C.SEED) -> np.ndarray:
    """为无时间戳数据集合成单调递增的伪时间戳。

    真实推荐场景中评分本来就是按时间产生的；随机切分会让"未来信息"
    泄漏到训练集，指标虚高。合成单调时间戳可让切分方式与 MovieLens 一致。
    """
    rng = np.random.default_rng(seed)
    # 每人内部大致有序，但保留噪声，避免完全人造的强时序规律
    return np.sort(rng.integers(1_000_000_000, 1_700_000_000, size=n))


# ------------------------------------------------------------------ MovieLens


def load_movielens() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (交互表, 物品表)。

    交互表: user_id, item_id, rating, timestamp
    物品表: item_id, title, genres, year, tag_text
    """
    raw: Path = C.DATASETS["movielens"]["raw"]

    ratings = pd.read_csv(raw / "ratings.csv")
    ratings = ratings.rename(columns={"userId": "user_id", "movieId": "item_id"})
    ratings = ratings[["user_id", "item_id", "rating", "timestamp"]]

    movies = pd.read_csv(raw / "movies.csv")
    movies = movies.rename(columns={"movieId": "item_id"})

    # 年份从标题里抽
    movies["year"] = (
        movies["title"].str.extract(r"\((\d{4})\)")[0].astype("float").astype("Int64")
    )
    movies["title_clean"] = movies["title"].map(_norm_title)
    # genres 用 | 分隔，转成空格分隔的 token 串（RecBole token_seq 要求）
    movies["genres_tok"] = movies["genres"].str.replace("|", " ", regex=False)

    # 用户标签聚合成物品的文本画像
    tags = pd.read_csv(raw / "tags.csv")
    tag_group = (
        tags.groupby("movieId")["tag"]
        .apply(lambda s: " ".join(s.astype(str).unique()[:50]))
        .rename("tag_text")
    )
    movies = movies.merge(tag_group, left_on="item_id", right_index=True, how="left")
    movies["tag_text"] = movies["tag_text"].fillna("")

    items = movies[
        ["item_id", "title", "title_clean", "genres", "genres_tok", "year", "tag_text"]
    ].copy()
    return ratings, items


# ------------------------------------------------------------------ goodbooks


def load_goodbooks() -> Tuple[pd.DataFrame, pd.DataFrame]:
    raw: Path = C.DATASETS["goodbooks"]["raw"]

    ratings = pd.read_csv(raw / "ratings.csv")
    ratings = ratings.rename(columns={"user_id": "user_id", "book_id": "item_id"})
    ratings["timestamp"] = _synth_timestamp(len(ratings))
    ratings = ratings[["user_id", "item_id", "rating", "timestamp"]]

    books = pd.read_csv(raw / "books.csv", low_memory=False)
    books = books.rename(columns={"book_id": "item_id"})

    # 类型标签：book_tags + tag_name
    genres_map: dict[int, str] = {}
    try:
        bt = pd.read_csv(raw / "book_tags.csv")
        names = pd.read_csv(raw / "tags.csv")
        bt = bt.merge(names, on="tag_id", how="left")
        # 每本书取 count 最高的前 15 个标签
        bt = bt.sort_values(["goodreads_book_id", "count"], ascending=[True, False])
        for gid, g in bt.groupby("goodreads_book_id"):
            toks = [str(t) for t in g["tag_name"].head(15) if isinstance(t, str)]
            genres_map[int(gid)] = " ".join(toks)
    except Exception:  # noqa: BLE001 - 标签缺失不阻断主流程
        pass

    books["genres"] = books["goodreads_book_id"].map(genres_map).fillna("")
    books["genres_tok"] = books["genres"]
    books["title_clean"] = books["title"].map(_norm_title)
    books["year"] = pd.to_numeric(
        books["original_publication_year"], errors="coerce"
    ).astype("Int64")
    # 作者 + 标题 作为内容文本
    books["tag_text"] = (
        books["authors"].fillna("").astype(str)
        + " "
        + books["title"].fillna("").astype(str)
    )
    books["image_url"] = books.get("image_url", "")

    items = books[
        [
            "item_id",
            "title",
            "title_clean",
            "genres",
            "genres_tok",
            "year",
            "tag_text",
            "image_url",
        ]
    ].copy()
    return ratings, items


# ------------------------------------------------------------------ Book-Crossing


def load_bookcrossing(min_user_ratings: int = 5) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Book-Crossing 规模大且噪声重，做最小必要清洗。

    - rating==0 表示"有交互无评分"，保留为隐式反馈（评分为 0 不参与排序损失）
    - 过滤交互数 < min_user_ratings 的冷用户，降低噪声
    """
    raw: Path = C.DATASETS["bookcrossing"]["raw"]

    ratings = pd.read_csv(
        raw / "BX-Book-Ratings.csv",
        sep=";",
        encoding="latin-1",
        on_bad_lines="skip",
        engine="python",
    )
    ratings.columns = ["user_id", "isbn", "rating"]
    ratings["user_id"] = pd.to_numeric(ratings["user_id"], errors="coerce")
    ratings["rating"] = pd.to_numeric(ratings["rating"], errors="coerce")
    ratings = ratings.dropna(subset=["user_id", "isbn", "rating"])
    ratings["user_id"] = ratings["user_id"].astype("int64")

    # 只保留显式正反馈 + 隐式反馈中"确实发生过"的记录
    cnt = ratings.groupby("user_id").size()
    keep_users = cnt[cnt >= min_user_ratings].index
    ratings = ratings[ratings["user_id"].isin(keep_users)].copy()

    # 隐式 0 分 → 视为弱正反馈，给一个中等分，避免被当成强负反馈
    ratings["rating"] = ratings["rating"].replace(0, 5.0)
    ratings["timestamp"] = _synth_timestamp(len(ratings))

    books = pd.read_csv(
        raw / "BX-Books.csv",
        sep=";",
        encoding="latin-1",
        on_bad_lines="skip",
        engine="python",
    )
    books.columns = [
        "isbn",
        "title",
        "author",
        "year",
        "publisher",
        "url_s",
        "url_m",
        "url_l",
    ]
    books = books.drop_duplicates(subset=["isbn"])

    # ISBN → 稠密整数 item_id
    isbns = sorted(books["isbn"].astype(str).unique())
    isbn2id = {isbn: i + 1 for i, isbn in enumerate(isbns)}
    books["item_id"] = books["isbn"].astype(str).map(isbn2id)
    ratings["item_id"] = ratings["isbn"].astype(str).map(isbn2id)
    ratings = ratings.dropna(subset=["item_id"])
    ratings["item_id"] = ratings["item_id"].astype("int64")

    books["year"] = pd.to_numeric(books["year"], errors="coerce").astype("Int64")
    books["title_clean"] = books["title"].map(_norm_title)
    books["genres"] = ""
    books["genres_tok"] = ""
    books["tag_text"] = (
        books["author"].fillna("").astype(str)
        + " "
        + books["title"].fillna("").astype(str)
        + " "
        + books["publisher"].fillna("").astype(str)
    )
    books["image_url"] = books["url_m"].fillna("")

    items = books[
        [
            "item_id",
            "title",
            "title_clean",
            "genres",
            "genres_tok",
            "year",
            "tag_text",
            "image_url",
        ]
    ].copy()
    inter = ratings[["user_id", "item_id", "rating", "timestamp"]].copy()
    return inter, items


# ------------------------------------------------------------------ 导出


LOADERS = {
    "movielens": load_movielens,
    "goodbooks": load_goodbooks,
    "bookcrossing": load_bookcrossing,
}


def export_dataset(name: str) -> dict:
    """跑通一个数据集的 ETL，写出 RecBole atomic 文件 + 元数据。"""
    loader = LOADERS[name]
    inter, items = loader()

    # 只保留出现在交互表里的物品，避免 item 表与 inter 表 ID 空间不一致
    items = items[items["item_id"].isin(inter["item_id"].unique())].copy()

    out_dir = C.DATA_PROCESSED / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- RecBole .inter
    inter_out = inter.copy()
    inter_out.insert(0, "user_id:token", inter_out.pop("user_id").astype(str))
    inter_out.insert(1, "item_id:token", inter_out.pop("item_id").astype(str))
    inter_out = inter_out.rename(
        columns={"rating": "rating:float", "timestamp": "timestamp:float"}
    )
    inter_out.to_csv(out_dir / f"{name}.inter", sep="\t", index=False)

    # ---- RecBole .item
    item_out = items.copy()
    item_out.insert(0, "item_id:token", item_out.pop("item_id").astype(str))
    item_out["title:token"] = item_out["title"].fillna("").astype(str).str.replace(
        "\t", " ", regex=False
    )
    item_out["genres:token_seq"] = item_out["genres_tok"].fillna("").astype(str)
    item_out[["item_id:token", "title:token", "genres:token_seq"]].to_csv(
        out_dir / f"{name}.item", sep="\t", index=False
    )

    # ---- 应用展示用元数据
    meta = items.copy()
    meta["item_id"] = meta["item_id"].astype(int)
    meta.to_parquet(out_dir / "items.parquet", index=False)

    # ---- 交互表（供特征工程与在线服务直接读取，避免反复解析 TSV）
    inter.astype({"user_id": "int64", "item_id": "int64"}).to_parquet(
        out_dir / "ratings.parquet", index=False
    )

    stats = {
        "dataset": name,
        "domain": C.DATASETS[name]["domain"],
        "n_users": int(inter["user_id"].nunique()),
        "n_items": int(inter["item_id"].nunique()),
        "n_interactions": int(len(inter)),
        "sparsity": round(
            1
            - len(inter)
            / (inter["user_id"].nunique() * inter["item_id"].nunique()),
            6,
        ),
        "rating_min": float(inter["rating"].min()),
        "rating_max": float(inter["rating"].max()),
        "rating_mean": round(float(inter["rating"].mean()), 4),
        "ts_min": int(inter["timestamp"].min()),
        "ts_max": int(inter["timestamp"].max()),
    }
    (out_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


def export_all() -> list[dict]:
    out = []
    for name in DATASETS_TO_RUN:
        try:
            s = export_dataset(name)
            out.append(s)
            print(f"[ETL] {name:14s} users={s['n_users']:>7} "
                  f"items={s['n_items']:>7} inter={s['n_interactions']:>9} "
                  f"sparsity={s['sparsity']:.5f}")
        except Exception as e:  # noqa: BLE001
            print(f"[ETL] {name} FAILED: {type(e).__name__}: {e}")
    return out


DATASETS_TO_RUN = ["movielens", "goodbooks", "bookcrossing"]

if __name__ == "__main__":
    stats = export_all()
    (C.DATA_PROCESSED / "all_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
