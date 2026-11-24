"""本地预览静态镜像（支持 Cloudflare Pages 的干净 URL 重写）。

`site/_redirects` 告诉 Cloudflare Pages 把 /recommend 映射到 recommend.html，
但 Python 自带的 http.server 不认识这个文件，直接本地预览时点导航会 404。
本脚本读取同一份 `_redirects`，在本地复现同样的重写行为。

用法:
    python scripts/serve_static.py                 # http://127.0.0.1:8082
    python scripts/serve_static.py --port 8090
"""
from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C

SITE = C.ROOT / "site"


class StaticHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        path = urlsplit(path).path
        # 与 site/_redirects 保持一致
        pages = {
            "/": "index.html",
            "/recommend": "recommend.html",
            "/dashboard": "dashboard.html",
            "/about": "about.html",
        }
        if path in pages:
            return str(SITE / pages[path])
        if path.startswith("/item/"):
            return str(SITE / "item.html")
        return super().translate_path(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8082)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if not (SITE / "index.html").exists():
        raise SystemExit("找不到 site/index.html，请先运行 python scripts/10_build_static.py")

    handler = partial(StaticHandler, directory=str(SITE))
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"静态镜像预览: http://{args.host}:{args.port}/  (目录: {SITE})")
        print("按 Ctrl+C 停止")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
