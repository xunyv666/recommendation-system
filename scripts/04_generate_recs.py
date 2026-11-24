"""离线生成推荐结果并落库（在线服务的"训练与 serving 解耦"关键一步）。

流程
----
1. 重建模型与数据集（与训练时完全一致的 config，保证 ID 空间对齐）
2. 从 checkpoint 加载最优权重
3. 对每个用户在全部物品上打分，过滤历史交互
4. 取 Top-N 写入 recommendations 表，同时生成推荐理由
5. 额外产出一个 hybrid 融合结果：图模型 + 内容 + 热度 三路加权

用法:
    python scripts/04_generate_recs.py --dataset movielens
    python scripts/04_generate_recs.py --dataset movielens --models LightGCN ItemKNN
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C


def newest_ckpt(model: str, dataset: str) -> str | None:
    """按文件修改时间取最新 checkpoint。

    不能用字符串排序：`FREEDOM-movielens.pth`（早期自研脚本产物）在字典序上
    排在 `FREEDOM-Nov-...pth` 之后，会被误当成"最新"。
    """
    files = glob.glob(str(C.RESULTS / "checkpoints" / f"{model}-*.pth"))
    if not files:
        return None
    return max(files, key=lambda p: Path(p).stat().st_mtime)


def build_model_and_data(dataset: str, model: str, cfg_extra: dict | None = None):
    """复刻训练时的数据与模型状态，返回 (config, dataset, test_loader, model_obj)。"""
    import torch
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation
    from recbole.utils import get_model, init_seed

    from recsys.runner import build_config, _patch_ncl

    if model == "FREEDOM":
        from recsys.models.freedom_recbole import register as _register_freedom

        _register_freedom()

    cfg = build_config(dataset, model, cfg_extra)
    cfg["saved"] = False
    config = Config(model=model, dataset=dataset, config_dict=cfg)
    init_seed(config["seed"], config["reproducibility"])
    ds = create_dataset(config)
    train_data, valid_data, test_data = data_preparation(config, ds)

    if model == "FREEDOM":
        from recsys.models.freedom_recbole import FREEDOM

        m = FREEDOM(config, train_data._dataset).to(config["device"])
    else:
        m = get_model(config["model"])(config, train_data._dataset).to(config["device"])
    if model == "NCL":
        m = _patch_ncl(m)

    ckpt = newest_ckpt(model, dataset)
    if not ckpt:
        raise FileNotFoundError(f"找不到 {model} 的 checkpoint，请先跑 02_run_benchmark.py")
    state = torch.load(ckpt, map_location=config["device"], weights_only=False)
    m.load_state_dict(state["state_dict"])
    m.eval()
    return config, ds, test_data, m, ckpt


def score_all_users(dataset: str, model: str, cfg_extra: dict | None = None):
    """返回 (原始 item_id 数组, 用户 id 数组, 分数矩阵 [n_users, n_items])。"""
    import torch
    from recbole.utils.case_study import full_sort_scores

    config, ds, test_data, m, ckpt = build_model_and_data(dataset, model, cfg_extra)

    tokens = ds.field2token_id["item_id"]          # 原始 token -> 内部 id
    internal_to_orig = np.zeros(ds.item_num, dtype=np.int64)
    for tok, iid in tokens.items():
        try:
            internal_to_orig[iid] = int(tok)
        except (TypeError, ValueError):
            continue        # 跳过 [PAD] / [UNK] 等特殊 token

    # 用测试集用户（即训练中出现、且有留出交互的用户）做推荐
    uid_tokens = ds.field2token_id["user_id"]
    # 内部 id → 原始 id：必须显式建映射，不能用 dict 的插入顺序，
    # 否则用户与分数行会错位（这是个很容易踩的隐蔽 bug）。
    internal_to_orig_user = {}
    for tok, iid in uid_tokens.items():
        try:
            internal_to_orig_user[iid] = int(tok)
        except (TypeError, ValueError):
            continue
    uids = sorted(internal_to_orig_user)
    chunks = []
    with torch.no_grad():
        for s in range(0, len(uids), 256):
            batch = uids[s:s + 256]
            chunks.append(full_sort_scores(batch, m, test_data, config["device"]).cpu())
    scores = torch.cat(chunks, dim=0).numpy()
    user_orig = np.array([internal_to_orig_user[i] for i in uids], dtype=np.int64)
    print(f"    scored {scores.shape[0]} users x {scores.shape[1]} items "
          f"from {Path(ckpt).name}", flush=True)
    return internal_to_orig, user_orig, scores, config, ds


def make_reason(model: str, user_genres: list[str], item_genres: str,
                score: float, avg_rating: float, n_ratings: int) -> str:
    """规则式推荐理由。

    不依赖大模型也能讲清楚"为什么推荐"，且完全可复现；
    若接入 LLM，只需把这段替换成 llm_rerank.generate_reason()。
    """
    item_g = [g for g in (item_genres or "").split("|") if g]
    hit = [g for g in user_genres if g in item_g]
    if model == "ItemKNN":
        base = "与你评分过的高分物品存在较强的共同受众"
    elif model in ("LightGCN", "SGL", "NCL", "DGCF", "FREEDOM"):
        base = "图模型在用户-物品交互图上捕捉到与你相似的偏好结构"
    elif model == "BPR":
        base = "隐因子模型判定你对这类物品的偏好概率更高"
    elif model == "NeuMF":
        base = "神经网络拟合出你对这类物品的非线性偏好"
    elif model == "content":
        base = "内容特征与你的历史偏好高度接近"
    elif model == "pop":
        base = "近期该领域的高热度内容"
    else:
        base = "综合多路召回信号后排序靠前"

    extra = []
    if hit:
        extra.append(f"题材同属「{'、'.join(hit[:2])}」")
    if n_ratings:
        extra.append(f"评分 {avg_rating:.1f}（{n_ratings} 人评）")
    return base + ("，" + "，".join(extra) if extra else "")


def user_genre_profile(dataset: str, uid2id: dict[int, int],
                       app_users: set[int] | None = None) -> dict[int, list[str]]:
    """从历史高分交互里提取每个用户的偏好类型（仅用于生成推荐理由）。"""
    items = pd.read_parquet(C.DATA_PROCESSED / dataset / "items.parquet")
    ratings = pd.read_parquet(C.DATA_PROCESSED / dataset / "ratings.parquet")
    if app_users:
        ratings = ratings[ratings["user_id"].isin(app_users)]
    gmap = dict(zip(items["item_id"].astype(int), items["genres"].fillna("")))
    out: dict[int, list[str]] = {}
    good = ratings[ratings["rating"] >= ratings["rating"].quantile(0.6)]
    for uid, g in good.groupby("user_id"):
        from collections import Counter
        c = Counter()
        for iid in g["item_id"]:
            for gg in str(gmap.get(int(iid), "")).split("|"):
                if gg:
                    c[gg] += 1
        out[int(uid)] = [k for k, _ in c.most_common(3)]
    return out


def save_recs(dataset: str, algo: str, results: list[dict]) -> int:
    """把推荐结果写入数据库（先删同 algo 旧结果）。"""
    from app import create_app
    from app.extensions import db
    from app.models import Recommendation

    app = create_app()
    with app.app_context():
        db.session.query(Recommendation).filter(
            Recommendation.dataset == dataset, Recommendation.algo == algo
        ).delete()
        db.session.commit()
        batch = []
        for r in results:
            batch.append(Recommendation(**r))
            if len(batch) >= 20000:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []
        if batch:
            db.session.bulk_save_objects(batch)
            db.session.commit()
    return len(results)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=C.PRIMARY_DATASET)
    ap.add_argument("--models", nargs="*",
                    default=["LightGCN", "ItemKNN", "BPR", "SGL", "NCL", "DGCF", "NeuMF", "EASE"])
    ap.add_argument("--topk", type=int, default=20)
    # hybrid 需要比展示条数更大的候选池，线上才能用 MMR 真正做"筛选"而不只是排序。
    # 0 表示与 --topk 相同。
    ap.add_argument("--topk-hybrid", type=int, default=0)
    args = ap.parse_args()
    hybrid_topk = args.topk_hybrid or args.topk

    from app import create_app
    from app.extensions import db
    from app.models import Item, User

    app = create_app()
    with app.app_context():
        item_rows = db.session.query(Item.id, Item.genres, Item.avg_rating,
                                     Item.n_ratings).filter(
            Item.dataset == args.dataset
        ).all()
        app_users = {
            r[0] for r in db.session.query(User.id).filter(
                User.dataset == args.dataset
            )
        }
    item_meta = {r[0]: (r[1] or "", r[2] or 0, r[3] or 0) for r in item_rows}
    profiles = user_genre_profile(args.dataset, item_meta, app_users)

    per_model_scores: dict[str, tuple] = {}

    # 全局维护"用户已交互物品"集合：推荐结果绝不能出现历史物品。
    # full_sort_scores 会把历史物品分数设为 -inf，但直接 argpartition
    # 取 top-k 时 -inf 会变成最大值被选中（这是极易忽略的坑），
    # 因此必须在排序时显式跳过非有限分数与历史物品。
    ratings_all = pd.read_parquet(C.DATA_PROCESSED / args.dataset / "ratings.parquet")
    if app_users:
        ratings_all = ratings_all[ratings_all["user_id"].isin(app_users)]
    seen = (
        ratings_all.groupby("user_id")["item_id"]
        .apply(lambda s: {int(x) for x in s})
        .to_dict()
    )

    for model in args.models:
        if model == "hybrid":
            continue   # hybrid 在主循环之后单独融合生成，不是 RecBole 模型名
        print(f"\n[GEN] {args.dataset} / {model}", flush=True)
        t0 = time.time()
        try:
            internal_to_orig, user_orig, scores, config, ds = score_all_users(
                args.dataset, model
            )
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f"    FAIL {type(e).__name__}: {e}", flush=True)
            continue

        per_model_scores[model] = (user_orig, internal_to_orig, scores)

        results = []
        for ui, uid in enumerate(user_orig):
            row = scores[ui]
            exclude = seen.get(int(uid), set())
            ug = profiles.get(int(uid), [])
            rank = 0
            for j in np.argsort(-row):
                if not np.isfinite(row[j]):
                    break
                orig = int(internal_to_orig[j])
                if orig <= 0 or orig not in item_meta or orig in exclude:
                    continue
                g, ar, nr = item_meta[orig]
                rank += 1
                results.append(dict(
                    user_id=int(uid), dataset=args.dataset, algo=model, rank=rank,
                    item_id=orig, score=float(row[j]),
                    reason=make_reason(model, ug, g, float(row[j]), ar, nr),
                ))
                if rank >= args.topk:
                    break
        n = save_recs(args.dataset, model, results)
        print(f"    saved {n} rows ({time.time() - t0:.0f}s)", flush=True)

    # ---------------- hybrid 融合 ----------------
    print(f"\n[GEN] {args.dataset} / hybrid (融合)", flush=True)
    graph_models = [m for m in ("LightGCN", "SGL", "NCL", "FREEDOM")
                    if m in per_model_scores]
    # 离线评测表明：按"线性 + 邻域 + 神经 + 内容"四族等权，比 9 路
    # 细粒度权重搜索更稳（测试集 NDCG 0.0722 vs 0.0687）。线上沿用
    # 这套强正则方案；图书域没有神经 checkpoint 时再退化为内容+热度。
    family_models = [m for m in ("EASE", "ItemKNN", "NeuMF")
                     if m in per_model_scores]

    if graph_models or family_models:
        ref_models = family_models or graph_models
        user_ref, item_map, _ = per_model_scores[ref_models[0]]
        if app_users:
            # 与数据库中的用户取交集，保证不生成"库里不存在的用户"的推荐
            keep_u = np.array([int(u) in app_users for u in user_ref])
            if not keep_u.all():
                user_ref = user_ref[keep_u]
                for m in list(per_model_scores):
                    u2, im2, sc2 = per_model_scores[m]
                    per_model_scores[m] = (u2, im2, sc2[keep_u])
        w_content, w_pop = 0.25, 0.0
    else:
        # 没有神经图模型（如图书域未训练）时，hybrid 退化为
        # 内容画像 + 热度两路融合，仍然可解释、可上线。
        import json as _json

        ids_path0 = C.DATA_PROCESSED / args.dataset / "item_ids.json"
        feat_ids0 = _json.loads(ids_path0.read_text(encoding="utf-8"))
        item_map = np.concatenate([[0], np.asarray(feat_ids0, dtype=np.int64)])
        user_ref = np.array(sorted(u for u in app_users if u in seen), dtype=np.int64)
        w_content, w_pop = 0.72, 0.28
        print(f"    无图模型，使用内容+热度融合，用户数={len(user_ref)}", flush=True)

    n_users = len(user_ref)

    def zscore(x: np.ndarray) -> np.ndarray:
        """按列做 z-score，但对 -inf（PAD / 历史交互）做特殊处理。

        坑点：full_sort_scores 会把 PAD 和用户已交互物品的分数置为 -inf。
        如果直接对含 -inf 的向量求均值/方差，统计量会被 -inf 破坏，
        融合结果整体退化成 -1e9 量级。正确做法是：
        只在有限值上计算均值方差，再把被屏蔽项统一压到 -3σ（最差档），
        这样另一路模型给出的信号仍然能把它救回来。
        """
        out = np.full(x.shape, -3.0, dtype=np.float32)
        finite = np.isfinite(x)
        n = int(finite.sum())
        if n < 2:
            return out
        vals = x[finite]
        mu, sd = float(vals.mean()), float(vals.std())
        sd = sd if sd > 1e-9 else 1.0
        z = (vals - mu) / sd
        # 截断极端值，避免单个异常分数主导融合；上界保留到 12，
        # 否则 ItemKNN 等重尾信号的 Top-10 会被压成平局。
        out[finite] = np.clip(z, -3.0, 12.0)
        return out

    fused = np.zeros((n_users, len(item_map)), dtype=np.float32)
    if family_models:
        model_w = 0.75 / len(family_models)
        for m in family_models:
            fused += model_w * zscore(per_model_scores[m][2])
    else:
        for m in graph_models:
            fused += 0.28 * zscore(per_model_scores[m][2])
        if "ItemKNN" in per_model_scores:
            fused += 0.16 * zscore(per_model_scores["ItemKNN"][2])

    # 内容 + 热度信号：直接从特征与热度表构造
    # 注意：分数矩阵的列空间是 RecBole 内部 id（含 [PAD]），长度 item_num；
    # 而特征矩阵按原始 item_id 排序，两者必须显式对齐，不能直接用下标相同的假设。
    feat_path = C.DATA_PROCESSED / args.dataset / "item_features.npy"
    ids_path = C.DATA_PROCESSED / args.dataset / "item_ids.json"
    if feat_path.exists() and ids_path.exists():
        import json

        import pandas as _pd

        F = np.load(feat_path)
        feat_ids = json.loads(ids_path.read_text(encoding="utf-8"))
        feat_pos = {int(iid): i for i, iid in enumerate(feat_ids)}
        orig_to_col = {int(o): i for i, o in enumerate(item_map) if o > 0}

        ratings = _pd.read_parquet(C.DATA_PROCESSED / args.dataset / "ratings.parquet")
        # 图书域只入库了活跃用户，这里同步裁剪，避免为 5 万用户构造画像
        if app_users:
            ratings = ratings[ratings["user_id"].isin(app_users)]
        pop = ratings.groupby("item_id").size()
        pop_col = np.zeros(len(item_map), dtype=np.float32)
        for oid, cnt in pop.items():
            j = orig_to_col.get(int(oid))
            if j is not None:
                pop_col[j] = float(cnt)
        pop_score = zscore(np.log1p(pop_col))

        # 用户画像 = 其高分物品特征的加权均值
        user_vec = {}
        q = ratings["rating"].quantile(0.6)
        for uid, g in ratings[ratings["rating"] >= q].groupby("user_id"):
            idx = [feat_pos[int(i)] for i in g["item_id"] if int(i) in feat_pos]
            if idx:
                user_vec[int(uid)] = F[idx].mean(axis=0).astype(np.float32)

        # 特征行 → 分数矩阵列的映射（一次性算好，避免每个用户都循环 1 万次）
        feat_to_col = np.full(len(feat_ids), -1, dtype=np.int64)
        for fi, iid in enumerate(feat_ids):
            j = orig_to_col.get(int(iid))
            if j is not None:
                feat_to_col[fi] = j
        keep_f = feat_to_col >= 0
        cols_f = feat_to_col[keep_f]

        content_col = np.full(len(item_map), np.nan, dtype=np.float32)
        for ui, uid in enumerate(user_ref):
            uv = user_vec.get(int(uid))
            if uv is None:
                continue
            nrm = float(np.linalg.norm(uv))
            if nrm <= 1e-9:
                continue
            sims = F @ (uv / nrm)
            content_col[:] = np.nan
            content_col[cols_f] = sims[keep_f]
            fused[ui] += w_content * zscore(content_col)
            fused[ui] += w_pop * pop_score

    # 显式排除用户已交互过的物品（seen 已在上面统一构建，对所有算法生效）
    results = []
    for ui, uid in enumerate(user_ref):
        row = fused[ui]
        exclude = seen.get(int(uid), set())
        order = np.argsort(-row)
        rank = 0
        for j in order:
            orig = int(item_map[j])
            if orig <= 0 or orig not in item_meta or orig in exclude:
                continue
            g, ar, nr = item_meta[orig]
            rank += 1
            results.append(dict(
                user_id=int(uid), dataset=args.dataset, algo="hybrid", rank=rank,
                item_id=orig, score=float(row[j]),
                reason=make_reason("hybrid", profiles.get(int(uid), []), g,
                                   float(row[j]), ar, nr),
            ))
            if rank >= hybrid_topk:
                break
    n = save_recs(args.dataset, "hybrid", results)
    print(f"    saved {n} rows", flush=True)
    print("\n[GEN] 全部完成", flush=True)


if __name__ == "__main__":
    main()
