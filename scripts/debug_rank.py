"""诊断 2：直接检查 RecBole LightGCN 的打分矩阵与测试正样本的对齐关系。

如果正样本在分数行里的排名普遍很靠前，说明是我的 Top-K 实现有 bug；
如果排名普遍在几千名，说明模型本身就不行（与 RecBole 报的 0.04 矛盾）。
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C


def hist(loader):
    arr = loader.uid2history_item

    def conv(v):
        return [] if v is None else [int(x) for x in np.asarray(v).reshape(-1).tolist()]

    return {u: conv(arr[u]) for u in range(len(arr))}


def main() -> None:
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation
    from recbole.utils import get_model, init_seed
    from recbole.utils.case_study import full_sort_scores

    from recsys.runner import build_config

    cfg = build_config("movielens", "LightGCN", {"embedding_size": 64, "n_layers": 3})
    cfg["saved"] = False
    config = Config(model="LightGCN", dataset="movielens", config_dict=cfg)
    init_seed(config["seed"], config["reproducibility"])
    ds = create_dataset(config)
    tr, va, te = data_preparation(config, ds)
    m = get_model("LightGCN")(config, tr._dataset).to("cpu")
    ck = sorted(glob.glob(str(C.RESULTS / "checkpoints" / "LightGCN-*.pth")))[-1]
    print("checkpoint:", Path(ck).name)
    state = torch.load(ck, map_location="cpu", weights_only=False)
    m.load_state_dict(state["state_dict"])
    m.eval()

    it = te.dataset.inter_feat
    tu = it["user_id"].numpy()
    ti = it["item_id"].numpy()
    print("test interactions:", len(tu), "users:", len(np.unique(tu)),
          "item id range:", int(ti.min()), int(ti.max()))
    print("dataset.item_num:", ds.item_num, "user_num:", ds.user_num)

    uids = sorted(np.unique(tu).tolist())
    with torch.no_grad():
        sc = full_sort_scores(uids, m, te, torch.device("cpu")).numpy()
    print("scores shape:", sc.shape, "finite per row:",
          int(np.isfinite(sc[0]).sum()))

    h = hist(te)
    pos_map = {}
    for u, i in zip(tu, ti):
        pos_map.setdefault(int(u), set()).add(int(i))

    ranks = []
    for k, u in enumerate(uids):
        row = sc[k].copy()
        for x in h.get(u, []):
            row[x] = -np.inf
        p = pos_map.get(u, set())
        for i in p:
            r = int((row > row[i]).sum()) + 1
            ranks.append(r)
    ranks = np.array(ranks)
    print("pos-item rank: mean=%.0f median=%.0f p10=%.0f p90=%.0f  top10=%.3f"
          % (ranks.mean(), np.median(ranks), np.percentile(ranks, 10),
             np.percentile(ranks, 90), float((ranks <= 10).mean())))

    u = uids[0]
    row = sc[0].copy()
    for x in h.get(u, []):
        row[x] = -np.inf
    top = np.argsort(-row)[:10]
    print("user", u, "pos:", sorted(pos_map.get(u, set()))[:10],
          "top10:", top.tolist())


if __name__ == "__main__":
    main()
