"""生成实验报告所需的全部图表（不依赖 seaborn，统一风格）。

运行:
    python scripts/05_make_figures.py

产出（figures/）:
    01_benchmark_ndcg.png      11 个模型 NDCG@10 对比
    02_dataset_stats.png       三个数据集的规模对比
    03_long_tail.png           三个数据集的物品长尾分布 + Gini
    04_training_curves.png     LightGCN / FREEDOM 训练损失与验证 NDCG
    05_freedom_fusion.png      FREEDOM 自适应融合权重
    06_mmr_diversity.png       MMR 重排前后的多样性
    07_time_quality.png        训练耗时与效果
    08_architecture.png        系统架构图
"""
from __future__ import annotations

import glob
import json
import math
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from recsys.llm_rerank import MMRReranker

# ------------------------------------------------------------------ 全局风格
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
if FONT_PATH.exists():
    font_manager.fontManager.addfont(str(FONT_PATH))

plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#ced4da",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": "#e9ecef",
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "xtick.color": "#495057",
    "ytick.color": "#495057",
    "text.color": "#212529",
    "axes.labelcolor": "#343a40",
    "font.size": 10,
})

BLUE = "#3b5bdb"
TEAL = "#0c8599"
ORANGE = "#e8590c"
PURPLE = "#7048e8"
GREEN = "#2b8a3e"
GRAY = "#868e96"
RED = "#c92a2a"
LIGHT = "#adb5bd"


def _save(fig, name: str) -> None:
    out = C.FIGURES / name
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[FIG] {out.name}  ({out.stat().st_size / 1024:.0f} KB)")


def _fmt_int(n: float) -> str:
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e4:
        return f"{n / 1e4:.1f}万"
    return f"{int(n):,}"


# ------------------------------------------------------------------ 1. 基准对比
def fig_benchmark() -> None:
    path = C.RESULTS / "benchmark_movielens.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in rows if isinstance(r.get("test"), dict)
            and r["test"].get("ndcg@10") is not None]
    rows.sort(key=lambda r: r["test"]["ndcg@10"])

    names = [r["model"] for r in rows]
    vals = [r["test"]["ndcg@10"] for r in rows]
    colors = []
    for n in names:
        if n == "FREEDOM":
            colors.append(ORANGE)
        elif n == "EASE":
            colors.append(GREEN)
        elif n in ("Random", "Pop"):
            colors.append(LIGHT)
        else:
            colors.append(BLUE)

    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    bars = ax.barh(names, vals, color=colors, height=0.62, edgecolor="white")
    for b, v in zip(bars, vals):
        ax.text(v + max(vals) * 0.012, b.get_y() + b.get_height() / 2,
                f"{v:.4f}", va="center", fontsize=9, color="#343a40")
    ax.set_xlim(0, max(vals) * 1.18)
    ax.set_xlabel("NDCG@10（越高越好）")
    ax.set_title("MovieLens 全排序评测结果", loc="left",
                 fontsize=15, fontweight="bold", pad=16)
    ax.text(0, 1.015, "8:1:1 时间序切分 · Top-10 全量排序 · seed=2026 · 11 个有效模型",
            transform=ax.transAxes, fontsize=9, color="#6c757d")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)
    _save(fig, "01_benchmark_ndcg.png")


# ------------------------------------------------------------------ 2. 数据集规模
def fig_dataset_stats() -> None:
    stats = {
        ds: json.loads((C.DATA_PROCESSED / ds / "stats.json").read_text(encoding="utf-8"))
        for ds in ("movielens", "goodbooks", "bookcrossing")
    }
    labels = {"movielens": "MovieLens", "goodbooks": "Goodbooks-10k",
              "bookcrossing": "Book-Crossing"}
    colors = {"movielens": BLUE, "goodbooks": TEAL, "bookcrossing": PURPLE}
    groups = ["用户数", "物品数", "交互数"]
    keys = ["n_users", "n_items", "n_interactions"]

    x = np.arange(len(groups))
    width = 0.26
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    for i, ds in enumerate(labels):
        vals = [stats[ds][k] for k in keys]
        pos = x + (i - 1) * width
        bars = ax.bar(pos, vals, width * 0.92, label=labels[ds],
                      color=colors[ds], edgecolor="white")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v * 1.18, _fmt_int(v),
                    ha="center", va="bottom", fontsize=8.2, color="#343a40",
                    rotation=0)
    ax.set_yscale("log")
    ax.set_ylim(80, 2.2e7)
    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_ylabel("数量（对数坐标）")
    ax.set_title("三个数据集的规模对比", loc="left",
                 fontsize=15, fontweight="bold", pad=14)
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=9)
    ax.grid(axis="x", visible=False)
    fig.text(0.01, -0.035,
             "注：Goodbooks-10k 为全量统计（5,976,479 条评分）；在线演示库只导入交互最活跃的 4,000 名用户。",
             fontsize=8, color="#6c757d")
    _save(fig, "02_dataset_stats.png")


# ------------------------------------------------------------------ 3. 长尾分布
def _gini(counts: np.ndarray) -> float:
    x = np.sort(np.asarray(counts, dtype=np.float64))
    n = len(x)
    if n == 0 or x.sum() <= 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * x) / (n * x.sum())) - (n + 1) / n)


def fig_long_tail() -> None:
    labels = {"movielens": ("MovieLens", BLUE),
              "goodbooks": ("Goodbooks-10k", TEAL),
              "bookcrossing": ("Book-Crossing", PURPLE)}
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    notes = []
    for ds, (label, color) in labels.items():
        r = pd.read_parquet(C.DATA_PROCESSED / ds / "ratings.parquet",
                            columns=["item_id"])
        counts = r.groupby("item_id").size().sort_values(ascending=False).to_numpy()
        rank = np.arange(1, len(counts) + 1)
        ax.plot(rank, counts, color=color, lw=1.7, label=f"{label}（Gini={_gini(counts):.3f}）")
        top1 = counts[: max(1, int(len(counts) * 0.01))].sum() / counts.sum()
        notes.append(f"{label}: 前 1% 物品贡献 {top1 * 100:.1f}% 交互")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("物品排名（按交互次数降序，对数坐标）")
    ax.set_ylabel("交互次数（对数坐标）")
    ax.set_title("三个数据集的物品交互长尾分布", loc="left",
                 fontsize=15, fontweight="bold", pad=14)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.text(0.015, 0.04, "\n".join(notes), transform=ax.transAxes,
            fontsize=8.2, color="#495057",
            bbox=dict(boxstyle="round,pad=0.45", fc="#f8f9fa", ec="#dee2e6"))
    _save(fig, "03_long_tail.png")


# ------------------------------------------------------------------ 4. 训练曲线
def _read_event_logs() -> list[dict]:
    logs = []
    pattern = str(C.ROOT / "log_tensorboard" / "*" / "events.out.tfevents.*")
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    for p in glob.glob(pattern):
        try:
            ea = EventAccumulator(p, size_guidance={"scalars": 0})
            ea.Reload()
            tags = ea.Tags().get("scalars", [])
            if "Loss/Train" not in tags:
                continue
            loss = [e.value for e in ea.Scalars("Loss/Train")]
            valid = [e.value for e in ea.Scalars("Vaild_score")] \
                if "Vaild_score" in tags else []
            logs.append({"path": p, "loss": loss, "valid": valid})
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 读取 {p} 失败: {exc}")
    return logs


def _event_for_checkpoint(model: str) -> dict | None:
    """用 checkpoint 的时间戳找到同一次训练的 TensorBoard 事件目录。

    RecBole 每次训练会新建 `model-<时间>` 目录；只用"文件最新/序列最长"
    去猜模型很容易串到别的实验（本项目调试期留下过多份日志）。
    checkpoint 文件名与日志目录共享同一个时间戳，这是最可靠的对应关系。
    """
    ckpts = glob.glob(str(C.RESULTS / "checkpoints" / f"{model}-*.pth"))
    if not ckpts:
        return None
    ckpt = max(ckpts, key=lambda p: Path(p).stat().st_mtime)
    stamp = Path(ckpt).stem[len(model) + 1:]
    log_dir = C.ROOT / "log_tensorboard" / f"model-{stamp}"
    best = None
    for p in glob.glob(str(log_dir / "events.out.tfevents.*")):
        try:
            from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

            ea = EventAccumulator(p, size_guidance={"scalars": 0})
            ea.Reload()
            tags = ea.Tags().get("scalars", [])
            if "Loss/Train" not in tags:
                continue
            loss = [e.value for e in ea.Scalars("Loss/Train")]
            if not loss or loss[0] < 0.1:      # 空跑/异常实验
                continue
            valid = [e.value for e in ea.Scalars("Vaild_score")] \
                if "Vaild_score" in tags else []
            cand = {"path": p, "loss": loss, "valid": valid}
            if best is None or len(cand["loss"]) > len(best["loss"]):
                best = cand
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] 读取 {p} 失败: {exc}")
    return best


def fig_training_curves() -> None:
    light = _event_for_checkpoint("LightGCN")
    free = _event_for_checkpoint("FREEDOM")
    if not light or not free:
        print("[WARN] TensorBoard 事件不足，跳过训练曲线")
        return

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.2))
    for log, name, color in ((light, "LightGCN", BLUE), (free, "FREEDOM", ORANGE)):
        epochs = np.arange(1, len(log["loss"]) + 1)
        axes[0].plot(epochs, log["loss"], color=color, lw=1.6,
                     marker="o", markersize=2.8, label=name)
        if log["valid"]:
            ep_v = np.arange(1, len(log["valid"]) + 1)
            axes[1].plot(ep_v, log["valid"], color=color, lw=1.6,
                         marker="o", markersize=2.8, label=name)
            best_i = int(np.argmax(log["valid"]))
            axes[1].scatter([best_i + 1], [log["valid"][best_i]], s=55,
                            color=color, edgecolor="white", zorder=5)
            axes[1].annotate(f"best {log['valid'][best_i]:.4f}",
                             (best_i + 1, log["valid"][best_i]),
                             xytext=(8, 8), textcoords="offset points",
                             fontsize=8, color=color)

    axes[0].set_yscale("log")
    axes[0].set_title("训练损失（BPR + 跨视图对齐）", loc="left", fontsize=12)
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss（对数坐标）")
    axes[0].legend(frameon=False)

    axes[1].set_title("验证集 NDCG@10", loc="left", fontsize=12)
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("NDCG@10")
    axes[1].legend(frameon=False)

    for ax in axes:
        ax.grid(axis="x", visible=False)
    fig.suptitle("LightGCN 与 FREEDOM 的训练过程", x=0.01, y=0.995,
                 ha="left", fontsize=15, fontweight="bold")
    fig.text(0.01, 0.925,
             f"早停轮数：LightGCN {len(light['loss'])} / FREEDOM {len(free['loss'])}，CPU 训练",
             fontsize=8.5, color="#6c757d")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    _save(fig, "04_training_curves.png")


# ------------------------------------------------------------------ 5. FREEDOM 融合
def fig_freedom_fusion() -> None:
    files = glob.glob(str(C.RESULTS / "checkpoints" / "FREEDOM-*.pth"))
    if not files:
        print("[WARN] 未找到 FREEDOM checkpoint，跳过融合权重图")
        return
    import torch

    ckpt = max(files, key=lambda p: Path(p).stat().st_mtime)
    sd = torch.load(ckpt, map_location="cpu", weights_only=False)["state_dict"]
    logits = sd["fuse_logits"].float()
    log_scale = sd["log_scale"].float()
    gate = torch.softmax(logits, dim=0).numpy()
    scale = torch.exp(log_scale).clamp(0.05, 50.0).numpy()
    eff = gate * scale
    share = eff / eff.sum()

    names = ["协同视图\n（用户-物品图传播）", "内容视图\n（物品内容图传播）"]
    colors = [BLUE, ORANGE]
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    bars = ax.bar(names, share * 100, color=colors, width=0.5, edgecolor="white")
    for b, s in zip(bars, share * 100):
        ax.text(b.get_x() + b.get_width() / 2, s + 1.2, f"{s:.1f}%",
                ha="center", fontsize=12, fontweight="bold", color="#343a40")
    ax.set_ylim(0, 100)
    ax.set_ylabel("对最终打分的有效贡献（%）")
    ax.set_title("FREEDOM 自适应融合权重", loc="left",
                 fontsize=15, fontweight="bold", pad=14)
    ax.grid(axis="x", visible=False)
    info = (f"门控 softmax(fuse_logits) = [{gate[0]:.3f}, {gate[1]:.3f}]\n"
            f"尺度 exp(log_scale) = [{scale[0]:.3f}, {scale[1]:.3f}]\n"
            f"有效贡献 = 门控 × 尺度，归一化后为 {share[0]*100:.1f}% / {share[1]*100:.1f}%")
    ax.text(0.5, -0.20, info, transform=ax.transAxes, ha="center", va="top",
            fontsize=8.6, color="#495057", linespacing=1.6)
    _save(fig, "05_freedom_fusion.png")


# ------------------------------------------------------------------ 6. MMR 多样性
def _intra_list_sim(items: list[dict], feat: np.ndarray,
                    pos: dict[int, int]) -> float:
    vecs = []
    for it in items:
        j = pos.get(int(it["id"]))
        if j is None:
            continue
        v = feat[j].astype(np.float64)
        n = np.linalg.norm(v)
        if n > 1e-9:
            vecs.append(v / n)
    if len(vecs) < 2:
        return 0.0
    M = np.vstack(vecs)
    sim = M @ M.T
    n = len(vecs)
    return float((sim.sum() - np.trace(sim)) / (n * (n - 1)))


def _genre_set(it: dict) -> set[str]:
    return {g for g in str(it.get("genres") or "").replace("|", " ").split() if g}


def _dominant_share(items: list[dict]) -> float:
    """Top-N 中包含"最大单一题材"的物品比例（越低越多样）。"""
    c: Counter[str] = Counter()
    for it in items:
        c.update(_genre_set(it))
    if not c or not items:
        return 0.0
    return c.most_common(1)[0][1] / len(items)


def _genre_coverage(items: list[dict]) -> float:
    s: set[str] = set()
    for it in items:
        s |= _genre_set(it)
    return float(len(s))


def _eval_mmr(dataset: str, n_users: int, lam: float = 0.6) -> dict:
    db_path = C.INSTANCE / "recsys.db"
    if not db_path.exists():
        raise FileNotFoundError(db_path)
    con = sqlite3.connect(str(db_path))
    meta = pd.read_sql_query(
        "select id, title, genres, avg_rating, n_ratings, popularity, image_url, "
        f"description, year from items where dataset='{dataset}'", con)
    recs = pd.read_sql_query(
        "select user_id, item_id, score, rank from recommendations "
        f"where dataset='{dataset}' and algo='hybrid' order by user_id, rank", con)
    con.close()
    recs = recs[recs["rank"] <= 60]
    if meta.empty or recs.empty:
        raise ValueError(f"{dataset} 缺少 MMR 所需数据")

    meta = meta.set_index("id")
    feat = np.load(C.DATA_PROCESSED / dataset / "item_features.npy").astype(np.float32)
    ids = json.loads((C.DATA_PROCESSED / dataset / "item_ids.json")
                     .read_text(encoding="utf-8"))
    pos = {int(i): k for k, i in enumerate(ids)}
    reranker = MMRReranker(dataset)

    users = sorted(recs["user_id"].unique())[:n_users]
    sim_b, sim_a, dom_b, dom_a, cov_b, cov_a = [], [], [], [], [], []
    rel_b, rel_a = [], []
    for uid in users:
        g = recs[recs["user_id"] == uid].sort_values("rank")
        pool = []
        for _, row in g.iterrows():
            iid = int(row["item_id"])
            if iid not in meta.index:
                continue
            m = meta.loc[iid]
            pool.append({
                "id": iid, "title": str(m["title"]), "genres": str(m["genres"] or ""),
                "avg_rating": float(m["avg_rating"] or 0),
                "n_ratings": int(m["n_ratings"] or 0),
                "score": float(row["score"]),
            })
        if len(pool) < 21:
            continue
        before = pool[:20]
        after = reranker.rerank(pool, k=20, lam=lam)
        sim_b.append(_intra_list_sim(before, feat, pos))
        sim_a.append(_intra_list_sim(after, feat, pos))
        dom_b.append(_dominant_share(before))
        dom_a.append(_dominant_share(after))
        cov_b.append(_genre_coverage(before))
        cov_a.append(_genre_coverage(after))

        scores = np.array([x["score"] for x in pool], dtype=np.float64)
        lo, hi = scores.min(), scores.max()
        rel = (scores - lo) / (hi - lo) if hi > lo else np.ones_like(scores)
        idx = {x["id"]: i for i, x in enumerate(pool)}
        rel_b.append(float(np.mean(rel[:20])))
        rel_a.append(float(np.mean([rel[idx[x["id"]]] for x in after])))

    out = {
        "dataset": dataset, "n_users": len(sim_b), "lambda": lam,
        "pool_size": 60, "k": 20,
        "intra_sim_before": float(np.mean(sim_b)),
        "intra_sim_after": float(np.mean(sim_a)),
        "dominant_share_before": float(np.mean(dom_b)),
        "dominant_share_after": float(np.mean(dom_a)),
        "genre_coverage_before": float(np.mean(cov_b)),
        "genre_coverage_after": float(np.mean(cov_a)),
        "relevance_before": float(np.mean(rel_b)),
        "relevance_after": float(np.mean(rel_a)),
    }
    out["relevance_retention"] = out["relevance_after"] / out["relevance_before"]
    print(f"[MMR] {dataset}: users={out['n_users']} "
          f"sim {out['intra_sim_before']:.4f}->{out['intra_sim_after']:.4f}; "
          f"dominant {out['dominant_share_before']:.3f}->{out['dominant_share_after']:.3f}; "
          f"coverage {out['genre_coverage_before']:.2f}->{out['genre_coverage_after']:.2f}; "
          f"rel_ret={out['relevance_retention']:.3f}")
    return out


def fig_mmr_diversity() -> None:
    try:
        movie = _eval_mmr("movielens", 120, 0.6)
        book = _eval_mmr("goodbooks", 60, 0.6)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] MMR 评估失败: {exc}")
        return
    (C.RESULTS / "mmr_eval.json").write_text(
        json.dumps({"movielens": movie, "goodbooks": book},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    labels = ["重排前", "MMR 后"]
    panels = [
        ("列表内平均相似度（越低越多样）",
         [movie["intra_sim_before"], movie["intra_sim_after"]],
         [LIGHT, BLUE], "下降", True),
        ("最大单一题材占比（越低越多样）",
         [movie["dominant_share_before"] * 100, movie["dominant_share_after"] * 100],
         [LIGHT, TEAL], "下降", True),
        ("Top-20 覆盖题材数（越高越多样）",
         [movie["genre_coverage_before"], movie["genre_coverage_after"]],
         [LIGHT, ORANGE], "提升", False),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 4.3))
    for ax, (title, vals, colors, direction, lower_better) in zip(axes, panels):
        ax.bar(labels, vals, color=colors, width=0.5)
        top = max(vals)
        for i, v in enumerate(vals):
            fmt = f"{v:.3f}" if v < 10 else f"{v:.1f}"
            ax.text(i, v + top * 0.04, fmt, ha="center", fontsize=11,
                    fontweight="bold")
        ax.set_title(title, fontsize=10.5)
        ax.set_ylim(0, top * 1.28)
        ax.grid(axis="x", visible=False)
        change = (vals[0] - vals[1]) / vals[0] * 100 if lower_better \
            else (vals[1] - vals[0]) / vals[0] * 100
        ax.text(0.5, 0.88, f"{direction} {change:.1f}%",
                transform=ax.transAxes, ha="center", fontsize=10,
                color=GREEN if lower_better else ORANGE, fontweight="bold")

    fig.suptitle("MMR 重排前后的推荐多样性（MovieLens，60 选 20，λ=0.6）",
                 x=0.01, y=0.995, ha="left", fontsize=14, fontweight="bold")
    fig.text(
        0.01, 0.93,
        f"统计样本：{movie['n_users']} 名用户；归一化相关性保留 "
        f"{movie['relevance_retention'] * 100:.1f}%\n"
        f"Goodbooks 同口径：相似度 {book['intra_sim_before']:.3f}→{book['intra_sim_after']:.3f}，"
        f"覆盖题材 {book['genre_coverage_before']:.1f}→{book['genre_coverage_after']:.1f}",
        fontsize=8.2, color="#6c757d", va="top", linespacing=1.6)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    _save(fig, "06_mmr_diversity.png")


# ------------------------------------------------------------------ 7. 时间 vs 效果
def fig_time_quality() -> None:
    rows = json.loads((C.RESULTS / "benchmark_movielens.json").read_text(encoding="utf-8"))
    rows = [r for r in rows if isinstance(r.get("test"), dict)
            and r["test"].get("ndcg@10") is not None and r.get("train_seconds")]
    fig, ax = plt.subplots(figsize=(8.8, 5.2))
    for r in rows:
        x = float(r["train_seconds"])
        y = float(r["test"]["ndcg@10"])
        color = ORANGE if r["model"] == "FREEDOM" else BLUE
        ax.scatter(x, y, s=70 if r["model"] == "FREEDOM" else 42,
                   color=color, edgecolor="white", zorder=3)
        offsets = {
            "FREEDOM": (1.08, -0.0020),
            "LightGCN": (0.90, 0.0014),
            "ItemKNN": (1.08, 0.0012),
            "NeuMF": (1.08, 0.0012),
            "DGCF": (1.08, 0.0012),
        }
        dx, dy = offsets.get(r["model"], (1.06, 0.0012))
        ax.annotate(r["model"], (x, y), xytext=(x * dx, y + dy),
                    fontsize=8.2, color="#343a40")
    ax.set_xscale("log")
    ax.set_xlabel("训练耗时（秒，对数坐标）")
    ax.set_ylabel("NDCG@10")
    ax.set_title("训练耗时与推荐效果", loc="left",
                 fontsize=15, fontweight="bold", pad=14)
    ax.axvline(300, color=GREEN, ls="--", lw=1.0, alpha=0.8)
    ax.text(310, ax.get_ylim()[0] + 0.002, "5 分钟预算线", color=GREEN, fontsize=8.5)
    ax.grid(axis="x", visible=False)
    _save(fig, "07_time_quality.png")


# ------------------------------------------------------------------ 8. 架构图
def _box(ax, x, y, w, h, title, body="", color=BLUE, fill="#f8f9ff", fs=9.0):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.10",
                       linewidth=1.2, edgecolor=color, facecolor=fill, zorder=2)
    ax.add_patch(p)
    if body:
        ax.text(x + w / 2, y + h - 0.20, title, ha="center", va="top",
                fontsize=fs + 0.8, fontweight="bold", color=color, zorder=3)
        ax.text(x + w / 2, y + h - 0.52, body, ha="center", va="top",
                fontsize=fs - 0.5, color="#343a40", linespacing=1.45, zorder=3)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=fs, color="#343a40", linespacing=1.4, zorder=3)


def _arrow(ax, p1, p2, color=GRAY, style="-|>", ls="-", lw=1.3, label=None):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=12,
                        linewidth=lw, color=color, linestyle=ls,
                        shrinkA=3, shrinkB=3, zorder=4)
    ax.add_patch(a)
    if label:
        ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + 0.08, label,
                ha="center", va="bottom", fontsize=7.8, color="#495057")


def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(13.2, 8.4))
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 9.5)
    ax.axis("off")

    # 背景分区
    for (y, h, label, color) in (
        (5.0, 4.0, "① 离线训练与预计算（Python / RecBole / PyTorch CPU）", "#e7f5ff"),
        (0.25, 4.45, "② 在线服务与部署（Flask + Waitress + Cloudflare）", "#fff4e6"),
    ):
        band = FancyBboxPatch((0.2, y), 12.8, h,
                              boxstyle="round,pad=0.02,rounding_size=0.12",
                              linewidth=1.0, edgecolor="#dee2e6",
                              facecolor=color, alpha=0.55, zorder=0)
        ax.add_patch(band)
        ax.text(0.38, y + h - 0.22, label, ha="left", va="top",
                fontsize=10.5, fontweight="bold", color="#495057")

    # ---- 离线四个阶段
    _box(ax, 0.42, 5.95, 2.95, 2.35, "数据与特征",
         "MovieLens / Goodbooks-10k\nBook-Crossing\nTF-IDF 文本语义\n类别 multi-hot\n结构化数值 + 相似图", BLUE)
    _box(ax, 3.62, 5.95, 3.15, 2.35, "模型训练",
         "FREEDOM 多视图融合（本文）\nLightGCN / SGL / NCL / DGCF\nBPR / NeuMF / ItemKNN / EASE\n热度 / 随机基线\n统一 RecBole 管线", TEAL)
    _box(ax, 7.02, 5.95, 2.55, 2.35, "统一评测",
         "8:1:1 时间序切分\nTop-10 全量排序\nRecall / NDCG\nMRR / MAP / Hit\n早停 + 固定随机种子", PURPLE)
    _box(ax, 9.82, 5.95, 2.95, 2.35, "预计算 Top-N",
         "每个用户 × 每种算法\nTop-20 候选 + 分数\n推荐理由模板\n内容画像 / 热度兜底\n离线批量落库", ORANGE)

    for x1, x2 in ((3.37, 3.62), (6.77, 7.02), (9.57, 9.82)):
        _arrow(ax, (x1, 7.12), (x2, 7.12), color="#868e96")

    # ---- 存储（横跨离线/在线）
    _box(ax, 9.82, 3.55, 2.95, 1.02, "",
         "", ORANGE, fill="#fff9db")
    ax.text(11.30, 4.32, "SQLite / MySQL", ha="center", va="top",
            fontsize=9.8, fontweight="bold", color="#b35c00", zorder=3)
    ax.text(11.30, 4.02, "物品表 · 评分表 · 相似度表 · 推荐结果表",
            ha="center", va="top", fontsize=7.8, color="#495057", zorder=3)
    _arrow(ax, (11.30, 5.95), (11.30, 4.57), color=ORANGE, ls="--", lw=1.5,
           label="Top-N 落库")

    # ---- 在线主链路
    _box(ax, 0.42, 2.05, 2.15, 1.45, "浏览器",
         "原生 HTML / CSS / JS\n零 CDN 依赖\nCloudflare Pages\n静态镜像", BLUE)
    _box(ax, 2.92, 2.05, 2.55, 1.45, "Flask REST API",
         "Waitress WSGI\n/api/recommend\n/api/items\n/api/overview", TEAL)
    _box(ax, 5.85, 1.90, 3.35, 1.75, "在线推荐服务",
         "① 查预计算表（毫秒级）\n② 内容画像补足 / 热度兜底\n③ MMR 多样性重排\n④ 模板或大模型生成理由", PURPLE, fs=8.8)

    _arrow(ax, (2.57, 2.78), (2.92, 2.78), color="#868e96")
    _arrow(ax, (5.47, 2.78), (5.85, 2.78), color="#868e96")
    _arrow(ax, (9.20, 2.78), (9.82, 2.78), color="#868e96", style="<|-|>",
           label="查表 / 回填")
    _arrow(ax, (11.30, 3.55), (9.20, 2.40), color=ORANGE, ls="--", lw=1.3)

    # ---- 部署链路
    _box(ax, 0.42, 0.55, 2.6, 0.95, "GitHub 仓库",
         "源码 / 文档 / 静态镜像", GRAY, fill="#f8f9fa", fs=8.6)
    _box(ax, 3.30, 0.55, 2.9, 0.95, "GitHub Actions",
         "自动构建 + 校验", GRAY, fill="#f8f9fa", fs=8.6)
    _box(ax, 6.48, 0.55, 2.55, 0.95, "Cloudflare Pages",
         "前端静态站点", ORANGE, fill="#fff4e6", fs=8.6)
    _box(ax, 9.30, 0.55, 3.45, 0.95, "Cloudflare Tunnel",
         "内网 Flask / Waitress → 公网 HTTPS", ORANGE, fill="#fff4e6", fs=8.6)
    for x1, x2 in ((3.02, 3.30), (6.20, 6.48), (9.03, 9.30)):
        _arrow(ax, (x1, 1.02), (x2, 1.02), color="#868e96")

    ax.text(6.7, 9.46, "双域智能推荐系统总体架构", ha="center", va="top",
            fontsize=16, fontweight="bold", color="#212529")
    _save(fig, "08_architecture.png")


# ------------------------------------------------------------------ main
def main() -> None:
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    fig_benchmark()
    fig_dataset_stats()
    fig_long_tail()
    fig_training_curves()
    fig_freedom_fusion()
    fig_mmr_diversity()
    fig_time_quality()
    fig_architecture()
    print("[FIG] 全部完成")


if __name__ == "__main__":
    main()
