"""LLM 重排 / 推荐理由演示：本地 Qwen2.5-0.5B-Instruct（CPU）。

用途
----
1. 证明 LLM 重排模块不是"纸面设计"：加载真实权重，对候选做排序与理由生成；
2. 记录 CPU 推理延迟，为"在线用 MMR、离线用 LLM"的架构取舍提供依据；
3. 产出 `experiments/results/llm_demo.json` 与 `llm_demo.md`，直接用于报告。

用法:
    python scripts/07_llm_demo.py --dataset movielens
    python scripts/07_llm_demo.py --dataset goodbooks --users 30944 12874 --k 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from app import create_app
from app.extensions import db
from app.models import Item, Rating
from app.services import recommender as R
from recsys.llm_rerank import LLMReranker


def pick_users(dataset: str, n: int = 2) -> list[int]:
    rows = db.session.execute(
        db.select(Rating.user_id, db.func.count(Rating.id).label("c"))
        .where(Rating.dataset == dataset)
        .group_by(Rating.user_id)
        .order_by(db.desc("c"))
        .limit(n)
    ).all()
    return [int(r[0]) for r in rows]


def build_profile(user_id: int, dataset: str, topn: int = 30) -> str:
    rows = db.session.execute(
        db.select(Rating.item_id, Rating.rating)
        .where(Rating.user_id == user_id, Rating.dataset == dataset)
        .order_by(Rating.rating.desc())
        .limit(topn)
    ).all()
    if not rows:
        return "新用户，暂无历史行为"
    ids = [int(r[0]) for r in rows]
    items = db.session.scalars(
        db.select(Item).where(Item.dataset == dataset, Item.id.in_(ids))
    ).all()
    meta = {it.id: it for it in items}
    genres: Counter[str] = Counter()
    titles: list[str] = []
    for iid, rating in rows:
        it = meta.get(int(iid))
        if not it:
            continue
        if len(titles) < 5:
            titles.append(it.title)
        for g in str(it.genres or "").replace("|", " ").split():
            if g:
                genres[g] += 2 if float(rating) >= 4 else 1
    top_g = [g for g, _ in genres.most_common(6)]
    return (f"用户 {user_id} 最近高分内容：{'、'.join(titles)}；"
            f"偏好题材：{'、'.join(top_g) if top_g else '未知'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=C.PRIMARY_DATASET)
    ap.add_argument("--users", nargs="*", type=int, default=None)
    ap.add_argument("--k", type=int, default=3, help="每名用户生成几条理由")
    ap.add_argument("--rerank-topn", type=int, default=6)
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        users = args.users or pick_users(args.dataset, 2)
        print(f"[LLM] dataset={args.dataset} users={users}", flush=True)
        profiles = {u: build_profile(u, args.dataset) for u in users}
        recs = {u: R.recommend(u, args.dataset, "hybrid", 20) for u in users}

        llm = LLMReranker()
        if not llm.available:
            raise SystemExit(
                f"未找到本地模型：{llm.model_dir}\n"
                "请先下载 Qwen2.5-0.5B-Instruct（见报告 5.4 节）。"
            )
        t0 = time.time()
        if not llm._load():
            raise SystemExit("模型加载失败，请检查 transformers / safetensors 依赖")
        load_s = time.time() - t0
        print(f"[LLM] 模型加载完成 {load_s:.1f}s", flush=True)

        samples = []
        rerank_samples = []
        for uid in users:
            profile = profiles[uid]
            items = recs[uid]["items"]
            for it in items[: args.k]:
                t = time.time()
                reason = llm.explain(profile, it)
                latency = time.time() - t
                samples.append({
                    "user_id": uid,
                    "profile": profile,
                    "item_id": it["id"],
                    "title": it["title"],
                    "genres": it["genres"],
                    "llm_reason": reason,
                    "template_reason": llm._fallback(profile, it),
                    "latency_s": round(latency, 2),
                })
                print(f"  [{uid}] {it['title'][:40]} -> {reason} ({latency:.1f}s)",
                      flush=True)

            # 可选：让 LLM 对候选做排序，记录其输出与基线顺序的差异
            cands = items[: args.rerank_topn]
            if len(cands) > 2:
                t = time.time()
                ordered = llm.rerank(cands, profile, k=len(cands))
                rerank_latency = time.time() - t
                rerank_samples.append({
                    "user_id": uid,
                    "baseline_order": [x["id"] for x in cands],
                    "llm_order": [x["id"] for x in ordered],
                    "baseline_titles": [x["title"] for x in cands],
                    "llm_titles": [x["title"] for x in ordered],
                    "latency_s": round(rerank_latency, 2),
                })
                print(f"  [{uid}] LLM rerank {len(cands)} items in {rerank_latency:.1f}s",
                      flush=True)

        payload = {
            "model_id": C.LLM["model_id"],
            "model_dir": str(C.LLM["model_dir"]),
            "device": "cpu",
            "dataset": args.dataset,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "load_seconds": round(load_s, 2),
            "samples": samples,
            "rerank_samples": rerank_samples,
        }
        out_json = C.RESULTS / "llm_demo.json"
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")

        lines = [
            "# 本地大模型演示（Qwen2.5-0.5B-Instruct，CPU）",
            "",
            f"- 数据集：`{args.dataset}`",
            f"- 模型加载：{load_s:.1f}s",
            f"- 生成样本：{len(samples)} 条",
            "",
            "| 用户 | 推荐物品 | LLM 生成理由 | 模板理由 | 延迟(s) |",
            "|---|---|---|---|---|",
        ]
        for s in samples:
            lines.append(
                f"| {s['user_id']} | {s['title']} | {s['llm_reason']} | "
                f"{s['template_reason']} | {s['latency_s']} |"
            )
        lines += ["", "## LLM 重排输出", ""]
        for r in rerank_samples:
            lines.append(f"- 用户 {r['user_id']}（{r['latency_s']}s）：")
            lines.append(f"  - 基线：{' → '.join(r['baseline_titles'])}")
            lines.append(f"  - LLM：{' → '.join(r['llm_titles'])}")
        out_md = C.RESULTS / "llm_demo.md"
        out_md.write_text("\n".join(lines), encoding="utf-8")
        print(f"[LLM] 写出 {out_json.name} / {out_md.name}", flush=True)


if __name__ == "__main__":
    main()
