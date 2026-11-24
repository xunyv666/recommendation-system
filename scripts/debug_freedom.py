"""诊断：分别评测 FREEDOM 的协同视图/内容视图，并用同一套指标复算 RecBole 基线。

目的是排除"指标实现有 bug"与"模型有问题"两种可能，定位指标偏低的原因。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recsys.models.freedom import (FreedomLike, build_norm_adj,
                                   build_norm_item_graph, evaluate)


def load_split(dataset: str):
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation
    from recsys.runner import build_config

    cfg = build_config(dataset, "LightGCN", {"embedding_size": 64, "n_layers": 3})
    cfg["saved"] = False
    config = Config(model="LightGCN", dataset=dataset, config_dict=cfg)
    ds = create_dataset(config)
    return (config, ds, *data_preparation(config, ds))


def to_arrays(loader):
    it = loader.dataset.inter_feat
    return (it["user_id"].numpy().astype(np.int64),
            it["item_id"].numpy().astype(np.int64))


def history_list(loader):
    arr = loader.uid2history_item

    def conv(v):
        return [] if v is None else [int(x) for x in np.asarray(v).reshape(-1).tolist()]

    if isinstance(arr, dict):
        return {int(u): conv(v) for u, v in arr.items()}
    return {u: conv(arr[u]) for u in range(len(arr))}


def main() -> None:
    ds_name = "movielens"
    config, ds, train_data, valid_data, test_data = load_split(ds_name)
    n_users, n_items = ds.user_num, ds.item_num
    tr_u, tr_i = to_arrays(train_data)
    va_u, va_i = to_arrays(valid_data)
    te_u, te_i = to_arrays(test_data)
    te_hist = history_list(test_data)

    # ---------- 1) 用同一套指标复算 RecBole 的 LightGCN，验证指标实现 ----------
    from recbole.utils.case_study import full_sort_scores
    from recsys.runner import build_config

    cfg = build_config(ds_name, "LightGCN", {"embedding_size": 64, "n_layers": 3})
    cfg["saved"] = False
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation
    from recbole.utils import get_model, init_seed

    config2 = Config(model="LightGCN", dataset=ds_name, config_dict=cfg)
    init_seed(config2["seed"], config2["reproducibility"])
    ds2 = create_dataset(config2)
    tr2, va2, te2 = data_preparation(config2, ds2)
    m = get_model("LightGCN")(config2, tr2._dataset).to("cpu")
    import glob
    ck = sorted(glob.glob(str(C.RESULTS / "checkpoints" / "LightGCN-*.pth")))[-1]
    state = torch.load(ck, map_location="cpu", weights_only=False)
    m.load_state_dict(state["state_dict"])
    m.eval()
    uids = sorted(range(1, ds2.user_num))
    with torch.no_grad():
        sc = full_sort_scores(uids, m, te2, torch.device("cpu")).numpy()
    sc = np.vstack([np.full((1, sc.shape[1]), -np.inf), sc])
    hist2 = history_list(te2)
    met = evaluate(torch.from_numpy(sc.astype(np.float32)),
                   np.unique(te_u), te_i, hist2, k=C.TOP_K)
    print("[SANITY] 我的指标实现 × RecBole LightGCN:", json.dumps(
        {k: round(v, 4) for k, v in met.items()}, ensure_ascii=False))

    # ---------- 2) 载入 FREEDOM 权重，分视图评测 ----------
    feat = np.load(C.DATA_PROCESSED / ds_name / "item_features.npy")
    feat_ids = json.loads((C.DATA_PROCESSED / ds_name / "item_ids.json").read_text("utf-8"))
    tok2id = ds.field2token_id["item_id"]
    feat_internal = np.zeros((n_items, feat.shape[1]), dtype=np.float32)
    for tok, iid in tok2id.items():
        try:
            row = int(tok)
        except (TypeError, ValueError):
            continue
        pos = int(np.searchsorted(np.asarray(feat_ids, dtype=np.int64), row))
        if pos < len(feat_ids) and int(feat_ids[pos]) == row:
            feat_internal[iid] = feat[pos]

    import pandas as pd
    sim = pd.read_parquet(C.DATA_PROCESSED / ds_name / "item_similarity.parquet")
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
    sc_v = sim.loc[ok, "score"].astype(np.float32).to_numpy()
    keep = sc_v > 0
    adj = build_norm_adj(n_users, n_items, tr_u, tr_i)
    iadj = build_norm_item_graph(n_items, src_i[keep], dst_i[keep], sc_v[keep])

    model = FreedomLike(n_users, n_items, feat_internal, adj, iadj, dim=64, n_layers=3)
    ckpt = C.RESULTS / "checkpoints" / "FREEDOM-movielens.pth"
    state = torch.load(ckpt, map_location="cpu", weights_only=False)
    model.load_state_dict(state["state_dict"])
    model.eval()
    inter_t = torch.from_numpy(np.stack([tr_u, tr_i]))
    with torch.no_grad():
        u_c, i_c, u_t, i_t = model(inter_t)
        full = model.fused_scores(u_c, i_c, u_t, i_t)
        collab = u_c @ i_c.t()
        content = u_t @ i_t.t()
        w = model._scales()
    users = np.unique(te_u)
    for name, mat in [("collab", collab), ("content", content), ("fused", full)]:
        met = evaluate(mat, users, te_i, te_hist, k=C.TOP_K)
        print(f"[VIEW] {name:<8}", json.dumps({k: round(v, 4) for k, v in met.items()},
                                              ensure_ascii=False))
    print(f"[VIEW] 融合尺度 collab={float(w[0]):.3f} content={float(w[1]):.3f}")

    # ---------- 3) 物品侧统计：内容视图是否退化为常数 ----------
    print("[STAT] content emb std:", float(i_t.std()), "collab emb std:", float(i_c.std()))
    print("[STAT] content score std per user (mean):", float(content.std(dim=1).mean()),
          "collab score std per user (mean):", float(collab.std(dim=1).mean()))


if __name__ == "__main__":
    main()
