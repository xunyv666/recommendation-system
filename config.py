"""全局配置：路径、数据集、数据库、算法超参。

所有脚本只从这里取路径，避免散落的硬编码。
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parent

DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
EXPERIMENTS = ROOT / "experiments"
RESULTS = EXPERIMENTS / "results"
CONFIGS = EXPERIMENTS / "configs"
FIGURES = ROOT / "figures"
SCREENSHOTS = ROOT / "screenshots"
REPORT = ROOT / "report"
INSTANCE = ROOT / "instance"

for _p in (DATA_PROCESSED, RESULTS, CONFIGS, FIGURES, SCREENSHOTS, REPORT, INSTANCE):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 数据集
# 每个数据集：原始文件位置、领域、是否有时间戳
DATASETS = {
    "movielens": {
        "domain": "movie",
        "label": "电影",
        "raw": DATA_RAW / "movielens",
        "ratings": "ratings.csv",
        "items": "movies.csv",
        "tags": "tags.csv",
        "links": "links.csv",
        "timestamp": True,
    },
    "goodbooks": {
        "domain": "book",
        "label": "图书",
        "raw": DATA_RAW / "goodbooks",
        "ratings": "ratings.csv",
        "items": "books.csv",
        "book_tags": "book_tags.csv",
        "tag_names": "tags.csv",
        "timestamp": False,
    },
    "bookcrossing": {
        "domain": "book",
        "label": "图书(大规模)",
        "raw": DATA_RAW / "book-crossing",
        "ratings": "BX-Book-Ratings.csv",
        "items": "BX-Books.csv",
        "timestamp": False,
    },
}

# 主实验数据集 / 副对照数据集
PRIMARY_DATASET = "movielens"
BOOK_DATASET = "goodbooks"
SCALE_DATASET = "bookcrossing"

# ---------------------------------------------------------------- 数据库
# 开发用 SQLite，生产用 MySQL；仅改环境变量 DATABASE_URL 即可
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{(INSTANCE / 'recsys.db').as_posix()}",
)

# ---------------------------------------------------------------- 评测
TOP_K = 10
METRICS = ["Recall", "Precision", "NDCG", "MRR", "Hit", "MAP"]
EVAL_CONFIG = {
    "split": {"RS": [0.8, 0.1, 0.1]},   # 按时间 8:1:1
    "group_by": "user",
    "order": "TO",
    "mode": "full",                      # 全排序评测
}
SEED = 2026

# ---------------------------------------------------------------- 模型基线表
# (模型名, 中文说明, 是否神经模型, 额外超参)
#
# 说明：SASRec / BERT4Rec 属于"序列推荐"，输入是 item_id_list（会话序列），
# 与本文用户-物品全排序任务的数据格式不同，强行跑会改变任务定义、指标不可比。
# 因此不放入主表，改在报告"局限与展望"中说明。
BASELINE_MODELS = [
    ("Random",      "随机推荐（下界）",       False, {}),
    ("Pop",         "全局热门",             False, {}),
    ("ItemKNN",     "物品协同过滤",          False, {"k": 20}),
    ("BPR",         "贝叶斯个性化排序",       True,  {}),
    ("NeuMF",       "神经协同过滤",          True,  {"embedding_size": 64}),
    ("LightGCN",    "轻量图卷积",            True,  {"embedding_size": 64, "n_layers": 3}),
    ("SGL",         "自监督图对比学习",       True,  {"embedding_size": 64, "n_layers": 3}),
    ("NCL",         "邻域对比学习",          True,  {"embedding_size": 64, "n_layers": 3}),
    ("DGCF",        "解耦图协同过滤",        True,  {"embedding_size": 64, "n_layers": 3}),
    ("FREEDOM",     "多视图图融合（本文）",    True,  {"embedding_size": 64, "n_layers": 3,
                                                    "align_weight": 0.15}),
    ("EASE",        "线性自编码器",          False, {"reg_weight": 250.0}),
]

# ---------------------------------------------------------------- 训练默认
TRAIN_DEFAULTS = {
    "epochs": 50,
    "train_batch_size": 2048,
    "eval_batch_size": 4096,
    "learning_rate": 0.001,
    "train_neg_sample_args": {"distribution": "uniform", "sample_num": 1},
    "device": "cpu",
    "seed": SEED,
    "show_progress": False,
    "saved": True,
}

# ---------------------------------------------------------------- LLM 重排
LLM = {
    # 本地模型（ModelScope 下载）；为空则退化为规则式理由生成
    "model_id": os.environ.get("LLM_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct"),
    "model_dir": str(ROOT / "models" / "qwen2.5-0.5b-instruct"),
    "max_new_tokens": 128,
    "temperature": 0.7,
    "top_n": 20,        # 对前 20 个候选做重排
}
