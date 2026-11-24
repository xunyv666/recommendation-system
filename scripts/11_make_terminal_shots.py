"""把真实命令输出渲染成终端风格截图（用于报告 7.1 安装/启动/测试步骤）。"""
import html
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(r"E:\桌面\推荐系统期末")
OUT = ROOT / "screenshots"
CASES = [
    ("00_env.png", "terminal_env.txt", "Windows PowerShell — 环境与依赖", "Python 3.12.14 · 关键依赖版本"),
    ("00_start.png", "terminal_start.txt", "Windows PowerShell — 启动服务", "Waitress 监听 8081，健康检查返回 ok"),
    ("00_api.png", "terminal_api.txt", "Windows PowerShell — 接口测试", "GET /api/recommend/1 返回 Top-2 与推荐理由"),
]
TPL = """<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}} body{{margin:0;background:#0b0e14;font-family:Consolas,'Cascadia Mono','Microsoft YaHei',monospace}}
.win{{width:1400px;background:#0b0e14;border:1px solid #23283a;border-radius:14px;overflow:hidden;margin:24px}}
.bar{{height:52px;background:#151925;display:flex;align-items:center;padding:0 20px;gap:9px;border-bottom:1px solid #23283a}}
.dot{{width:13px;height:13px;border-radius:50%}} .r{{background:#ff5f57}} .y{{background:#febc2e}} .g{{background:#28c840}}
.title{{margin-left:16px;color:#9aa4bf;font-size:15px}}
.body{{padding:26px 30px 30px;color:#d6deeb;font-size:17px;line-height:1.62;white-space:pre-wrap;word-break:break-all}}
.p{{color:#7aa2f7;font-weight:600}} .s{{color:#9ece6a}} .n{{color:#e0af68}} .k{{color:#bb9af7}}
.foot{{padding:12px 30px;border-top:1px solid #23283a;color:#5f6b8a;font-size:14px;background:#10141e}}
</style></head><body><div class="win">
<div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="title">{title}</span></div>
<div class="body">{body}</div><div class="foot">{foot}</div></div></body></html>"""


def colorize(text: str) -> str:
    out = []
    for line in text.splitlines():
        e = html.escape(line)
        if line.startswith("PS "):
            e = '<span class="p">' + html.escape("PS ") + "</span>" + html.escape(line[3:])
        elif line.strip().startswith('"') or line.strip().startswith("{"):
            e = e.replace(":", '<span class="k">:</span>', 1) if ":" in e else e
        out.append(e)
    return "\n".join(out)


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1450, "height": 800}, device_scale_factor=2)
    for name, src, title, foot in CASES:
        text = (ROOT / "experiments" / "results" / src).read_text(encoding="utf-8")
        html_text = TPL.format(title=html.escape(title), body=colorize(text), foot=html.escape(foot))
        tmp = ROOT / "experiments" / "results" / "_terminal.html"
        tmp.write_text(html_text, encoding="utf-8")
        pg.goto(tmp.as_uri(), wait_until="load")
        pg.locator(".win").screenshot(path=str(OUT / name))
        print("wrote", name)
    b.close()
