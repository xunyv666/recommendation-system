"""开发入口。

    python run.py                # 开发模式 (5000 端口)
    waitress-serve --port 8080 run:app   # 生产模式
"""
from __future__ import annotations

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
