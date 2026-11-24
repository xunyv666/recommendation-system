"""临时探针：验证自写全排序评测与 RecBole 官方指标口径一致。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
from recbole.config import Config
from recbole.data import create_dataset, data_preparation
from recbole.data.interaction import Interaction
from recbole.utils import get_model, init_seed

import config as C
from recsys.runner import build_config


def build(dataset: str, model: str):
    cfg = build_config(dataset, model, {})
    cfg["saved"] = False
    config = Config(model=model, dataset=dataset, config_dict=cfg)
    init_seed(config["seed"], config["reproducibility"])
    ds = create_dataset(config)
    train, valid, test = data_preparation(config, ds)
    m = get_model(config["model"])(config, train._dataset).to(config["device"])
    files = sorted((C.RESULTS / "checkpoints").glob(f"{model}-*.pth"),
                   key=lambda p: p.stat().st_mtime)
    state = torch.load(files[-1], map_location=config["device"],
                       weights_only=False)
    m.load_state_dict(state["state_dict"])
    m.eval()
    return config, ds, train, valid, test, m


def raw_scores(uids, m, ds, device):
    with torch.no_grad():
        inter = Interaction({ds.uid_field: torch.tensor(uids)})
        try:
            s = m.full_sort_predict(inter)
        except NotImplementedError:
            inter = inter.repeat_interleave(ds.item_num)
            inter.update(ds.get_item_feature().repeat(len(uids)))
            s = m.predict(inter)
        return s.view(len(uids), ds.item_num).cpu().numpy()


def split_sets(loader):
    f = loader._dataset.inter_feat.interaction
    u = f["user_id"].numpy().astype(np.int64)
    i = f["item_id"].numpy().astype(np.int64)
    out = {}
    for uu, ii in zip(u, i):
        out.setdefault(int(uu), set()).add(int(ii))
    return out


def evaluate(scores, uids, rel, history, k=10):
    ndcg, recall, mrr, hit = [], [], [], []
    for row, u in zip(scores, uids):
        s = row.copy()
        s[0] = -np.inf
        for h in history.get(int(u), ()):
            s[h] = -np.inf
        top = np.argpartition(-s, k)[:k]
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
    return {"ndcg@10": float(np.mean(ndcg)), "recall@10": float(np.mean(recall)),
            "mrr@10": float(np.mean(mrr)), "hit@10": float(np.mean(hit)),
            "n": len(ndcg)}


def main():
    config, ds, train, valid, test, m = build("movielens", "EASE")
    tok2int = ds.field2token_id["item_id"]
    int2orig = {}
    for tok, iid in tok2int.items():
        try:
            int2orig[int(iid)] = int(tok)
        except (TypeError, ValueError):
            pass
    utok = ds.field2token_id["user_id"]
    int2orig_u = {}
    for tok, iid in utok.items():
        try:
            int2orig_u[int(iid)] = int(tok)
        except (TypeError, ValueError):
            pass
    test_int_users = sorted({int(x) for x in test._dataset.inter_feat.interaction["user_id"]})
    uids = [u for u in test_int_users if u in int2orig_u]
    scores = raw_scores(uids, m, ds, config["device"])
    rel = split_sets(test)
    hist = split_sets(train)
    for u, s in split_sets(valid).items():
        hist.setdefault(u, set()).update(s)
    print(evaluate(scores, uids, rel, hist))


if __name__ == "__main__":
    main()
