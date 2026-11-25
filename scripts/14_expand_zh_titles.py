"""批量扩充电影 / 图书的中文译名（可续跑）。

现有 13_translate_titles.py 逐条翻译，受 MyMemory 匿名额度限制只覆盖了热门
Top-150 / Top-90。本脚本改用 `|` 分隔的批量请求，把热门条目扩到 Top-N，
并保留「已翻译就跳过」的续跑能力。

用法
----
    python scripts/14_expand_zh_titles.py --top 800          # 两个域一起扩
    python scripts/14_expand_zh_titles.py --dataset movielens --top 1000
    python scripts/14_expand_zh_titles.py --all --top 800

配额用完时脚本会自动停止并保存进度，第二天再跑即可继续。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "processed" / "titles_zh.json"
SITE_ZH = ROOT / "site" / "data" / "titles_zh.json"

API = "https://api.mymemory.translated.net/get"
EMAIL = "recsys.course2026@gmail.com"
MAX_CHARS = 1100          # 实测 >1500 字符会被截断，留足余量避免逐条重试
BATCH_SIZE = 40

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_YEAR_TAIL = re.compile(r"[（(]\s*\d{4}\s*年?\s*[)）]\s*$")
_TAG = re.compile(r"</?g[^>]*>")
_CJK = re.compile(r"[\u4e00-\u9fff]")

# 翻译记忆里个别同名 / 误匹配条目，手工校正（dataset, item_id）
OVERRIDES = {
    ("movielens", 64614): "老爷车",          # Gran Torino
    ("movielens", 431): "情枷爱锁",           # Carlito's Way
    ("movielens", 3897): "几近成名",          # Almost Famous
    ("movielens", 2791): "空前绝后满天飞",     # Airplane!
    ("movielens", 1673): "不羁夜",            # Boogie Nights
    ("movielens", 337): "不一样的天使",       # What's Eating Gilbert Grape
    ("movielens", 2871): "激流四勇士",        # Deliverance
    ("movielens", 3108): "渔王",              # The Fisher King
    ("movielens", 3507): "古怪夫妻",          # The Odd Couple
    ("movielens", 3681): "黄昏双镖客",        # For a Few Dollars More
    ("movielens", 1396): "神偷大盗",          # Sneakers
}


def clean(text: str) -> str:
    text = html.unescape(text or "")
    text = _TAG.sub("", text)
    text = text.replace("《", "").replace("》", "")
    text = text.replace("“", "").replace("”", "")
    text = _YEAR_TAIL.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,、-—:")
    return text


def is_zh(text: str) -> bool:
    return bool(text) and bool(_CJK.search(text))


def translate_batch(segments: list[str], delay: float) -> list[str | None]:
    """一次请求翻译多个片段，返回与输入等长的结果（失败项为 None）。"""
    joined = "|".join(segments)
    url = (
        f"{API}?q={urllib.parse.quote(joined)}"
        f"&langpair=en|zh-CN&de={EMAIL}"
    )
    try:
        with urllib.request.urlopen(url, timeout=90, context=_CTX) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! 请求失败：{type(exc).__name__}，改用逐条重试", flush=True)
        return [_translate_one(s, delay) for s in segments]

    if data.get("quotaFinished"):
        print("  ! 今日配额已用完", flush=True)
        return [None] * len(segments)
    if str(data.get("responseStatus")) != "200":
        print(f"  ! 响应异常：{data.get('responseDetails')}", flush=True)
        return [_translate_one(s, delay) for s in segments]

    out = clean(data.get("responseData", {}).get("translatedText", ""))
    parts = out.split("|")
    if len(parts) != len(segments):
        # MyMemory 偶尔截断长批次，退回逐条保证一一对应
        print(f"  ! 批量返回 {len(parts)}/{len(segments)} 段，逐条重试", flush=True)
        return [_translate_one(s, delay) for s in segments]

    results: list[str | None] = []
    for part in parts:
        zh = clean(part)
        results.append(zh if is_zh(zh) else None)
    return results


def _translate_one(text: str, delay: float) -> str | None:
    url = (
        f"{API}?q={urllib.parse.quote(text)}"
        f"&langpair=en|zh-CN&de={EMAIL}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30, context=_CTX) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("quotaFinished"):
            return None
        zh = clean(data.get("responseData", {}).get("translatedText", ""))
        return zh if is_zh(zh) else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        time.sleep(delay)


def load_all() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_all(data: dict) -> None:
    for (ds, iid), zh in OVERRIDES.items():
        data.setdefault(ds, {})[str(iid)] = zh
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    SITE_ZH.parent.mkdir(parents=True, exist_ok=True)
    SITE_ZH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def chunks(items: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    cur: list[dict] = []
    size = 0
    for it in items:
        n = len(it["title"]) + 1
        if cur and (len(cur) >= BATCH_SIZE or size + n > MAX_CHARS):
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        out.append(cur)
    return out


def run(dataset: str, top: int, delay: float) -> None:
    items_path = ROOT / "site" / "data" / f"items_{dataset}.json"
    items = json.loads(items_path.read_text(encoding="utf-8"))
    ranked = sorted(items.values(), key=lambda x: -(x.get("popularity") or 0))[:top]

    all_data = load_all()
    table = all_data.get(dataset, {})
    todo = [it for it in ranked if str(it["id"]) not in table]
    print(f"[{dataset}] 目标 Top {top}，已译 {len(table)}，待译 {len(todo)}", flush=True)

    done = 0
    for chunk in chunks(todo):
        segs = [it["title"] for it in chunk]
        results = translate_batch(segs, delay)
        if results and results[0] is None and all(r is None for r in results):
            print("  配额耗尽，停止本域翻译", flush=True)
            break
        for it, zh in zip(chunk, results):
            if zh:
                table[str(it["id"])] = zh
                done += 1
                print(f"  {it['id']:>6} {it['title'][:40]:<42} -> {zh}", flush=True)
        all_data[dataset] = table
        save_all(all_data)
        time.sleep(delay)

    save_all(all_data)
    print(f"[{dataset}] 完成：新增 {done}，累计 {len(table)}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["movielens", "goodbooks", "bookcrossing"])
    ap.add_argument("--top", type=int, default=800)
    ap.add_argument("--delay", type=float, default=0.25)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fix-only", action="store_true",
                    help="只把手工校正写回译名表，不请求翻译接口")
    args = ap.parse_args()

    if args.fix_only:
        save_all(load_all())
        print("已应用手工校正")
        return 0

    datasets = (["movielens", "goodbooks"] if args.all
                else [args.dataset] if args.dataset else [])
    if not datasets:
        ap.print_help()
        return 1
    for ds in datasets:
        run(ds, args.top, args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
