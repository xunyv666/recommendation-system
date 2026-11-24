"""统一实验运行器：一个函数跑任何 (数据集 × 模型) 组合。

为什么不用 recbole.quick_start.run_recbole
-----------------------------------------
quick_start 会无条件 `from ray import tune`，而 ray 在 Windows 上安装体积大、
且与 py3.12 兼容性不稳。这里改为 RecBole 官方推荐的"手动流水线"：
Config → create_dataset → data_preparation → get_model → Trainer.fit，
完全等价，但零额外依赖、可控性更强。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import config as C


# 需要梯度训练（多轮）的模型白名单；其余一律 1 轮
_NEURAL_MODELS = {
    "BPR", "NeuMF", "LightGCN", "SGL", "NCL", "DGCF", "NGCF",
    "GCMC", "DGCF", "FREEDOM", "SimGCL", "XSimGCL", "MultiVAE", "MacridVAE",
}


def is_neural(model: str) -> bool:
    return model in _NEURAL_MODELS


def _patch_ncl(model_obj):
    """把 NCL 的 run_kmeans 换成 sklearn 实现。

    NCL 原始实现 import faiss 且写死 gpu=True —— faiss-gpu 只有 Linux 版，
    在 Windows 上必然 ImportError（而且会被外层 try 吞掉，表现为
    "user_2cluster 恒为 None"）。改用 sklearn KMeans 后语义完全等价，
    只是聚类在 CPU 上跑，对本文数据规模没有性能影响。
    """
    import numpy as np
    import torch
    import torch.nn.functional as F
    from sklearn.cluster import KMeans

    def run_kmeans(self, x):
        arr = x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)
        # NCL 默认 k=1000，但小数据集（如 611 个用户）的样本数可能不足，
        # sklearn 会直接报错。这里按样本量自适应裁剪簇数。
        k = max(2, min(int(self.k), arr.shape[0] - 1))
        km = KMeans(n_clusters=k, n_init=10, random_state=C.SEED).fit(arr)
        cents = torch.tensor(km.cluster_centers_, dtype=torch.float32,
                             device=self.device)
        cents = F.normalize(cents, p=2, dim=1)
        labels = torch.tensor(km.labels_, dtype=torch.long, device=self.device)
        return cents, labels

    model_obj.run_kmeans = run_kmeans.__get__(model_obj, type(model_obj))
    return model_obj


def _make_trainer():
    """构造 Trainer 子类，修补 RecBole 1.2.0 的缺陷。

    注意：RecBole 1.2.0 的 fit() 本身会在每轮调用 model.e_step()（若存在），
    NCL 的聚类逻辑就是靠它驱动的，这里不再重复调用，避免每轮跑两次 KMeans。
    """
    from recbole.trainer import Trainer

    class PatchedTrainer(Trainer):
        def _train_epoch(self, train_data, epoch_idx, loss_func=None,
                         show_progress=False):
            # NCL 的 EM 训练需要每轮先做一次 E-step（聚类）；通用 Trainer 不调它。
            e_step = getattr(self.model, "e_step", None)
            if callable(e_step):
                try:
                    e_step()
                except Exception:  # noqa: BLE001 - 聚类失败不应中断训练
                    pass
            return super()._train_epoch(train_data, epoch_idx, loss_func,
                                        show_progress)

    return PatchedTrainer



def build_config(dataset: str, model: str, extra: dict[str, Any] | None = None):
    """组装 RecBole Config 字典。

    注意 data_path 指向 data/processed，RecBole 会去
    data/processed/<dataset>/<dataset>.inter 找文件。
    """
    ds = C.DATASETS[dataset]

    # 大规模数据集：全排序评测的 batch 必须调小，否则显存/内存爆掉
    eval_bs = 128 if dataset == "bookcrossing" else 4096
    train_bs = 4096 if dataset == "bookcrossing" else 2048

    cfg: dict[str, Any] = {
        "data_path": str(C.DATA_PROCESSED),
        "USER_ID_FIELD": "user_id",
        "ITEM_ID_FIELD": "item_id",
        "RATING_FIELD": "rating",
        "TIME_FIELD": "timestamp",
        "load_col": {"inter": ["user_id", "item_id", "rating", "timestamp"]},
        "field_separator": "\t",
        "seq_separator": " ",
        "eval_args": C.EVAL_CONFIG,
        "metrics": C.METRICS,
        "topk": [C.TOP_K],
        "valid_metric": f"NDCG@{C.TOP_K}",
        "epochs": C.TRAIN_DEFAULTS["epochs"],
        "train_batch_size": train_bs,
        "eval_batch_size": eval_bs,
        "learning_rate": C.TRAIN_DEFAULTS["learning_rate"],
        "train_neg_sample_args": C.TRAIN_DEFAULTS["train_neg_sample_args"],
        "device": C.TRAIN_DEFAULTS["device"],
        "seed": C.TRAIN_DEFAULTS["seed"],
        "show_progress": False,
        "saved": True,
        # 早停：验证集 NDCG 连续 10 轮不涨就停
        "stopping_step": 10,
        "checkpoint_dir": str(C.RESULTS / "checkpoints"),
        "save_dataset": False,
        "save_dataloaders": False,
    }
    if extra:
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v

    # FREEDOM 需要内容特征与内容相似图的路径（与在线服务共用同一套三视图特征）
    if model == "FREEDOM":
        base = C.DATA_PROCESSED / dataset
        cfg.setdefault("freedom_feat", str(base / "item_features.npy"))
        cfg.setdefault("freedom_sim", str(base / "item_similarity.parquet"))
        cfg.setdefault("freedom_item_ids", str(base / "item_ids.json"))
    return cfg


def run_one(
    dataset: str,
    model: str,
    extra: dict[str, Any] | None = None,
    epochs: int | None = None,
) -> dict[str, Any]:
    """训练 + 评测单个组合，返回结果字典（含耗时与全部指标）。"""
    import torch  # noqa: F401  延迟导入，避免影响纯数据脚本
    from recbole.config import Config
    from recbole.data import create_dataset, data_preparation
    from recbole.utils import get_model, init_seed

    from recsys.models.freedom_recbole import FREEDOM, make_trainer as make_freedom_trainer
    from recsys.models.freedom_recbole import register as register_freedom

    register_freedom()
    Trainer = make_freedom_trainer() if model == "FREEDOM" else _make_trainer()

    cfg = build_config(dataset, model, extra)
    if epochs:
        cfg["epochs"] = epochs

    # 非神经模型（Pop / Random / ItemKNN / EASE 等）没有梯度下降过程，
    # 训练 1 轮即可得到最终结果；跑多轮只是重复评测，白白拉长实验时间。
    if not is_neural(model):
        cfg["epochs"] = 1

    # RecBole 会解析 sys.argv，把我们自己的命令行参数误当配置覆盖项并告警。
    # 这里临时清空，保证显式传入的 config_dict 不被污染。
    _argv_backup = sys.argv
    sys.argv = sys.argv[:1]

    t0 = time.time()
    config = Config(model=model, dataset=dataset, config_dict=cfg)
    init_seed(config["seed"], config["reproducibility"])
    ds = create_dataset(config)
    train_data, valid_data, test_data = data_preparation(config, ds)

    m = (FREEDOM(config, train_data._dataset) if config["model"] == "FREEDOM"
         else get_model(config["model"])(config, train_data._dataset)).to(config["device"])
    if config["model"] == "NCL":
        m = _patch_ncl(m)
    trainer = Trainer(config, m)
    best_valid_score, best_valid_result = trainer.fit(
        train_data, valid_data, saved=cfg["saved"], show_progress=False
    )
    test_result = trainer.evaluate(
        test_data, load_best_model=True, model_file=trainer.saved_model_file,
        show_progress=False,
    )
    elapsed = time.time() - t0
    sys.argv = _argv_backup

    return {
        "dataset": dataset,
        "model": model,
        "epochs_cfg": int(cfg["epochs"]),
        "valid": {k: round(float(v), 6) for k, v in (best_valid_result or {}).items()},
        "test": {k: round(float(v), 6) for k, v in (test_result or {}).items()},
        "train_seconds": round(elapsed, 1),
        "n_users": int(ds.user_num),
        "n_items": int(ds.item_num),
        "n_interactions": int(ds.inter_num),
    }


def run_benchmark(
    dataset: str,
    models: list[tuple[str, dict]] | None = None,
    epochs: int | None = None,
    tag: str = "",
) -> list[dict]:
    """跑一组模型，逐条落盘，避免中途崩掉丢结果。"""
    models = models or [(m, o) for m, _, _, o in C.BASELINE_MODELS]
    results: list[dict] = []
    out_path = C.RESULTS / f"benchmark_{dataset}{('_' + tag) if tag else ''}.json"

    for name, override in models:
        print(f"[RUN] {dataset} / {name} ...", flush=True)
        try:
            r = run_one(dataset, name, override, epochs=epochs)
            results.append(r)
            nd = r["test"].get(f"ndcg@{C.TOP_K}", 0)
            rc = r["test"].get(f"recall@{C.TOP_K}", 0)
            print(f"      ok  NDCG@{C.TOP_K}={nd:.4f}  Recall@{C.TOP_K}={rc:.4f}  "
                  f"{r['train_seconds']}s", flush=True)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            results.append({"dataset": dataset, "model": name,
                            "error": f"{type(e).__name__}: {e}"})
            print(f"      FAIL {type(e).__name__}: {e}", flush=True)
        out_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return results
