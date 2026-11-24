"""用 Playwright + 本机 Edge 生成系统运行效果截图。

前置条件
--------
1. Flask 服务已在 http://127.0.0.1:8080 启动；
2. 已安装 playwright（`pip install playwright`），无需额外下载 Chromium，
   直接复用 Windows 自带 Edge。

运行:
    python scripts/09_screenshots.py
    python scripts/09_screenshots.py --base http://127.0.0.1:8080
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C

SHOTS = [
    {
        "name": "01_home_movie.png",
        "path": "/",
        "wait": "#itemGrid .card",
        "desc": "电影域首页：数据规模、热门内容与六种题材筛选",
    },
    {
        "name": "02_recommend_movie.png",
        "path": "/recommend?dataset=movielens&uid=1&algo=hybrid&k=20",
        "wait": "#recGrid .card",
        "desc": "电影域个性化推荐：融合推荐 + MMR 重排 + 推荐理由",
    },
    {
        "name": "03_dashboard_movie.png",
        "path": "/dashboard?dataset=movielens",
        "wait": "#metricTable tbody tr",
        "desc": "算法看板：11 个模型的 Recall/NDCG/MRR 与训练耗时",
    },
    {
        "name": "04_home_book.png",
        "path": "/?dataset=goodbooks",
        "wait": "#itemGrid .card",
        "desc": "图书域首页：Goodbooks-10k 数据规模与热门图书",
    },
    {
        "name": "05_recommend_book.png",
        "path": "/recommend?dataset=goodbooks&uid=2487&algo=hybrid&k=20",
        "wait": "#recGrid .card",
        "desc": "图书域个性化推荐：同一套服务切换数据域",
    },
    {
        "name": "06_item_detail_book.png",
        "path": "/item/25?dataset=goodbooks",
        "wait": ".detail",
        "desc": "物品详情页：评分统计与内容相似物品",
    },
    {
        "name": "07_about.png",
        "path": "/about",
        "wait": ".section",
        "desc": "关于页：系统架构、算法与数据集说明",
    },
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--width", type=int, default=1440)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    C.SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(
            viewport={"width": args.width, "height": 1000},
            device_scale_factor=1,
        )
        for shot in SHOTS:
            url = args.base + shot["path"]
            print(f"[SHOT] {shot['name']} <- {url}", flush=True)
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_selector(shot["wait"], timeout=30000)
            page.wait_for_timeout(700)   # 等字体、渐变色块与过渡动画稳定
            out = C.SCREENSHOTS / shot["name"]
            page.screenshot(path=str(out), full_page=True)
            print(f"       {out.name}  {out.stat().st_size / 1024:.0f} KB  "
                  f"{shot['desc']}", flush=True)
        browser.close()
    print("[SHOT] 全部完成")


if __name__ == "__main__":
    main()
