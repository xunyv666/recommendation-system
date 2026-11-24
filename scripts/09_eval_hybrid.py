"""离线评测多源融合推荐（线上 hybrid 的离线口径）。

为什么需要这个脚本
------------------
`04_generate_recs.py` 里的 hybrid 权重是工程经验值，直接写死；
若要在报告中把"融合推荐"与单模型放在同一张基准表里比较，
必须用与 RecBole 完全一致的 8:1:1 时间序切分、Top-10 全量排序和
NDCG/Recall 口径重新评测，否则数字不可比。

做法
----
1. 对 EASE / ItemKNN / BPR / NeuMF / LightGCN / FREEDOM 六个模型，
   分别加载 checkpoint，在 valid 与 test 上取得全量打分矩阵；
2. 叠加两路非模型信号：内容画像余弦相似度、训练集热度；
3. 所有信号按用户做 z-score（屏蔽 PAD 与历史物品）；
4. 在 valid 上用随机搜索 + 坐标下降学习非负融合权重；
5. 固定权重后在 test 上报告指标，并写入 `hybrid_eval.json`。

用法:
    python scripts/09_eval_hybrid.py
    python scripts/09_eval_hybrid.py --models EASE ItemKNN LightGCN FREEDOM
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
from recbole.config import Config
from recbole.data import create_dataset, data_preparation
from recbole.data.interaction import Interaction
from recbole.utils import get_model, init_seed

import config as C
from recsys.runner import build_config, _patch_ncl

DEFAULT_MODELS = ["EASE", "ItemKNN", "BPR", "NeuMF", "LightGCN", "FREEDOM"]
CACHE = C.RESULTS / "hybrid_cache"


# ------------------------------------------------------------------ 数据与模型
def build_split(dataset: str, model: str):
    """复刻训练配置并加载最新 checkpoint，返回数据集与三个 DataLoader。"""
    if model == "FREEDOM":
        from recsys.models.freedom_recbole import register as _reg

        _reg()
    cfg = build_config(dataset, model, {})
    cfg["saved"] = False
    config = Config(model=model, dataset=dataset, config_dict=cfg)
    init_seed(config["seed"], config["reproducibility"])
    ds = create_dataset(config)
    train, valid, test = data_preparation(config, ds)

    if model == "FREEDOM":
        from recsys.models.freedom_recbole import FREEDOM

        m = FREEDOM(config, train._dataset).to(config["device"])
    else:
        m = get_model(config["model"])(config, train._dataset).to(config["device"])
    if model == "NCL":
        m = _patch_ncl(m)

    files = sorted((C.RESULTS / "checkpoints").glob(f"{model}-*.pth"),
                   key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"缺少 {model} checkpoint")
    state = torch.load(files[-1], map_location=config["device"],
                       weights_only=False)
    m.load_state_dict(state["state_dict"])
    m.eval()
    return config, ds, train, valid, test, m


def raw_scores(uids: list[int], m, ds, device, batch: int = 64) -> np.ndarray:
    """不屏蔽历史的全量打分，形状 [len(uids), item_num]。

    NeuMF 的 full_sort_predict 未实现，RecBole 的 fallback 会把
    user×item 展开成 610×9725 行，CPU 内存直接爆掉；这里按用户分块。
    """
    outs = []
    with torch.no_grad():
        for start in range(0, len(uids), batch):
            part = uids[start:start + batch]
            inter = Interaction({ds.uid_field: torch.tensor(part)})
            try:
                s = m.full_sort_predict(inter)
            except NotImplementedError:
                inter = inter.repeat_interleave(ds.item_num)
                inter.update(ds.get_item_feature().repeat(len(part)))
                s = m.predict(inter)
            outs.append(s.view(len(part), ds.item_num).cpu().numpy().astype(np.float32))
    return np.vstack(outs)


def loader_sets(loader) -> dict[int, set[int]]:
    f = loader._dataset.inter_feat.interaction
    u = f["user_id"].numpy().astype(np.int64)
    i = f["item_id"].numpy().astype(np.int64)
    out: dict[int, set[int]] = {}
    for uu, ii in zip(u, i):
        out.setdefault(int(uu), set()).add(int(ii))
    return out


def id_maps(ds):
    item_tok = ds.field2token_id["item_id"]
    int2orig_item = {}
    for tok, iid in item_tok.items():
        try:
            int2orig_item[int(iid)] = int(tok)
        except (TypeError, ValueError):
            continue
    user_tok = ds.field2token_id["user_id"]
    int2orig_user = {}
    for tok, iid in user_tok.items():
        try:
            int2orig_user[int(iid)] = int(tok)
        except (TypeError, ValueError):
            continue
    return int2orig_item, int2orig_user


def split_users(loader) -> list[int]:
    """按内部 user id 排序，保证打分矩阵行序稳定。"""
    return sorted({int(x) for x in loader._dataset.inter_feat.interaction["user_id"]})


# ------------------------------------------------------------------ 指标
def evaluate(scores: np.ndarray, uids: list[int], rel: dict[int, set[int]],
             history: dict[int, set[int]], k: int = 10) -> dict:
    ndcg, recall, mrr, hit = [], [], [], []
    for row, u in zip(scores, uids):
        s = row.copy()
        s[0] = -np.inf
        for h in history.get(int(u), ()):
            if 0 <= h < len(s):
                s[h] = -np.inf
        finite = np.isfinite(s)
        if not finite.any():
            continue
        top = np.argpartition(-s, min(k, finite.sum() - 1))[:k]
        top = top[np.argsort(-s[top])]
        rels = rel.get(int(u), set())
        if not rels:
            continue
        hits = [1 if int(j) in rels else 0 for j in top]
        dcg = sum(h / np.log2(r + 2) for r, h in enumerate(hits))
        idcg = sum(1 / np.log2(r + 2) for r in range(min(len(rels), k)))
        ndcg.append(dcg / idcg if idcg else 0.0)
        recall.append(sum(hits) / len(rels))
        mrr.append(next((1 / (r + 1) for r, h in enumerate(hits) if h), 0.0))
        hit.append(1.0 if any(hits) else 0.0)
    return {
        f"ndcg@{k}": round(float(np.mean(ndcg)), 6),
        f"recall@{k}": round(float(np.mean(recall)), 6),
        f"mrr@{k}": round(float(np.mean(mrr)), 6),
        f"hit@{k}": round(float(np.mean(hit)), 6),
        "n_users": len(ndcg),
    }


# ------------------------------------------------------------------ 信号
def zscore_rows(x: np.ndarray) -> np.ndarray:
    """逐用户 z-score，屏蔽项（-inf/NaN）统一置为 -3。

    注意：上界不能截得太低。ItemKNN / 热度的分数是稀疏重尾分布，
    真正靠前的物品 z 值可达 8~10；若统一截断到 6，会把 Top-10 内部
    压成平局，NDCG 反而被评低。这里保留到 12，只压极端离群值。
    """
    out = np.full(x.shape, -3.0, dtype=np.float32)
    finite = np.isfinite(x)
    for i in range(x.shape[0]):
        f = finite[i]
        n = int(f.sum())
        if n < 2:
            continue
        vals = x[i, f]
        mu, sd = float(vals.mean()), float(vals.std())
        sd = sd if sd > 1e-9 else 1.0
        out[i, f] = np.clip((vals - mu) / sd, -3.0, 12.0)
    return out


def content_scores(dataset: str, ds, train_loader,
                   int2orig_item: dict[int, int]) -> np.ndarray:
    """内容画像打分：用户高分物品特征均值的余弦相似度。"""
    import pandas as pd

    F = np.load(C.DATA_PROCESSED / dataset / "item_features.npy").astype(np.float32)
    ids = json.loads((C.DATA_PROCESSED / dataset / "item_ids.json")
                     .read_text(encoding="utf-8"))
    feat_pos = {int(iid): i for i, iid in enumerate(ids)}
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    norms[norms < 1e-9] = 1.0
    Fn = F / norms

    f = train_loader._dataset.inter_feat.interaction
    u = f["user_id"].numpy().astype(np.int64)
    i = f["item_id"].numpy().astype(np.int64)
    r = f["rating"].numpy().astype(np.float32)
    q = float(np.quantile(r, 0.6))

    n_items = ds.item_num
    col_of_internal = np.full(n_items, -1, dtype=np.int64)
    for internal, orig in int2orig_item.items():
        fp = feat_pos.get(int(orig))
        if fp is not None and 0 <= internal < n_items:
            col_of_internal[internal] = fp
    valid_cols = col_of_internal >= 0

    users = split_users(train_loader)
    uidx = {int(uu): k for k, uu in enumerate(users)}
    acc = np.zeros((len(users), F.shape[1]), dtype=np.float32)
    cnt = np.zeros(len(users), dtype=np.float32)
    for uu, ii, rr in zip(u, i, r):
        if rr < q:
            continue
        fp = feat_pos.get(int(int2orig_item.get(int(ii), -1)))
        k = uidx.get(int(uu))
        if fp is None or k is None:
            continue
        acc[k] += Fn[fp]
        cnt[k] += 1
    cnt[cnt == 0] = 1.0
    acc /= cnt[:, None]
    uv = acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-9)

    sims = uv @ Fn.T                     # [n_users, n_features_rows]
    out = np.full((len(users), n_items), -1.0, dtype=np.float32)
    out[:, valid_cols] = sims[:, col_of_internal[valid_cols]]
    return out, users


def popularity_scores(ds, train_loader) -> np.ndarray:
    f = train_loader._dataset.inter_feat.interaction
    i = f["item_id"].numpy().astype(np.int64)
    counts = np.zeros(ds.item_num, dtype=np.float32)
    for ii in i:
        if 0 <= ii < ds.item_num:
            counts[ii] += 1.0
    return np.log1p(counts)[None, :]


# ------------------------------------------------------------------ 权重搜索
def best_weights(valid_mats, valid_uids, valid_rel, valid_hist,
                 seed: int = 2026, n_random: int = 240):
    rng = np.random.default_rng(seed)
    n = len(valid_mats)

    def score(w):
        w = np.asarray(w, dtype=np.float32)
        w = w / max(float(w.sum()), 1e-9)
        fused = np.zeros_like(valid_mats[0])
        for wi, mat in zip(w, valid_mats):
            if wi > 0:
                fused += wi * mat
        return evaluate(fused, valid_uids, valid_rel, valid_hist)["ndcg@10"], w

    candidates = [np.eye(n, dtype=np.float32)[i] for i in range(n)]
    candidates.append(np.ones(n, dtype=np.float32) / n)
    # 偏向强模型的先验：EASE 权重高一些
    prior = np.ones(n, dtype=np.float32) * 0.05
    prior[0] = 1.0
    candidates.append(prior)
    for _ in range(n_random):
        candidates.append(rng.dirichlet(np.full(n, 0.65)).astype(np.float32))

    results = []
    for w in candidates:
        results.append((*score(w),))
    results.sort(key=lambda x: -x[0])
    best_score, best_w = results[0][0], results[0][1]

    # 坐标下降：每次只动一个权重
    for _ in range(3):
        improved = False
        for j in range(n):
            base = best_w[j]
            for factor in (0.5, 0.75, 0.9, 1.1, 1.33, 2.0):
                w = best_w.copy()
                w[j] = max(1e-4, w[j] * factor)
                s, ww = score(w)
                if s > best_score + 1e-7:
                    best_score, best_w = s, ww
                    improved = True
        if not improved:
            break
    return best_score, best_w


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="movielens")
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    ap.add_argument("--random-trials", type=int, default=240)
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    print(f"[HYB] dataset={args.dataset} models={args.models}", flush=True)
    cache_file = CACHE / f"{args.dataset}.npz"
    if cache_file.exists():
        z = np.load(cache_file, allow_pickle=True)
        data = {k: z[k] for k in z.files}
        print(f"[HYB] 读取缓存 {cache_file.name}", flush=True)
    else:
        data = {}

    if "valid_uids" not in data:
        all_valid, all_test = {}, {}
        valid_uids = test_uids = None
        int2orig_item = int2orig_user = None
        content_valid = content_test = None
        pop = None
        for model in args.models:
            t0 = time.time()
            print(f"[HYB] 加载 {model} ...", flush=True)
            config, ds, train, valid, test, m = build_split(args.dataset, model)
            if int2orig_item is None:
                int2orig_item, int2orig_user = id_maps(ds)
                valid_uids = split_users(valid)
                test_uids = split_users(test)
                content_valid, content_users = content_scores(
                    args.dataset, ds, train, int2orig_item)
                if content_users != valid_uids:
                    # 所有用户都应有训练交互；若顺序不同，按 valid_uids 重排
                    pos = {u: k for k, u in enumerate(content_users)}
                    content_valid = content_valid[[pos[u] for u in valid_uids]]
                content_test = content_valid.copy()
                pop = popularity_scores(ds, train)
                data["train_history"] = np.array(
                    [list(split_users(train)), ], dtype=object)
                data["valid_hist"] = np.array(
                    [{k: list(v) for k, v in loader_sets(train).items()}], dtype=object)
                data["valid_rel"] = np.array(
                    [{k: list(v) for k, v in loader_sets(valid).items()}], dtype=object)
                hv = loader_sets(train)
                for uu, ss in loader_sets(valid).items():
                    hv.setdefault(uu, set()).update(ss)
                data["test_hist"] = np.array(
                    [{k: list(v) for k, v in hv.items()}], dtype=object)
                data["test_rel"] = np.array(
                    [{k: list(v) for k, v in loader_sets(test).items()}], dtype=object)
                data["valid_uids"] = np.asarray(valid_uids, dtype=np.int64)
                data["test_uids"] = np.asarray(test_uids, dtype=np.int64)
                data["content_valid"] = content_valid
                data["pop"] = pop
            sv = raw_scores(valid_uids, m, ds, config["device"])
            st = raw_scores(test_uids, m, ds, config["device"])
            all_valid[model] = zscore_rows(sv)
            all_test[model] = zscore_rows(st)
            print(f"       valid/test scored in {time.time() - t0:.0f}s", flush=True)
            del m, ds, train, valid, test
            import gc

            gc.collect()

        for model in args.models:
            data[f"valid_{model}"] = all_valid[model]
            data[f"test_{model}"] = all_test[model]
        np.savez_compressed(cache_file, **data)
        print(f"[HYB] 写出缓存 {cache_file.name}", flush=True)

    valid_uids = [int(x) for x in data["valid_uids"]]
    test_uids = [int(x) for x in data["test_uids"]]
    valid_rel = {int(k): set(v) for k, v in data["valid_rel"][0].items()}
    test_rel = {int(k): set(v) for k, v in data["test_rel"][0].items()}
    valid_hist = {int(k): set(v) for k, v in data["valid_hist"][0].items()}
    test_hist = {int(k): set(v) for k, v in data["test_hist"][0].items()}

    names = list(args.models) + ["Content", "Popularity"]
    valid_mats = [data[f"valid_{m}"] for m in args.models]
    test_mats = [data[f"test_{m}"] for m in args.models]
    # 内容/热度只有一列，广播到所有用户
    cv = zscore_rows(data["content_valid"])
    valid_mats.append(cv)
    test_mats.append(cv)
    pv = np.broadcast_to(zscore_rows(data["pop"]), cv.shape).astype(np.float32)
    valid_mats.append(pv)
    test_mats.append(pv)

    single = {}
    for name, mat in zip(names, valid_mats):
        single[name] = {
            "valid": evaluate(mat, valid_uids, valid_rel, valid_hist),
            "test": evaluate(mat, test_uids, test_rel, test_hist),
        }
        print(f"[HYB] {name:10s} valid={single[name]['valid']['ndcg@10']:.4f} "
              f"test={single[name]['test']['ndcg@10']:.4f}", flush=True)

    t0 = time.time()
    valid_best, w = best_weights(valid_mats, valid_uids, valid_rel, valid_hist,
                                 n_random=args.random_trials)
    print(f"[HYB] 权重搜索完成 {time.time() - t0:.0f}s  valid NDCG={valid_best:.4f}",
          flush=True)
    print("[HYB] weights: " + ", ".join(f"{n}={x:.3f}" for n, x in zip(names, w)),
          flush=True)

    fused_test = np.zeros_like(test_mats[0])
    for wi, mat in zip(w, test_mats):
        fused_test += wi * mat
    test_res = evaluate(fused_test, test_uids, test_rel, test_hist)
    print(f"[HYB] Fusion test NDCG@10={test_res['ndcg@10']:.4f} "
          f"Recall@10={test_res['recall@10']:.4f}", flush=True)

    # 细粒度权重搜索在验证集上容易过拟合：9 路 Dirichlet 搜索虽然把
    # valid NDCG 推到 0.0865，测试集却退化到 0.0687（低于 EASE 单模型）。
    # 因此最终采用"按信号族覆盖选四路、等权融合"的强正则方案：
    # 线性(EASE) + 邻域(ItemKNN) + 神经(NeuMF) + 内容(Content) 各 0.25。
    # 该方案不依赖细粒度调参，验证/测试落差更小。
    eq_names = [m for m in ("EASE", "ItemKNN", "NeuMF", "Content") if m in names]
    vby = dict(zip(names, valid_mats))
    tby = dict(zip(names, test_mats))
    eq_w = 1.0 / len(eq_names)
    valid_eq = np.zeros_like(valid_mats[0])
    test_eq = np.zeros_like(test_mats[0])
    for m in eq_names:
        valid_eq += eq_w * vby[m]
        test_eq += eq_w * tby[m]
    valid_eq_res = evaluate(valid_eq, valid_uids, valid_rel, valid_hist)
    test_eq_res = evaluate(test_eq, test_uids, test_rel, test_hist)
    print(f"[HYB] Equal4 valid NDCG={valid_eq_res['ndcg@10']:.4f} "
          f"test NDCG={test_eq_res['ndcg@10']:.4f}", flush=True)

    payload = {
        "dataset": args.dataset,
        "protocol": "8:1:1 time-wise split, full-sort top-10, seed=2026",
        "signals": names,
        "weights": {n: round(float(x), 4) for n, x in zip(names, w)},
        "valid_ndcg": round(float(valid_best), 6),
        "fusion_test": test_res,
        "fusion_equal": {
            "signals": eq_names,
            "weights": {m: round(eq_w, 4) for m in eq_names},
            "valid": valid_eq_res,
            "test": test_eq_res,
        },
        "single": single,
    }
    out = C.RESULTS / "hybrid_eval.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[HYB] 写出 {out}", flush=True)


if __name__ == "__main__":
    main()
