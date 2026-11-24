"""把物品标题翻译成中文，产出 site/data/titles_zh.json。

为什么只翻热门而不是全量
------------------------
全量 19,724 条标题约 40 万字符，MyMemory 匿名额度（5000 字符/天）撑不住，
要十几天才能跑完。而热门条目的记忆库覆盖最好——经典片名几乎都能命中
专业译名（The Shining -> 闪灵），冷门片反而容易被直译成四不像。
所以按 popularity 取 Top-N，优先保证实际会被浏览到的条目质量。

用法
----
    python scripts/13_translate_titles.py --dataset movielens --top 300
    python scripts/13_translate_titles.py --dataset goodbooks --top 150
    python scripts/13_translate_titles.py --all        # 两个域一起跑

已翻译的条目会跳过，可反复运行续跑。
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "site" / "data"
CACHE = ROOT / "data" / "processed" / "titles_zh.json"

API = "https://api.mymemory.translated.net/get?q={}&langpair=en|zh-CN"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 结尾的年份：(1995) / （1995 年） / (1995年)
_YEAR_TAIL = re.compile(r"[（(]\s*\d{4}\s*年?\s*[)）]\s*$")
# MyMemory 偶尔吐出 <g id="51"> 这类标记
_TAG = re.compile(r"</?g[^>]*>")


def _split_title(title: str) -> tuple[str, str]:
    """拆出「主标题」和「尾部括注」。

    Toy Story (1995)                        -> ("Toy Story", "(1995)")
    Hunger Games (The Hunger Games, #1)     -> ("Hunger Games", "(The Hunger Games, #1)")
    """
    m = re.search(r"\s*[（(][^（()）]*[)）]\s*$", title)
    if not m:
        return title.strip(), ""
    return title[: m.start()].strip(), m.group(0).strip()


def _clean(text: str) -> str:
    text = _TAG.sub("", text or "")
    text = text.replace("《", "").replace("》", "")
    text = _YEAR_TAIL.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,、-")
    return text


def translate(text: str, retries: int = 3) -> str | None:
    url = API.format(urllib.parse.quote(text))
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=15, context=_CTX) as r:
                d = json.loads(r.read().decode())
            if d.get("quotaFinished"):
                print("  ! 当日额度已用完", flush=True)
                return None
            out = d.get("responseData", {}).get("translatedText") or ""
            out = _clean(out)
            # 完全没翻动（还是英文）就当作失败，避免把英文写进译名表
            if not out or not re.search(r"[\u4e00-\u9fff]", out):
                return None
            return out
        except Exception as e:
            if i == retries - 1:
                print(f"  ! 失败 {text[:30]}: {type(e).__name__}", flush=True)
                return None
            time.sleep(1.5 * (i + 1))
    return None


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cache(data: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def run(dataset: str, top: int, delay: float) -> None:
    items = json.loads((SITE_DATA / f"items_{dataset}.json").read_text(encoding="utf-8"))
    ranked = sorted(items.values(), key=lambda x: -(x.get("popularity") or 0))[:top]

    cache = load_cache().get(dataset, {})
    todo = [it for it in ranked if str(it["id"]) not in cache]
    print(f"[{dataset}] 取 Top {top}，已译 {len(cache)}，待译 {len(todo)}", flush=True)

    done = 0
    for it in todo:
        main, tail = _split_title(it["title"])
        zh = translate(main)
        if not zh:
            continue
        cache[str(it["id"])] = zh
        done += 1
        print(f"  {it['id']:>6} {it['title'][:44]:<46} -> {zh}", flush=True)
        if done % 20 == 0:
            all_data = load_cache()
            all_data[dataset] = cache
            save_cache(all_data)
        time.sleep(delay)

    all_data = load_cache()
    all_data[dataset] = cache
    save_cache(all_data)
    print(f"[{dataset}] 完成：本次新增 {done}，累计 {len(cache)}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["movielens", "goodbooks"])
    ap.add_argument("--top", type=int, default=200)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        run("movielens", 300, args.delay)
        run("goodbooks", 150, args.delay)
    elif args.dataset:
        run(args.dataset, args.top, args.delay)
    else:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
