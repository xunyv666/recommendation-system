"""训练多视图图融合模型（FREEDOM 风格）并落库。

用法:
    python scripts/06_train_freedom.py --dataset movielens --epochs 60
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recsys.models.freedom import (FreedomLike, build_norm_adj,
                                  build_norm_item_graph, evaluate)


def load_split(dataset: str):
    """用 RecBole 生成与基线完全一致的 8:1:1 时间序切分。"""
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation

    from recsys.runner import build_config

    cfg = build_config(dataset, "LightGCN", {"embedding_size": 64, "n_layers": 3})
    cfg["saved"] = False
    config = Config(model="LightGCN", dataset=dataset, config_dict=cfg)
    ds = create_dataset(config)
    train_data, valid_data, test_data = data_preparation(config, ds)
    return config, ds, train_data, valid_data, test_data


def to_arrays(loader):
    it = loader.dataset.inter_feat
    return (it["user_id"].numpy().astype(np.int64),
            it["item_id"].numpy().astype(np.int64))


def history_list(loader) -> dict[int, list[int]]:
    """RecBole 的 uid2history_item 是以内部用户 id 为下标的数组。"""
    arr = loader.uid2history_item

    def conv(v):
        return [] if v is None else [int(x) for x in np.asarray(v).reshape(-1).tolist()]

    if isinstance(arr, dict):
        return {int(u): conv(v) for u, v in arr.items()}
    return {u: conv(arr[u]) for u in range(len(arr))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=C.PRIMARY_DATASET)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--dim", type=int, default=64)
    ap.add_argument("--layers", type=int, default=3)
    ap.add_argument("--batch", type=int, default=8192)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--align_weight", type=float, default=0.15)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--seed", type=int, default=C.SEED)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(max(1, torch.get_num_threads()))

    t0 = time.time()
    print(f"[FREEDOM] {args.dataset}: 构建切分 …", flush=True)
    config, ds, train_data, valid_data, test_data = load_split(args.dataset)
    n_users, n_items = ds.user_num, ds.item_num
    tr_u, tr_i = to_arrays(train_data)
    va_u, va_i = to_arrays(valid_data)
    te_u, te_i = to_arrays(test_data)
    print(f"    users={n_users} items={n_items} train={len(tr_u)} "
          f"valid={len(va_u)} test={len(te_u)}", flush=True)

    # 内容特征与内容相似图（与在线服务共用同一套三视图特征）
    feat = np.load(C.DATA_PROCESSED / args.dataset / "item_features.npy")
    feat_ids = json.loads(
        (C.DATA_PROCESSED / args.dataset / "item_ids.json").read_text(encoding="utf-8")
    )
    # 特征矩阵行序 = 原始 item_id 升序；需映射到 RecBole 内部 id 空间
    tok2id = ds.field2token_id["item_id"]
    feat_dim = feat.shape[1]
    feat_internal = np.zeros((n_items, feat_dim), dtype=np.float32)
    for tok, iid in tok2id.items():
        try:
            row = int(tok)
        except (TypeError, ValueError):
            continue
        pos = int(np.searchsorted(np.asarray(feat_ids, dtype=np.int64), row))
        if pos < len(feat_ids) and int(feat_ids[pos]) == row:
            feat_internal[iid] = feat[pos]

    sim = pd.read_parquet(C.DATA_PROCESSED / args.dataset / "item_similarity.parquet")
    orig2int = {}
    for tok, iid in tok2id.items():
        try:
            orig2int[int(tok)] = iid
        except (TypeError, ValueError):
            continue
    src = sim["src_id"].map(orig2int)
    dst = sim["dst_id"].map(orig2int)
    ok = src.notna() & dst.notna()
    src_i = src[ok].astype(int).to_numpy()
    dst_i = dst[ok].astype(int).to_numpy()
    sc = sim.loc[ok, "score"].astype(np.float32).to_numpy()
    # 相似度截断到 [0,1]，负相似对不参与内容图传播
    keep = sc > 0
    src_i, dst_i, sc = src_i[keep], dst_i[keep], sc[keep]
    print(f"    内容图边数={len(src_i):,}", flush=True)

    adj = build_norm_adj(n_users, n_items, tr_u, tr_i)
    item_adj = build_norm_item_graph(n_items, src_i, dst_i, sc)

    model = FreedomLike(n_users, n_items, feat_internal, adj, item_adj,
                        dim=args.dim, n_layers=args.layers)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-5)

    inter_t = torch.from_numpy(np.stack([tr_u, tr_i]))
    n_train = len(tr_u)
    test_users = np.unique(te_u)
    test_hist = history_list(test_data)
    valid_users = np.unique(va_u)
    valid_hist = history_list(valid_data)

    best_valid, best_state, best_epoch = -1.0, None, 0
    pos_u = torch.from_numpy(tr_u)
    pos_i = torch.from_numpy(tr_i)
    n_pairs = len(tr_u)
    for epoch in range(1, args.epochs + 1):
        model.train()
        # 全量正样本 + 每轮重采样负样本：每轮只做一次图传播，
        # 相比"每 batch 重算传播"快一个数量级（实测 15min → 2min），
        # 且负样本仍然逐轮刷新，不会退化成静态负采样。
        neg = torch.from_numpy(np.random.randint(1, n_items, size=n_pairs))

        u_c, i_c, u_t, i_t = model(inter_t)
        s_pos = model.pair_scores(u_c, i_c, u_t, i_t, pos_u, pos_i)
        s_neg = model.pair_scores(u_c, i_c, u_t, i_t, pos_u, neg)
        loss = -F.logsigmoid(s_pos - s_neg).mean()

        align_idx = torch.from_numpy(
            np.random.choice(n_items - 1, size=min(1024, n_items - 1),
                             replace=False) + 1)
        loss = loss + args.align_weight * model.align_loss(i_c, i_t, align_idx)
        loss = loss + 1e-5 * (model.user_emb.weight.norm(2).pow(2)
                              + model.item_emb.weight.norm(2).pow(2)) / n_users
        opt.zero_grad()
        loss.backward()
        opt.step()

        model.eval()
        with torch.no_grad():
            u_c, i_c, u_t, i_t = model(inter_t)
            scores = model.fused_scores(u_c, i_c, u_t, i_t)
        vm = evaluate(scores, valid_users, va_i, valid_hist, k=C.TOP_K)
        flag = ""
        if vm[f"ndcg@{C.TOP_K}"] > best_valid:
            best_valid = vm[f"ndcg@{C.TOP_K}"]
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            best_epoch = epoch
            flag = " *"
        print(f"    epoch {epoch:>3} loss={float(loss):.4f} "
              f"valid NDCG@{C.TOP_K}={vm[f'ndcg@{C.TOP_K}']:.4f} "
              f"Recall@{C.TOP_K}={vm[f'recall@{C.TOP_K}']:.4f}{flag}", flush=True)
        if epoch - best_epoch >= args.patience:
            print(f"    早停：验证集连续 {args.patience} 轮未提升", flush=True)
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        u_c, i_c, u_t, i_t = model(inter_t)
        scores = model.fused_scores(u_c, i_c, u_t, i_t)
    tm = evaluate(scores, test_users, te_i, test_hist, k=C.TOP_K)
    w = torch.softmax(model.fuse_logits, dim=0).detach().numpy()
    elapsed = time.time() - t0
    print(f"\n[FREEDOM] best_epoch={best_epoch} 融合权重 "
          f"collab={w[0]:.3f} content={w[1]:.3f}", flush=True)
    print(f"[FREEDOM] test: " + "  ".join(f"{k}={v:.4f}" for k, v in tm.items()),
          flush=True)

    out = {
        "dataset": args.dataset,
        "model": "FREEDOM",
        "config": {"dim": args.dim, "layers": args.layers, "lr": args.lr,
                   "batch": args.batch, "align_weight": args.align_weight,
                   "epochs": args.epochs, "patience": args.patience},
        "best_epoch": best_epoch,
        "best_valid": {f"ndcg@{C.TOP_K}": best_valid},
        "test": {k: round(float(v), 6) for k, v in tm.items()},
        "fuse_weight": {"collab": float(w[0]), "content": float(w[1])},
        "train_seconds": round(elapsed, 1),
    }
    p = C.RESULTS / f"freedom_{args.dataset}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    torch.save({"state_dict": model.state_dict(), "config": out["config"]},
               C.RESULTS / "checkpoints" / f"FREEDOM-{args.dataset}.pth")

    # ---------------- 落库：Top-N 推荐 ----------------
    from app import create_app
    from app.extensions import db
    from app.models import Item, Recommendation

    app = create_app()
    with app.app_context():
        rows = db.session.query(Item.id, Item.genres, Item.avg_rating,
                                Item.n_ratings).all()
        meta = {r[0]: (r[1] or "", r[2] or 0, r[3] or 0) for r in rows}

        int2orig = {}
        for tok, iid in tok2id.items():
            try:
                int2orig[iid] = int(tok)
            except (TypeError, ValueError):
                continue

        # 用户偏好题材（用于生成推荐理由）
        ratings = pd.read_parquet(C.DATA_PROCESSED / args.dataset / "ratings.parquet")
        items = pd.read_parquet(C.DATA_PROCESSED / args.dataset / "items.parquet")
        gmap = dict(zip(items["item_id"].astype(int),
                        items["genres"].fillna("").astype(str)))
        from collections import Counter
        prof = {}
        q = ratings["rating"].quantile(0.6)
        for uid, g in ratings[ratings["rating"] >= q].groupby("user_id"):
            c = Counter()
            for iid in g["item_id"]:
                for gg in gmap.get(int(iid), "").split("|"):
                    if gg:
                        c[gg] += 1
            prof[int(uid)] = [k for k, _ in c.most_common(3)]

        s = scores.detach().cpu().numpy()
        recs = []
        for u in test_users:
            hist = set(test_hist.get(int(u), []))
            row = s[int(u)].copy()
            row[0] = -np.inf
            for h in hist:
                row[h] = -np.inf
            order = np.argsort(-row)
            rank = 0
            for j in order:
                if not np.isfinite(row[j]):
                    break
                oid = int2orig.get(int(j))
                if oid is None or oid not in meta:
                    continue
                g, ar, nr = meta[oid]
                hit = [x for x in prof.get(int(u), []) if x in g.split("|")]
                reason = "多视图图融合模型同时利用了协同传播与内容图传播信号"
                if hit:
                    reason += f"，题材偏好匹配「{'、'.join(hit[:2])}」"
                if nr:
                    reason += f"，评分 {ar:.1f}（{nr} 人评）"
                rank += 1
                recs.append(dict(user_id=int(u), dataset=args.dataset,
                                 algo="FREEDOM", rank=rank, item_id=oid,
                                 score=float(row[j]), reason=reason))
                if rank >= args.topk:
                    break

        db.session.query(Recommendation).filter(
            Recommendation.dataset == args.dataset,
            Recommendation.algo == "FREEDOM",
        ).delete()
        db.session.commit()
        for s0 in range(0, len(recs), 20000):
            db.session.bulk_save_objects(
                [Recommendation(**r) for r in recs[s0:s0 + 20000]]
            )
            db.session.commit()
        print(f"[FREEDOM] 已写入 {len(recs)} 条推荐", flush=True)


if __name__ == "__main__":
    main()
