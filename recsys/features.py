"""内容特征工程：为每个物品构造"多视图"特征。

为什么要多视图
--------------
纯协同过滤在冷启动、长尾物品上表现差。内容特征提供互补信号：
  视图1 文本语义  —— 标题 + 类型 + 用户标签 / 作者 + 出版社，TF-IDF → SVD 降维
  视图2 类别 multi-hot —— 电影类型 / 图书标签
  视图3 结构化数值 —— 年份、热度、平均分

三个视图拼接 + L2 归一化，得到统一的物品特征矩阵。
这类"多视图/多模态融合"是 FREEDOM、LATTICE 等模型的核心输入；
若后续拿到真实海报/封面图，只需在此追加一个图像视图即可，下游代码不用改。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler

import config as C


def _load_items(dataset: str) -> pd.DataFrame:
    p = C.DATA_PROCESSED / dataset / "items.parquet"
    df = pd.read_parquet(p)
    df["item_id"] = df["item_id"].astype(int)
    return df


def build_text_view(df: pd.DataFrame, n_components: int = 128) -> np.ndarray:
    """文本视图：TF-IDF → TruncatedSVD 稠密向量。

    token_pattern 同时兼容英文单词与中文连续字块，因此电影（英文）和
    图书（英文）无需分语种处理；若接入中文数据，jieba 分词后可复用。
    """
    text = (
        df["title_clean"].fillna("").astype(str)
        + " "
        + df["genres"].fillna("").astype(str).str.replace("|", " ", regex=False)
        + " "
        + df["tag_text"].fillna("").astype(str)
    ).str.lower()

    vec = TfidfVectorizer(
        max_features=20000,
        min_df=2,
        token_pattern=r"(?u)\b\w{2,}\b",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    try:
        X = vec.fit_transform(text)
    except ValueError:
        return np.zeros((len(df), n_components), dtype=np.float32)

    k = min(n_components, max(2, min(X.shape) - 1))
    svd = TruncatedSVD(n_components=k, random_state=C.SEED)
    Z = svd.fit_transform(X)
    # 补齐到固定维度，便于不同数据集共用下游代码
    if Z.shape[1] < n_components:
        Z = np.pad(Z, ((0, 0), (0, n_components - Z.shape[1])))
    return Z.astype(np.float32)


def build_category_view(df: pd.DataFrame) -> np.ndarray:
    """类别视图：类型 / 标签的 multi-hot 编码。"""
    def toks(s):
        s = str(s) if s is not None else ""
        if not s or s == "nan":
            return []
        return [t.strip().lower() for t in s.replace("|", " ").split() if t.strip()]

    labels = df["genres"].map(toks)
    if labels.map(len).sum() == 0:
        return np.zeros((len(df), 1), dtype=np.float32)
    mlb = MultiLabelBinarizer()
    return mlb.fit_transform(labels).astype(np.float32)


def build_numeric_view(df: pd.DataFrame, ratings: pd.DataFrame) -> np.ndarray:
    """结构化视图：年份（缺失用中位数）、热度（log 交互数）、平均分。"""
    pop = ratings.groupby("item_id").size().rename("n_ratings")
    avg = ratings.groupby("item_id")["rating"].mean().rename("avg_rating")
    m = df[["item_id"]].merge(pop, left_on="item_id", right_index=True, how="left")
    m = m.merge(avg, left_on="item_id", right_index=True, how="left")

    year = pd.to_numeric(df["year"], errors="coerce").astype(float)
    year = year.fillna(year.median())

    X = np.column_stack([
        year.to_numpy(),
        np.log1p(m["n_ratings"].fillna(0).to_numpy()),
        m["avg_rating"].fillna(m["avg_rating"].mean()).to_numpy(),
    ]).astype(np.float32)
    return StandardScaler().fit_transform(X).astype(np.float32)


def build_item_features(dataset: str) -> tuple[np.ndarray, list[int]]:
    """返回 (物品特征矩阵 [n_items, d], 对应的 item_id 列表)。"""
    df = _load_items(dataset)
    ratings = pd.read_parquet(C.DATA_PROCESSED / dataset / "ratings.parquet")

    df = df.sort_values("item_id").reset_index(drop=True)

    Z_text = build_text_view(df)
    Z_cat = build_category_view(df)
    Z_num = build_numeric_view(df, ratings)

    F = np.hstack([Z_text, Z_cat, Z_num]).astype(np.float32)
    # L2 归一化：让不同视图的尺度可比，余弦相似度才不会被大数值视图主导
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    F = F / norms
    return F, df["item_id"].tolist()


def build_item_similarity(
    dataset: str, top_k: int = 50, block: int = 256, max_src_items: int = 30000
) -> pd.DataFrame:
    """基于内容特征计算物品-物品 Top-K 相似度。

    大规模数据集（如 Book-Crossing 25.7 万物品）全量计算不可行：
    每个 block 的相似度矩阵就是 block×n_items 的稠密阵，内存与耗时都爆炸。
    因此只对"交互数最多的 max_src_items 个物品"作为源计算相似度，
    这些正是详情页真正会被点开的物品，业务上无损失。
    """
    F, ids = build_item_features(dataset)
    n = len(ids)

    # 按热度截断源物品
    if n > max_src_items:
        ratings = pd.read_parquet(C.DATA_PROCESSED / dataset / "ratings.parquet")
        hot = (
            ratings.groupby("item_id").size()
            .sort_values(ascending=False)
            .head(max_src_items)
            .index.tolist()
        )
        hot_set = set(hot)
        src_idx = [i for i, iid in enumerate(ids) if iid in hot_set]
    else:
        src_idx = list(range(n))

    S = sparse.csr_matrix(F)   # 特征已 L2 归一化，点积即余弦
    rows = []
    for start in range(0, len(src_idx), block):
        chunk = src_idx[start:start + block]
        sim_block = (S[chunk] @ S.T).toarray()
        for r, global_i in enumerate(chunk):
            vec = sim_block[r]
            vec[global_i] = -np.inf          # 屏蔽自身
            k = min(top_k, n - 1)
            idx = np.argpartition(-vec, kth=k - 1)[:k]
            idx = idx[np.argsort(-vec[idx])]
            for j in idx:
                if vec[j] == -np.inf:
                    continue
                rows.append((ids[global_i], ids[int(j)], float(vec[j])))

    return pd.DataFrame(rows, columns=["src_id", "dst_id", "score"])


def save_features(dataset: str) -> dict:
    F, ids = build_item_features(dataset)
    out = C.DATA_PROCESSED / dataset
    np.save(out / "item_features.npy", F)
    (out / "item_ids.json").write_text(json.dumps(ids), encoding="utf-8")
    sim = build_item_similarity(dataset)
    sim.to_parquet(out / "item_similarity.parquet", index=False)
    return {"dataset": dataset, "n_items": len(ids), "dim": int(F.shape[1]),
            "n_sim_pairs": int(len(sim))}


if __name__ == "__main__":
    for ds in ["movielens", "bookcrossing"]:
        try:
            print(save_features(ds))
        except Exception as e:  # noqa: BLE001
            print(f"{ds} FAILED: {type(e).__name__}: {e}")
