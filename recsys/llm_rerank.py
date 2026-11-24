"""重排层：多样性约束（MMR）+ 大模型推荐理由生成。

为什么重排要单独一层
--------------------
离线模型只优化"相关性"，直接输出 Top-N 往往同质化严重（同一题材刷屏）。
工业系统在召回/排序之后还有一层重排，用 MMR（最大边际相关性）在相关性与
多样性之间取平衡。这里实现两件事：

1. ``mmr_rerank``——纯算法、无外部依赖，线上每次请求都能跑（毫秒级）；
2. ``LLMReranker``——若本地存在 Qwen2.5-0.5B-Instruct，则用大模型对候选
   做语义重排并生成个性化理由；模型缺失时自动退化为模板理由，保证服务可用。

设计取舍：LLM 推理在 CPU 上单次约数秒，不适合放进在线请求链路，
因此生产用法是"离线生成 + 落库"，在线只读结果；本模块两种路径都支持。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import config as C


# ------------------------------------------------------------------ MMR
class MMRReranker:
    """最大边际相关性重排（Maximal Marginal Relevance）。

    score(i) = λ · rel(i) − (1−λ) · max_{j∈已选} sim(i, j)

    sim 由"物品内容特征余弦"与"题材 Jaccard"各占一半组成；
    特征文件缺失时退化为纯题材 Jaccard。
    """

    def __init__(self, dataset: str):
        self.dataset = dataset
        self._feat: np.ndarray | None = None
        self._pos: dict[int, int] = {}
        self._load()

    def _load(self) -> None:
        fp = C.DATA_PROCESSED / self.dataset / "item_features.npy"
        ip = C.DATA_PROCESSED / self.dataset / "item_ids.json"
        if fp.exists() and ip.exists():
            try:
                self._feat = np.load(fp).astype(np.float32)
                ids = json.loads(ip.read_text(encoding="utf-8"))
                self._pos = {int(i): k for k, i in enumerate(ids)}
            except Exception:  # noqa: BLE001
                self._feat = None

    def _sim(self, a: dict, b: dict) -> float:
        """内容相似度 = 0.5 × 稠密特征余弦 + 0.5 × 题材 Jaccard。

        只用稠密特征时，TF-IDF 与 multi-hot 维度让任意两物品的余弦普遍
        在 0.8 以上，MMR 的多样性惩罚几乎没有区分度；题材 Jaccard 对
        "是否同一类型"更敏感，两者各占一半可以在语义细粒度与类别多样性
        之间取得平衡。
        """
        cos = None
        if self._feat is not None:
            ia, ib = self._pos.get(a["id"]), self._pos.get(b["id"])
            if ia is not None and ib is not None:
                va, vb = self._feat[ia], self._feat[ib]
                na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
                if na > 0 and nb > 0:
                    cos = float(va @ vb / (na * nb))
        ga = set(str(a.get("genres") or "").replace("|", " ").split())
        gb = set(str(b.get("genres") or "").replace("|", " ").split())
        jac = (len(ga & gb) / len(ga | gb)) if ga and gb else 0.0
        if cos is None:
            return jac
        return 0.5 * cos + 0.5 * jac

    def rerank(self, items: list[dict], k: int | None = None,
               lam: float = 0.75) -> list[dict]:
        if not items:
            return []
        k = k or len(items)
        scores = np.array([float(x.get("score") or 0.0) for x in items], dtype=np.float64)
        # 分数可能为负/量纲不一，先 min-max 归一到 [0,1] 再与相似度加权
        lo, hi = float(np.min(scores)), float(np.max(scores))
        rel = (scores - lo) / (hi - lo) if hi - lo > 1e-12 else np.ones_like(scores)

        order = [int(np.argmax(rel))]
        remaining = set(range(len(items))) - set(order)
        while remaining and len(order) < k:
            best_j, best_v = None, -1e9
            for j in remaining:
                div = max(self._sim(items[j], items[i]) for i in order)
                v = lam * rel[j] - (1 - lam) * div
                if v > best_v:
                    best_j, best_v = j, v
            order.append(best_j)
            remaining.discard(best_j)
        return [items[i] for i in order]


# ------------------------------------------------------------------ LLM
class LLMReranker:
    """本地小参数大模型：语义重排 + 推荐理由生成。

    模型不存在时 ``available=False``，所有方法走模板兜底，不会抛异常。
    """

    def __init__(self, model_dir: str | None = None):
        self.model_dir = Path(model_dir or C.LLM["model_dir"])
        self._model = None
        self._tok = None
        self._tried = False

    @property
    def available(self) -> bool:
        return (self.model_dir / "config.json").exists()

    def _load(self) -> bool:
        if self._tried:
            return self._model is not None
        self._tried = True
        if not self.available:
            return False
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self._tok = AutoTokenizer.from_pretrained(str(self.model_dir))
            self._model = AutoModelForCausalLM.from_pretrained(
                str(self.model_dir), torch_dtype=torch.float32
            )
            self._model.eval()
            return True
        except Exception:  # noqa: BLE001 - 缺依赖/权重损坏都退化为模板
            self._model = None
            return False

    # -------------------------------------------------- 生成
    def generate(self, system: str, user: str, max_new_tokens: int | None = None) -> str:
        if not self._load():
            return ""
        import torch

        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
        text = self._tok.apply_chat_template(msgs, tokenize=False,
                                             add_generation_prompt=True)
        inputs = self._tok(text, return_tensors="pt")
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens or C.LLM["max_new_tokens"],
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self._tok.eos_token_id,
            )
        gen = out[0][inputs["input_ids"].shape[1]:]
        return self._tok.decode(gen, skip_special_tokens=True).strip()

    # -------------------------------------------------- 业务接口
    def explain(self, user_profile: str, item: dict) -> str:
        """为单个推荐结果生成理由；模型不可用时用模板。"""
        if self._load():
            prompt = (
                f"用户画像：{user_profile}\n"
                f"推荐物品：{item.get('title')}，题材：{item.get('genres')}，"
                f"平均评分 {item.get('avg_rating')}（{item.get('n_ratings')} 人评分）\n"
                "请用一句不超过 40 字的中文说明为什么推荐给该用户，不要加引号。"
            )
            out = self.generate("你是推荐系统的解释生成模块，只输出一句中文推荐理由。", prompt)
            if out:
                return out.replace("\n", " ")[:120]
        return self._fallback(user_profile, item)

    def _fallback(self, user_profile: str, item: dict) -> str:
        genres = [g for g in str(item.get("genres") or "").split("|") if g]
        pref = [p for p in user_profile.replace("、", " ").split() if p]
        hit = [g for g in genres if g in pref]
        base = "综合协同信号与内容匹配度排序靠前"
        if hit:
            base = f"与你偏好的「{'、'.join(hit[:2])}」题材一致"
        if item.get("n_ratings"):
            base += f"，且评分 {float(item.get('avg_rating') or 0):.1f}"
        return base

    def rerank(self, candidates: list[dict], user_profile: str,
               k: int | None = None) -> list[dict]:
        """让模型给出候选的偏好排序（输出 id 列表），失败则保持原序。"""
        if not self._load() or len(candidates) <= 2:
            return candidates[:k] if k else candidates
        listing = "\n".join(
            f"{i+1}. {c.get('title')}（{c.get('genres')}，评分 {c.get('avg_rating')}）"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"用户偏好：{user_profile}\n候选列表：\n{listing}\n"
            f"请从最可能喜欢到最不可能排序，只输出编号，用逗号分隔，例如：3,1,2。"
        )
        out = self.generate("你是推荐排序器，只输出编号序列。", prompt, max_new_tokens=64)
        order: list[int] = []
        for tok in out.replace("，", ",").split(","):
            tok = tok.strip()
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(candidates) and idx not in order:
                    order.append(idx)
        if len(order) < len(candidates):
            order += [i for i in range(len(candidates)) if i not in order]
        res = [candidates[i] for i in order]
        return res[:k] if k else res


# ------------------------------------------------------------------ 便捷函数
_MMR_CACHE: dict[str, MMRReranker] = {}


def rerank(items: list[dict], dataset: str, k: int | None = None,
           lam: float = 0.75) -> list[dict]:
    """线上重排入口：MMR 多样性重排，结果缓存 reranker 避免重复加载特征。"""
    r = _MMR_CACHE.get(dataset)
    if r is None:
        r = MMRReranker(dataset)
        _MMR_CACHE[dataset] = r
    return r.rerank(items, k=k, lam=lam)


def llm_enabled() -> bool:
    return LLMReranker().available


if __name__ == "__main__":
    # 自检：用两条假数据跑通 MMR，确保无特征文件时也能退化工作
    demo = [
        {"id": 1, "title": "A", "genres": "Action|Sci-Fi", "score": 0.9},
        {"id": 2, "title": "B", "genres": "Action|Sci-Fi", "score": 0.8},
        {"id": 3, "title": "C", "genres": "Romance", "score": 0.7},
    ]
    print([x["title"] for x in MMRReranker("movielens").rerank(demo, lam=0.5)])
    print("llm available:", llm_enabled())
