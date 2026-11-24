"""生成课程设计报告（Word）。

严格按照南京财经大学本科毕业论文（设计）规范化要求排版：
    页边距 上2.5 / 下2.5 / 左3.0 / 右2.0 cm
    正文 小四号仿宋，行距 28 磅
    一级标题 四号黑体；二级及以下标题 小四号仿宋
    题目 二号黑体；摘要 / 参考文献 五号仿宋
    页眉右对齐“南京财经大学本科毕业论文（设计）”，五号仿宋
    页码居中

用法:
    python scripts/11_build_report.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

import config as C

OUT = C.REPORT / "推荐系统课程设计报告.docx"
BLACK = RGBColor(0, 0, 0)
GRAY = RGBColor(0x40, 0x40, 0x40)
LIGHT_FILL = "F2F4F7"

# ------------------------------------------------------------------ 文档骨架
doc = Document()
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.top_margin = Cm(2.5)
sec.bottom_margin = Cm(2.5)
sec.left_margin = Cm(3.0)
sec.right_margin = Cm(2.0)
sec.header_distance = Cm(1.5)
sec.footer_distance = Cm(1.5)
sec.different_first_page_header_footer = True


def set_run_font(run, cn_font="仿宋", size=12, bold=False, color=BLACK,
                 ascii_font="Times New Roman", italic=False):
    run.font.name = ascii_font
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)
    rfonts.set(qn("w:eastAsia"), cn_font)


def add_field(paragraph, instr: str, placeholder: str = "") -> None:
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    text_el = OxmlElement("w:t")
    text_el.text = placeholder
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr_el)
    run._r.append(fld_sep)
    run._r.append(text_el)
    run._r.append(fld_end)
    set_run_font(run, "宋体", 10.5)


# 页眉 / 页脚
header_p = sec.header.paragraphs[0]
header_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
h_run = header_p.add_run("南京财经大学本科毕业论文（设计）")
set_run_font(h_run, "仿宋", 10.5)

footer_p = sec.footer.paragraphs[0]
footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
add_field(footer_p, "PAGE", "1")

# 正文样式
normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(12)
normal._element.rPr.rFonts.set(qn("w:eastAsia"), "仿宋")
normal.paragraph_format.line_spacing = Pt(28)
normal.paragraph_format.space_before = Pt(0)
normal.paragraph_format.space_after = Pt(0)
normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

for level, size, cn, bold in ((1, 14, "黑体", True), (2, 12, "仿宋", True),
                              (3, 12, "仿宋", True)):
    st = doc.styles[f"Heading {level}"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(size)
    st.font.bold = bold
    st.font.color.rgb = BLACK
    st._element.rPr.rFonts.set(qn("w:eastAsia"), cn)
    st.paragraph_format.line_spacing = Pt(28)
    st.paragraph_format.space_before = Pt(12 if level == 1 else 6)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.keep_with_next = True
    st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

# Word 打开时自动更新目录域
settings = doc.settings.element
update_fields = OxmlElement("w:updateFields")
update_fields.set(qn("w:val"), "true")
settings.append(update_fields)

FIG_NO = 0
TAB_NO = 0


def para(text: str, size: float = 12, cn: str = "仿宋", bold: bool = False,
         indent: bool = True, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
         spacing: float = 28, before: float = 0, after: float = 0,
         ascii_font: str = "Times New Roman") -> None:
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = Pt(spacing)
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.alignment = align
    if indent:
        pf.first_line_indent = Pt(size * 2)
    r = p.add_run(text)
    set_run_font(r, cn, size, bold, ascii_font=ascii_font)


def formula(text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = Pt(24)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text)
    set_run_font(r, "宋体", 11, ascii_font="Cambria Math")


def bullet(text: str, size: float = 12) -> None:
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = Pt(28)
    pf.left_indent = Pt(24)
    pf.first_line_indent = Pt(-12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run("• " + text)
    set_run_font(r, "仿宋", size)


def heading(text: str, level: int = 1) -> None:
    p = doc.add_paragraph(style=f"Heading {level}")
    r = p.add_run(text)
    size = {1: 14, 2: 12, 3: 12}[level]
    cn = "黑体" if level == 1 else "仿宋"
    set_run_font(r, cn, size, bold=True)


def fig(path: Path, caption: str, width: float = 15.2) -> None:
    global FIG_NO
    assert path.exists(), f"缺少图片: {path}"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    # 图片段落必须用单倍行距：Normal 样式的“固定 28 磅”会把内联图片裁剪成一行高
    p.paragraph_format.line_spacing = 1.0
    p.add_run().add_picture(str(path), width=Cm(width))
    FIG_NO += 1
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(8)
    r = cap.add_run(f"图 {FIG_NO}  {caption}")
    set_run_font(r, "宋体", 10.5)


def crop_top(path: Path, bottom: int) -> Path:
    """截取页面截图的上部，避免整页长图把正文挤成大片空白。

    系统页面截图是 full_page 长图（高度约 2400–2700 px），按 15 cm 宽插入后
    高度会超过一页，导致图注被推到下一页、前一页大量留白。这里只保留标题、
    筛选项与首屏推荐区域，既有信息量，也能与正文自然衔接。
    """
    out_dir = C.REPORT / "_figs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{path.stem}_top{bottom}.png"
    im = Image.open(path)
    im.crop((0, 0, im.width, min(bottom, im.height))).save(out)
    return out


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def table(caption: str, headers: list[str], rows: list[list[str]],
          widths: list[float] | None = None, font_size: float = 9.5,
          align_first_left: bool = False) -> None:
    global TAB_NO
    TAB_NO += 1
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(6)
    cap.paragraph_format.space_after = Pt(2)
    r = cap.add_run(f"表 {TAB_NO}  {caption}")
    set_run_font(r, "宋体", 10.5, bold=True)

    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        run = p.add_run(h)
        set_run_font(run, "宋体", font_size, bold=True)
        shade_cell(hdr[i], LIGHT_FILL)
        hdr[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            p.alignment = (WD_ALIGN_PARAGRAPH.LEFT if (i == 0 and align_first_left)
                           else WD_ALIGN_PARAGRAPH.CENTER)
            run = p.add_run(str(val))
            set_run_font(run, "宋体", font_size)
            cells[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)

    # 表后留白
    after = doc.add_paragraph()
    after.paragraph_format.space_after = Pt(2)
    after.paragraph_format.line_spacing = Pt(6)


def page_break() -> None:
    """插入分页符。

    分页符段落本身如果沿用 28 磅行距，恰好在页底时会因为放不下而被挤到下一页，
    形成一个只有页码的空白页。这里把分页段落压到 1 磅，保证它总能贴在当前页底部。
    """
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(1)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run()
    run.add_break(WD_BREAK.PAGE)
    set_run_font(run, "仿宋", 1)


# ------------------------------------------------------------------ 读取数据
bench = json.loads((C.RESULTS / "benchmark_movielens.json").read_text(encoding="utf-8"))
final = json.loads((C.RESULTS / "benchmark_movielens_final.json").read_text(encoding="utf-8"))
by_model = {r["model"]: r for r in bench if "error" not in r}
for r in final:
    if "error" not in r:
        by_model[r["model"]] = r
rows = sorted(by_model.values(), key=lambda r: -r["test"].get("ndcg@10", 0))

mmr = json.loads((C.RESULTS / "mmr_eval.json").read_text(encoding="utf-8"))
llm = json.loads((C.RESULTS / "llm_demo.json").read_text(encoding="utf-8"))
stats = {
    ds: json.loads((C.DATA_PROCESSED / ds / "stats.json").read_text(encoding="utf-8"))
    for ds in ("movielens", "goodbooks", "bookcrossing")
}
hybrid = None
if (C.RESULTS / "hybrid_eval.json").exists():
    hybrid = json.loads((C.RESULTS / "hybrid_eval.json").read_text(encoding="utf-8"))

# ------------------------------------------------------------------ 封面
for _ in range(3):
    doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("南京财经大学本科毕业论文（设计）")
set_run_font(r, "黑体", 18, bold=True)

for _ in range(3):
    doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("基于多视图融合的双域推荐系统\n设计与实现")
set_run_font(r, "黑体", 22, bold=True)

for _ in range(4):
    doc.add_paragraph()
for label in ("学    院", "专    业", "班    级", "学    号", "学生姓名", "指导教师"):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = Pt(32)
    r = p.add_run(f"{label}：____________________")
    set_run_font(r, "仿宋", 14)

for _ in range(3):
    doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("2026 年 11 月")
set_run_font(r, "仿宋", 14)
page_break()

# ------------------------------------------------------------------ 目录
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("目    录")
set_run_font(r, "黑体", 16, bold=True)
p.paragraph_format.space_after = Pt(12)

p = doc.add_paragraph()
p.paragraph_format.line_spacing = Pt(1)
p.paragraph_format.space_before = Pt(0)
p.paragraph_format.space_after = Pt(0)
add_field(p, r'TOC \o "1-3" \h \z \u',
          "（目录域：在 Word 中右键选择“更新域”即可生成/刷新目录）")
page_break()

# ------------------------------------------------------------------ 题目与摘要
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(12)
r = p.add_run("基于多视图融合的双域推荐系统设计与实现")
set_run_font(r, "黑体", 22, bold=True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(10)
r = p.add_run("摘    要")
set_run_font(r, "黑体", 14, bold=True)

para(
    "针对电影与图书两类典型应用场景，本文设计并实现了一个双域智能推荐系统。系统以开源推荐算法"
    "平台 RecBole 为算法底座，构建统一的 ETL、内容特征工程与 8:1:1 时间序切分流程，集成 EASE、"
    "ItemKNN、BPR、NeuMF、LightGCN、SGL、NCL、DGCF 等十种基线模型，并实现 FREEDOM 式多视图图"
    "融合模型：协同视图在用户—物品二部图上传播，内容视图在由 TF-IDF 文本、类别 multi-hot 与结构化"
    "数值特征构成的物品相似图上传播，通过跨视图 InfoNCE 对齐和自适应门控完成融合。在线层采用"
    "“离线预计算 + 在线查表 + 内容画像补足 + 热度兜底”的分层架构，并在排序后加入 MMR 多样性重排"
    "与推荐理由生成。MovieLens 上的实验表明，EASE 取得最高的 NDCG@10（0.0688），BPR 仅用 24 秒"
    "训练即达到 0.0576；本文实现的 FREEDOM 为 0.0390，低于强基线，本文对其原因进行了拆解分析。"
    "MMR 使推荐列表的最大单一题材占比下降 8.6%、题材覆盖提升 6.4%，同时保留 97.9% 的相关性。"
    "系统在 Windows/CPU 环境完成了安装、测试与实例运行，验证了双域推荐架构的可行性与可复现性。",
    size=10.5, spacing=22,
)
p = doc.add_paragraph()
p.paragraph_format.line_spacing = Pt(22)
p.paragraph_format.space_before = Pt(6)
r = p.add_run("关键词：")
set_run_font(r, "黑体", 10.5, bold=True)
r = p.add_run("推荐系统；多视图融合；图神经网络；对比学习；多样性重排")
set_run_font(r, "仿宋", 10.5)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(14)
p.paragraph_format.space_after = Pt(6)
r = p.add_run("Design and Implementation of a Dual-Domain Recommender System\n"
              "Based on Multi-View Fusion")
set_run_font(r, "黑体", 14, bold=True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Abstract")
set_run_font(r, "黑体", 12, bold=True)

para(
    "This paper designs and implements a dual-domain recommender system for movies and books. "
    "Built on the open-source recommendation platform RecBole, the system provides a unified ETL "
    "pipeline, multi-view content features and an 8:1:1 time-wise split. Ten baselines, including "
    "EASE, ItemKNN, BPR, NeuMF, LightGCN, SGL, NCL and DGCF, are benchmarked under identical "
    "full-sort top-10 protocols. We further implement a FREEDOM-style multi-view graph fusion model, "
    "which propagates representations on both the user-item interaction graph and an item-item content "
    "graph, aligns the two views with an InfoNCE objective, and fuses them through adaptive gates. "
    "The online layer follows an offline-precompute plus online-lookup architecture, with content-based "
    "fallback, popularity fallback, MMR diversification and explanation generation. Experiments on "
    "MovieLens show that EASE achieves the best NDCG@10 of 0.0688, BPR reaches 0.0576 within 24 seconds, "
    "while the implemented FREEDOM obtains 0.0390. The reasons for this gap are analyzed in detail. "
    "MMR reduces the dominant-genre share by 8.6% and increases genre coverage by 6.4%, while retaining "
    "97.9% of the normalized relevance. The system is installed, tested and demonstrated on a Windows "
    "CPU environment, which verifies its feasibility and reproducibility.",
    size=10.5, spacing=22,
)
p = doc.add_paragraph()
p.paragraph_format.line_spacing = Pt(22)
r = p.add_run("Keywords: ")
set_run_font(r, "黑体", 10.5, bold=True)
r = p.add_run("recommender system; multi-view fusion; graph neural network; contrastive learning; "
              "diversified re-ranking")
set_run_font(r, "Times New Roman", 10.5)
page_break()

# ------------------------------------------------------------------ 1 背景
heading("一、应用需求及背景分析", 1)
heading("（一）研究背景", 2)
para(
    "互联网平台的内容规模持续膨胀。MovieLens 的公开数据集中仅有 610 名活跃用户，却对应 9,724 部"
    "电影；Goodbooks-10k 包含 1 万册图书与近 600 万条评分；Book-Crossing 更是包含 25 万余册图书和"
    "90 余万条交互。用户在海量候选中手工筛选的成本越来越高，“信息过载”使个性化推荐从增值功能"
    "转变为内容平台的基础设施。推荐系统通过建模用户历史行为与物品属性，在有限曝光位中排列出最可能"
    "被接受的内容，从而同时提升用户体验、内容分发效率和平台商业价值。"
)
para(
    "从技术演进看，推荐算法经历了从协同过滤、矩阵分解到深度学习的多个阶段。ItemKNN 以物品共现"
    "相似度完成召回，简单可靠；BPR 将隐式反馈转化为成对排序问题；NeuMF 用多层感知机拟合用户与物品"
    "的非线性交互；LightGCN 等图神经网络在用户—物品二部图上传播高阶协同信号；SGL、NCL、DGCF 则"
    "分别从自监督增广、邻域对比和解耦表示的角度缓解稀疏性问题。与此同时，EASE 这类线性自编码器"
    "凭借闭式解和强正则，在小规模稀疏数据上往往不输深度模型。如何在同一数据切分与同一评测口径下"
    "比较这些算法，并把离线结论可靠地落到在线服务，是推荐系统课程设计需要回答的核心问题。"
)
para(
    "本课题选取电影与图书两个应用域：电影域元数据丰富、时间戳完整，适合验证时序切分与多视图内容"
    "特征；图书域交互更稀疏、物品规模更大，适合检验系统的泛化能力与工程可扩展性。两个域共用一套"
    "数据规范、算法管线与服务框架，既能展示推荐算法的差异，也能体现推荐系统从离线实验到在线产品"
    "的完整链路。"
)

heading("（二）应用需求分析", 2)
para(
    "从用户视角看，系统需要满足四类需求。其一是个性化：不同用户的题材偏好、评分习惯差异显著，"
    "推荐结果不能退化为统一的热门榜。其二是跨域一致性：用户应能在电影与图书之间切换，并获得相同"
    "交互范式的推荐、详情与历史对照。其三是冷启动与长尾覆盖：新用户没有历史行为时，系统仍需给出"
    "可解释的热门或内容推荐；长尾物品也不能因交互稀少而永远得不到曝光。其四是多样性与可解释性："
    "Top-N 列表若被同一题材刷屏，会降低用户的新鲜感；每条推荐还应说明“为什么推荐”，以建立信任。"
)
para(
    "从运营与开发视角看，系统需要满足三类需求。其一是可比较：所有算法必须使用同一份清洗数据、"
    "同一时间序切分和同一套指标，否则“某模型更好”的结论没有意义。其二是可运维：训练与 serving "
    "解耦，在线请求只做查表和轻量重排，保证毫秒级响应并支持水平扩展。其三是低成本与可复现："
    "课程环境只有 CPU，系统应避免强依赖 GPU 或外部在线服务；依赖版本、随机种子、数据切分和实验"
    "脚本都应固化，便于教师或同学复现实验结果。"
)

heading("（三）研究内容与主要工作", 2)
para("围绕上述需求，本文完成了以下工作：")
bullet("设计统一的数据 ETL：吸收 MovieLens、Goodbooks-10k、Book-Crossing 三个数据集的字段差异，"
       "输出 RecBole atomic 格式、Parquet 交互表与 SQLite 业务库；对无时间戳的数据集合成单调伪时间戳，"
       "保证三个数据集都能采用时间序切分，避免随机切分造成未来信息泄漏。")
bullet("构建多视图内容特征：将标题/作者/标签文本的 TF-IDF 经 SVD 降维，与类别 multi-hot、年份/热度/"
       "均分等结构化数值拼接并 L2 归一化，再计算 Top-50 物品内容近邻，作为内容视图与冷启动召回的基础。")
bullet("实现统一训练与评测管线：把 11 个模型接入同一 RecBole 配置，采用 8:1:1 按用户时间序切分、"
       "Top-10 全量排序，报告 Recall、Precision、NDCG、MRR、Hit、MAP 六项指标，并记录训练耗时。")
bullet("实现 FREEDOM 式多视图图融合模型：协同图传播 + 内容图传播 + 跨视图对比对齐 + 自适应门控，"
       "并针对 CPU 环境实现全批 BPR 训练器，把训练时间从分钟级进一步压缩。")
bullet("设计在线推荐服务：离线预计算 Top-N 落库，在线按“预计算 → 内容补足 → 热度兜底”三级路径取数，"
       "hybrid 模式在 60 个候选中用 MMR 重排到 20 个，并生成模板或大模型推荐理由。")
bullet("完成系统实现与部署：Flask + Waitress 提供页面与 REST API，SQLAlchemy 支持 SQLite/MySQL 切换，"
       "前端零 CDN 依赖，并可构建为 Cloudflare Pages 静态镜像。")
bullet("完成实验分析与报告：从准确性、训练效率、多样性、可解释性四个维度分析结果，如实讨论"
       "FREEDOM 未超过强基线的原因，并给出改进方向。")

heading("（四）本章小结", 2)
para(
    "本章从信息过载与算法演进出发，明确了电影、图书双域推荐系统的用户需求与工程需求，并给出了"
    "本文的主要工作。下一章将在此基础上给出系统的总体架构与功能设计。"
)

# ------------------------------------------------------------------ 2 架构
heading("二、推荐系统架构设计", 1)
heading("（一）总体架构", 2)
para(
    "系统采用“离线训练与预计算 + 在线查表与服务”的两段式架构，如图 1 所示。离线部分由数据与特征、"
    "模型训练、统一评测、Top-N 预计算四个阶段串联；在线部分由浏览器、Flask REST API、在线推荐服务"
    "与数据库组成；部署部分通过 GitHub、Cloudflare Pages 与 Cloudflare Tunnel 完成静态前端与内网"
    "服务的公网暴露。两段式架构的核心取舍是：把昂贵的图传播、矩阵求逆和全量打分放在离线完成，"
    "在线只承担 O(1) 的数据库查询与 O(k²) 的轻量重排，从而在单台 CPU 服务器上也能获得稳定的响应时间。"
)
fig(C.FIGURES / "08_architecture.png", "双域智能推荐系统总体架构", 15.8)

heading("（二）离线层设计", 2)
para(
    "离线层的第一阶段是数据与特征。ETL 模块读取原始 CSV，统一为 user_id、item_id、rating、timestamp "
    "四列交互表，并输出 items.parquet、ratings.parquet、.inter、.item 与 stats.json。对 Goodbooks 与 "
    "Book-Crossing 这类没有时间戳的数据集，系统在用户内部合成单调递增的伪时间戳，使 8:1:1 切分"
    "仍然按时间先后进行；这比随机切分更接近真实上线场景，也能暴露模型对分布漂移的敏感性。"
)
para(
    "第二阶段是模型训练。所有模型共享 recsys.runner.build_config 生成的 RecBole 配置，仅通过超参"
    "字典区分。训练统一使用固定随机种子 2026、均匀负采样（每个正样本 1 个负样本）、最多 60 轮、"
    "验证集 NDCG@10 连续 10 轮不提升则早停。非神经模型（Random、Pop、ItemKNN、EASE）只跑 1 轮，"
    "避免重复评测。第三阶段是统一评测，采用按用户分组的时间序 8:1:1 切分和全排序协议：对每个测试"
    "用户，在全部物品上打分，屏蔽训练集与验证集中已交互的物品，再取 Top-10 计算指标。"
)
para(
    "第四阶段是 Top-N 预计算。脚本加载最优 checkpoint，对每个用户输出 Top-20 推荐并写入 "
    "recommendations 表；hybrid 结果额外保留 60 个候选，供在线 MMR 重排使用。预计算表同时保存"
    "分数与推荐理由，在线服务无需再次访问模型，也不需要 GPU。"
)

heading("（三）在线层设计", 2)
para(
    "在线层由 Flask 提供页面路由与 REST API，生产环境用 Waitress 作为 WSGI 服务器。推荐服务"
    "recommender.py 设计了三条取数路径：其一是热用户路径，直接查询 recommendations 表中对应"
    "算法与数据集的预计算记录；其二是内容补足路径，当预计算不足 k 条时，用用户高分物品的题材画像"
    "做内容召回，补足候选；其三是冷启动路径，当用户完全没有历史时，退化为贝叶斯平滑后的热度榜。"
    "这种分级兜底保证任何用户、任何时刻都能拿到推荐结果，而不会返回空列表或报错。"
)
para(
    "hybrid 模式在取数后增加两层处理。第一层是多路融合：预计算的图模型分数、内容画像分数和热度"
    "分数先按用户做 z-score 标准化，再按权重相加；标准化时只在有限值上计算均值和方差，并把被屏蔽"
    "的历史物品统一压到 −3σ，避免 −inf 破坏统计量。第二层是 MMR 多样性重排：从 60 个候选中迭代"
    "选择 20 个，既考虑与用户的相关性，也惩罚与已选物品的相似度。推荐理由优先使用离线写入的模板"
    "理由，也可以在离线演示中调用本地 Qwen2.5-0.5B-Instruct 生成更自然的解释。"
)
para(
    "接口设计遵循“前端只拉数据、渲染交给模板/JS”的原则。主要接口包括 /api/overview、/api/popular、"
    "/api/items、/api/items/<id>、/api/users、/api/history/<uid>、/api/recommend/<uid>、/api/metrics 与 "
    "/api/feedback。同一套接口既服务于 Flask 模板，也被静态镜像的 fetch 适配层映射到预计算 JSON，"
    "因此前端代码无需为两种部署方式写两套逻辑。"
)

heading("（四）数据与存储设计", 2)
para(
    "业务库使用 SQLAlchemy 抽象，开发环境为 SQLite，生产环境只需设置 DATABASE_URL 即可切换到 "
    "MySQL。核心表包括：items（物品元数据、评分统计、热度）、users（用户统计）、ratings（交互）、"
    "recommendations（离线 Top-N）、item_similarity（内容近邻）、algorithm_metrics（算法指标）与 "
    "feedback_log（在线行为）。其中 items 与 users 使用自增代理主键，并在 (dataset, id) 上建立唯一"
    "约束，避免电影与图书的原始 id 重名造成串号；recommendations 在 (user_id, algo, rank) 上建立"
    "联合索引，保证在线查询走索引而不是全表扫描。"
)
table(
    "核心数据表设计",
    ["表名", "主要字段", "用途"],
    [
        ["items", "id, dataset, title, genres, year, avg_rating, n_ratings, popularity", "物品元数据与热度"],
        ["users", "id, dataset, n_ratings, avg_rating", "用户统计"],
        ["ratings", "user_id, item_id, dataset, rating, timestamp", "历史交互"],
        ["recommendations", "user_id, dataset, algo, rank, item_id, score, reason", "离线 Top-N"],
        ["item_similarity", "src_id, dst_id, dataset, score", "内容相似物品"],
        ["algorithm_metrics", "dataset, model, metric, value, train_seconds", "算法看板"],
        ["feedback_log", "user_id, item_id, action, algo, position", "在线行为日志"],
    ],
    widths=[3.1, 8.4, 4.0], font_size=9,
)

heading("（五）推荐功能展示", 2)
para(
    "系统首页如图 2 所示。页面顶部展示系统定位与推荐流水线，中部给出物品数、用户数、评分数三项"
    "规模统计，下方是按题材筛选的热门内容。首页的数据全部来自真实数据库，题材 chip 的点击会触发"
    "带 genre 参数的 /api/popular 请求，而不是前端静态过滤。"
)
fig(crop_top(C.SCREENSHOTS / "01_home_movie.png", 1360), "MovieLens 电影域首页", 15.2)
para(
    "个性化推荐页如图 3 所示。用户可以选择演示用户、推荐算法与返回数量；页面同时展示该用户的真实"
    "历史行为，便于对照推荐结果是否合理。图 3 中用户 1 的历史集中在动作、冒险与剧情题材，推荐列表"
    "以《虎胆龙威 3》《指环王》《肖申克的救赎》等高分作品为主，并给出“题材同属 Action”“评分 3.6"
    "（144 人评）”等理由。"
)
fig(crop_top(C.SCREENSHOTS / "02_recommend_movie.png", 1650), "MovieLens 个性化推荐页（用户 1，hybrid）", 15.2)
para(
    "算法看板如图 4 所示，展示同一数据切分下各模型的 Recall@10、NDCG@10、MRR@10、Precision@10 与"
    "训练耗时，并按 NDCG 降序排列。看板不仅是实验结果的展示，也是系统可解释性的一部分：运营人员"
    "可以直观看到“更复杂的模型未必更好”，从而在效果、成本与稳定性之间做取舍。"
)
fig(C.SCREENSHOTS / "03_dashboard_movie.png", "算法效果看板", 15.2)
para(
    "图书域复用同一套页面与接口，仅通过 dataset 参数切换数据源。图 5 展示了图书域用户 7 的推荐"
    "结果：历史以科幻与奇幻为主，推荐列表覆盖《安德的游戏》《银河系漫游指南》《基地》等作品；"
    "图书封面由数据集提供的图片地址渲染，缺失时自动退化为首字母渐变卡片。图 6 展示了物品详情页"
    "与内容相似物品，《哈利·波特与死亡圣器》的相似结果集中在同系列与同题材作品，说明三视图内容"
    "特征能够捕捉系列、题材与受众的重合。"
)
fig(crop_top(C.SCREENSHOTS / "05_recommend_book.png", 1650), "图书域个性化推荐页（用户 7）", 15.2)
fig(C.SCREENSHOTS / "06_item_detail_book.png", "物品详情与内容相似推荐", 15.2)

heading("（六）部署方案", 2)
para(
    "系统提供两种部署形态。第一种是 Flask 动态站点：开发环境执行 python run.py，生产环境执行 "
    "waitress-serve --port 8080 run:app，再通过 Cloudflare Tunnel 把内网服务映射为公网 HTTPS。"
    "第二种是静态镜像：scripts/10_build_static.py 把首页、推荐页、看板、详情页与预计算 JSON 导出到 "
    "site/，并注入 static-api.js 作为 fetch 适配层，使 /api/* 请求在浏览器端直接命中本地 JSON。"
    "静态镜像可以部署到 Cloudflare Pages，即使后端离线也能完整演示；动态站点则用于展示真实数据库"
    "查询与在线重排能力。两者共用同一套前端代码，避免了演示环境与生产环境行为不一致。"
)

heading("（七）本章小结", 2)
para(
    "本章给出了系统的总体架构、离线与在线分层、数据库设计、功能页面与部署方案。架构的核心是"
    "训练与 serving 解耦：离线负责重计算，在线负责轻量取数与重排。下一章将说明系统的安装、测试与"
    "实例运行过程。"
)

# ------------------------------------------------------------------ 3 安装测试
heading("三、系统安装、测试与实例运行", 1)
heading("（一）运行环境", 2)
para(
    "系统在 Windows 11 + Python 3.12 环境下开发和验证，全部实验在 CPU 上完成，未依赖 GPU。"
    "SQLite 业务库约 223 MB，包含电影与图书两个域的物品、评分、相似度与预计算推荐。主要环境"
    "参数如表 3 所示。"
)
table(
    "软硬件运行环境",
    ["项目", "配置"],
    [
        ["操作系统", "Windows 11（x86-64）"],
        ["Python", "3.12.14（venv 虚拟环境）"],
        ["计算设备", "CPU（未使用 GPU / CUDA）"],
        ["算法框架", "PyTorch 2.5.1 + RecBole 1.2.0"],
        ["Web 框架", "Flask 3.1.3 + Waitress 3.0.2"],
        ["数据库", "SQLite 3（开发）/ MySQL 8（可选）"],
        ["浏览器", "Chrome / Edge（桌面端）"],
    ],
    widths=[4.5, 11.0], font_size=10,
)
para(
    "依赖版本必须严格锁定。RecBole 1.2.0 仍在使用 numpy 已移除的 np.float_ 别名，且依赖 scipy 的 "
    "dok_matrix._update 接口；当 numpy≥2 或 scipy≥1.13 时，数据加载会直接报错。requirements.txt "
    "因此固定 numpy==1.26.4、scipy==1.12.0、pandas==2.2.3，并锁定 torch、matplotlib 等可能间接"
    "引入新 numpy 的包。"
)
table(
    "关键依赖版本",
    ["依赖", "版本", "作用"],
    [
        ["numpy", "1.26.4", "数值计算（兼容 RecBole）"],
        ["scipy", "1.12.0", "稀疏矩阵与图构造"],
        ["pandas", "2.2.3", "数据处理"],
        ["torch", "2.5.1", "深度学习训练"],
        ["recbole", "1.2.0", "推荐算法平台"],
        ["scikit-learn", "1.5.2", "TF-IDF、SVD、KMeans"],
        ["flask / waitress", "3.1.3 / 3.0.2", "Web 服务"],
        ["python-docx", "1.2.0", "报告生成"],
    ],
    widths=[4.2, 3.6, 7.7], font_size=9.5,
)

heading("（二）安装步骤", 2)
para("安装过程分为四步。第一步创建虚拟环境并安装依赖：")
formula("python -m venv venv")
formula(r"venv\Scripts\activate")
formula("pip install -r requirements.txt")
para(
    "第二步准备原始数据。将 MovieLens（ml-latest-small）放到 data/raw/movielens/，将 Goodbooks-10k "
    "放到 data/raw/goodbooks/，将 Book-Crossing 放到 data/raw/book-crossing/。目录内应分别包含 "
    "ratings.csv、movies.csv、tags.csv、links.csv；ratings.csv、books.csv、book_tags.csv、tags.csv；"
    "BX-Book-Ratings.csv、BX-Books.csv。"
)
para("第三步执行数据与特征流水线：")
formula("python -m recsys.etl")
formula("python scripts/01_build_features.py")
formula("python scripts/03_build_db.py")
para(
    "ETL 会输出统一的 .inter/.item 文件、items.parquet、ratings.parquet 与 stats.json；特征脚本会"
    "生成 item_features.npy、item_ids.json 与 item_similarity.parquet；建库脚本把物品、用户、评分、"
    "相似度和指标写入 SQLite。执行成功后，控制台会打印每个数据集的数据规模与相似度边数。"
)
para("第四步训练与评测。以 MovieLens 为例：")
formula("python scripts/02_run_benchmark.py --dataset movielens")
formula("python scripts/08_sync_metrics.py --dataset movielens")
para(
    "完整基准包含 11 个模型，EASE 需要计算 9,724×9,724 矩阵的逆，是耗时最长的一步（约 4 小时）；"
    "若只需验证流程，可先运行 LightGCN、BPR、ItemKNN 等轻量模型。训练完成后，checkpoint 保存在 "
    "experiments/results/checkpoints/，指标保存在 benchmark_movielens.json。"
)

heading("（三）服务启动", 2)
para("开发模式启动 Flask：")
formula("python run.py")
para("浏览器访问 http://127.0.0.1:5000 即可。生产模式使用 Waitress：")
formula("waitress-serve --port 8080 run:app")
para(
    "若需切换到 MySQL，只需设置环境变量 DATABASE_URL，例如 "
    "mysql+pymysql://user:password@127.0.0.1:3306/recsys?charset=utf8mb4，然后重新执行 "
    "python scripts/03_build_db.py。代码层不需要修改，这也是 SQLAlchemy 抽象带来的直接收益。"
)
para("静态镜像的构建与预览：")
formula("python scripts/10_build_static.py")
formula("python -m http.server 8090 --directory site")
para(
    "构建脚本会重新生成 site/index.html、recommend.html、dashboard.html、about.html、item.html、"
    "data/*.json 与 _redirects，并把 Flask 的 CSS/JS 复制到 site/static/。使用任意静态服务器打开 "
    "site/ 即可验证无后端场景下的完整交互。"
)

heading("（四）功能测试", 2)
para(
    "功能测试覆盖 API、页面与推荐逻辑三个层面。API 层使用 Flask test_client 逐个请求核心接口，"
    "检查状态码与返回结构；页面层检查五个主页面是否返回 200；推荐层检查推荐条数、历史物品过滤、"
    "算法切换与冷启动兜底。测试结果如表 4 所示。"
)
table(
    "功能测试用例与结果",
    ["编号", "测试项", "输入 / 操作", "预期结果", "结果"],
    [
        ["T1", "健康检查", "GET /api/health", "status=ok", "通过"],
        ["T2", "数据概览", "GET /api/overview?dataset=movielens", "返回 610 用户 / 9724 物品", "通过"],
        ["T3", "热门榜", "GET /api/popular?dataset=movielens&k=5", "返回 5 条", "通过"],
        ["T4", "个性化推荐", "GET /api/recommend/1?algo=hybrid&k=20", "返回 20 条且不含历史物品", "通过"],
        ["T5", "算法切换", "algo=EASE / ItemKNN / FREEDOM", "source 随算法变化", "通过"],
        ["T6", "物品详情", "GET /api/items/25?dataset=goodbooks", "返回详情与 12 条相似物品", "通过"],
        ["T7", "页面渲染", "GET /、/recommend、/dashboard、/about、/item/1", "全部 HTTP 200", "通过"],
        ["T8", "反馈接口", "POST /api/feedback", "写入 feedback_log 并返回 id", "通过"],
    ],
    widths=[1.2, 3.0, 6.6, 4.4, 1.6], font_size=8.8,
)
para(
    "实测中 /api/health、/api/overview、/api/popular 均返回 200，MovieLens 概览为 610 名用户、"
    "9,724 个物品、100,836 条评分，Top-5 热门请求返回 5 条记录；用户 1 的 hybrid 推荐返回 20 条，"
    "来源标记为 precomputed:hybrid，重排标记为 mmr；五个页面全部返回 200。说明系统在开发环境下"
    "功能完整、接口契约稳定。"
)

heading("（五）实例运行", 2)
para(
    "以 MovieLens 用户 1 为例。该用户在训练集中有 232 条评分，历史高分作品包括《墓碑镇》"
    "《加拿大培根》《平克·弗洛伊德：墙》《圣女贞德》《早安越南》《罗伯·罗伊》《亨利五世》"
    "《辛德勒的名单》《陆军野战医院》《绿里奇迹》《全民公敌》《七宗罪》，题材集中在动作、冒险、"
    "剧情与战争。系统在 hybrid 模式下返回的 Top-8 如表 5 所示。"
)
table(
    "用户 1 的 hybrid 推荐结果（Top-8）",
    ["排名", "物品", "题材", "分数", "推荐理由（节选）"],
    [
        ["1", "Die Hard: With a Vengeance (1995)", "Action / Crime / Thriller", "5.679",
         "题材同属 Action，评分 3.6（144 人评）"],
        ["2", "Lord of the Rings: The Fellowship of the Ring (2001)", "Adventure / Fantasy", "5.636",
         "题材同属 Adventure，评分 4.1（198 人评）"],
        ["3", "Shawshank Redemption, The (1994)", "Crime / Drama", "5.635",
         "评分 4.4（317 人评）"],
        ["4", "Apollo 13 (1995)", "Adventure / Drama / IMAX", "5.579",
         "题材同属 Adventure，评分 3.8（201 人评）"],
        ["5", "Lord of the Rings: The Two Towers (2002)", "Adventure / Fantasy", "5.573",
         "题材同属 Adventure，评分 4.0（188 人评）"],
        ["6", "Terminator 2: Judgment Day (1991)", "Action / Sci-Fi", "5.538",
         "题材同属 Action，评分 4.0（224 人评）"],
        ["7", "True Lies (1994)", "Action / Adventure / Comedy", "5.499",
         "题材同属 Action、Adventure，评分 3.5（178 人评）"],
        ["8", "Aladdin (1992)", "Adventure / Animation / Children", "5.487",
         "题材同属 Adventure、Comedy，评分 3.8（183 人评）"],
    ],
    widths=[1.2, 7.0, 4.0, 1.8, 4.2], font_size=8.5, align_first_left=False,
)
para(
    "从结果看，推荐覆盖了动作、冒险、剧情三类主偏好，且没有重复用户已看过的作品；排名第 3 的"
    "《肖申克的救赎》虽然题材只命中剧情，但凭借 4.4 的高分与强协同信号进入前三，说明融合分数"
    "并非单纯按题材匹配。MMR 重排后，列表没有被《指环王》系列完全占据，而是穿插了动作、动画与"
    "犯罪题材，兼顾了相关性与新鲜感。"
)
para(
    "图书域以用户 7 为例。该用户有 155 条评分，历史包括《安德的游戏》《银河系漫游指南》《基地》"
    "《饥饿游戏》《火星编年史》《使女的故事》等科幻与反乌托邦作品。系统返回的前六名为《安德的"
    "游戏》《银河系漫游指南》《基地》《饥饿游戏》《火星编年史》《使女的故事》，与历史偏好高度"
    "一致；后续推荐扩展到《时间机器》《华氏 451》《失落的世界》等经典科幻，体现了内容画像与"
    "协同信号的互补。该实例也说明同一套服务代码可以通过 dataset 参数无缝迁移到图书域。"
)
para(
    "最后在算法看板中查看 MovieLens 的评测结果。看板按 NDCG@10 降序展示 EASE、ItemKNN、NCL、BPR、"
    "NeuMF、Pop、LightGCN、DGCF、FREEDOM、SGL、Random 等模型，并显示每个模型的训练耗时。该页面"
    "的数据来自 algorithm_metrics 表，由 08_sync_metrics.py 从实验 JSON 同步；因此离线实验重跑后，"
    "只需重新同步即可刷新看板，不需要改前端代码。"
)

heading("（六）本章小结", 2)
para(
    "本章给出了系统的软硬件环境、依赖锁定、安装与数据准备步骤、服务启动方式、功能测试结果以及"
    "电影/图书两个域的实例运行情况。测试表明系统接口完整、页面可用、推荐结果符合用户历史偏好，"
    "具备可演示性和可复现性。下一章将深入分析推荐算法的设计与实验结果。"
)

# ------------------------------------------------------------------ 4 算法
heading("四、推荐算法描述与分析", 1)
heading("（一）问题定义与符号", 2)
para(
    "设用户集合为 U，物品集合为 I，交互矩阵为 R∈{0,1}^{|U|×|I|}，其中 r_ui=1 表示用户 u 与物品 i "
    "发生过交互。推荐任务是在给定用户 u 与候选集合 I 的条件下，学习打分函数 f(u,i)，将候选按分数"
    "降序排列并返回 Top-K。本文采用全排序评测：对每个测试用户，对全部物品打分，屏蔽训练集与验证集"
    "中的历史物品后取前 K 个，从而避免“从固定负样本中排序”带来的指标虚高。"
)

heading("（二）数据预处理与多视图特征", 2)
para(
    "物品内容特征由三个视图拼接而成。文本视图把标题、题材、用户标签（图书为作者、标题、出版社）"
    "拼接后小写化，使用 TF-IDF 提取 1–2 元词组，再用 TruncatedSVD 降到 128 维："
)
formula("X_text = TF-IDF(title, genres, tags),   Z_text = SVD_128(X_text)")
para(
    "类别视图把题材/标签按“|”或空格切分后做 multi-hot 编码；结构化视图使用年份、log(1+交互数) 与"
    "平均评分三个数值，经 StandardScaler 标准化。三个视图横向拼接后做 L2 归一化："
)
formula("F = [Z_text ; Z_cat ; Z_num],   F ← F / ||F||_2")
para(
    "L2 归一化的作用是让不同视图的尺度可比，否则文本 SVD 的大数值会压制类别与数值视图。归一化后，"
    "物品向量的点积即余弦相似度，可直接用于内容近邻与内容图构建。对每个物品保留 Top-50 正相似近邻，"
    "得到物品—物品内容图。该图既用于 FREEDOM 的内容视图传播，也用于详情页的“相似物品”与冷启动召回。"
)

heading("（三）基于内容的推荐", 2)
para(
    "基于内容的推荐不依赖其他用户的行为，而是根据用户历史高分物品的内容画像做匹配。系统取用户"
    "评分最高的若干物品，统计其题材分布并按评分加权（高分物品权重 2，其余权重 1），得到用户偏好"
    "题材集合；再在候选物品中筛选命中主偏好题材、评分人数不少于 10 的物品，按“平均评分 × "
    "log(1+评分数)”排序。设置评分人数阈值是为了避免“1 人打 5 分”的长尾物品被误推，这是内容推荐"
    "最常见的陷阱之一。该路径同时承担新用户冷启动与预计算不足时的补足职责。"
)

heading("（四）协同过滤算法", 2)
para(
    "ItemKNN 基于物品共现计算相似度。对物品 i 与 j，其余弦相似度为："
)
formula("s_ij = Σ_u r_ui·r_uj / ( sqrt(Σ_u r_ui²) · sqrt(Σ_u r_uj²) )")
para(
    "用户 u 对物品 j 的分数为 u 已交互物品相似度的加权和：score(u,j)=Σ_{i∈N(u)} s_ij。ItemKNN 不"
    "需要梯度训练，可解释性强，在稀疏数据上往往是很难打败的强基线。本文取 k=20 个最近邻。"
)
para(
    "BPR 把推荐建模为成对排序。对每个正样本 (u,i) 采样一个负样本 j，最大化正样本分数高于负样本"
    "的概率："
)
formula("L_BPR = − Σ_{(u,i,j)∈D} ln σ( f(u,i) − f(u,j) ) + λ||Θ||²")
para(
    "其中 σ 为 sigmoid，D 为训练三元组，Θ 为模型参数。BPR 只使用隐式反馈的相对顺序，训练快、"
    "实现简单，是本文衡量深度模型性价比的重要参照。"
)
para(
    "EASE 是一个线性自编码器，具有闭式解。令 X 为用户—物品交互矩阵，G = XᵀX + λI，则权重矩阵为："
)
formula("P = G⁻¹,   B = I − P / diag(P),   Ŷ = XB")
para(
    "其中 diag(P) 表示取 P 的对角线构造对角矩阵，除法为逐元素除法。EASE 通过强正则约束权重矩阵"
    "的对角线，等价于学习物品之间的去噪相似度。它没有迭代训练过程，但需要一次 |I|×|I| 矩阵求逆；"
    "在 9,724 个物品上这是一次约 4 小时的计算，但推理阶段只需一次矩阵乘法，因而非常适合“离线贵、"
    "在线快”的架构。"
)

heading("（五）图神经网络推荐", 2)
para(
    "LightGCN 在用户—物品二部图上做线性传播。令 A 为加入自环的邻接矩阵，D 为度矩阵，归一化邻接"
    "矩阵为："
)
formula("Ã = D^{-1/2} A D^{-1/2}")
para(
    "第 l 层表示为 E^{(l+1)} = Ã E^{(l)}，最终表示为各层平均 E = (1/(L+1)) Σ_{l=0}^{L} E^{(l)}，"
    "用户与物品的分数为二者最终表示的内积。LightGCN 去掉了非线性变换与特征变换，只保留邻域聚合，"
    "在小规模数据上更不容易过拟合，也更容易分析过平滑现象。"
)
para(
    "SGL 在 LightGCN 基础上引入自监督：对图做节点丢弃、边丢弃或随机游走增广，构造同一节点的两个"
    "视图，并用 InfoNCE 拉近正对、推远负对。NCL 进一步引入邻域对比：除了实例级对比，还把用户/物品"
    "与 KMeans 聚类中心做对比，使表征在语义邻域上更紧凑。DGCF 则把用户/物品表示拆成多个意图通道，"
    "在通道间做解耦与独立性约束，试图缓解单一表征无法表达多兴趣的问题。三者都通过额外的对比损失"
    "增强稀疏交互下的表征学习，但代价是更多的超参、更长的训练时间与对增广策略的敏感性。"
)

heading("（六）FREEDOM 式多视图融合模型", 2)
para(
    "FREEDOM 原文面向多模态推荐，核心思想是冻结物品—物品模态图、对用户—物品图做去噪，并在"
    "多视图之间做自适应融合。本文结合课程数据的特点实现了其简化版本，保留三个关键部件：协同视图、"
    "内容视图与跨视图对齐。"
)
para(
    "协同视图与 LightGCN 相同：在用户—物品图上做 L 层传播并平均池化，得到用户协同表示 u_c 与物品"
    "协同表示 i_c。内容视图先把多视图特征 F 经线性层投影到 d 维并 L2 归一化，再在物品—物品内容图上"
    "传播 S 步："
)
formula("i_t^{(0)} = normalize(W_t F),   i_t^{(s+1)} = normalize((1−β)·i_t^{(s)} + β·S·i_t^{(s)})")
para(
    "其中 S 为按行归一化的内容相似矩阵，β 控制保留自身信息与聚合邻居信息的比例（本文取 0.5），"
    "S 取 2 步。用户内容表示 u_t 为其交互物品内容表示的平均并归一化。两个视图的最终打分为："
)
formula("ŷ(u,i) = w_c · ⟨u_c, i_c⟩ + w_t · ⟨u_t, i_t⟩")
para(
    "其中 w = softmax(fuse_logits) ⊙ exp(log_scale)，⊙ 为逐元素乘法。softmax 决定两个视图的相对"
    "可信度，exp(log_scale) 允许每个视图有独立的尺度，避免归一化后内积范围过小。为了让协同表示与"
    "内容表示处于同一语义空间，模型在每轮随机采样的物品子集上加入跨视图 InfoNCE："
)
formula("L_align = − (1/|B|) Σ_{i∈B} log [ exp(sim(a_i,b_i)/τ) / Σ_{j∈B} exp(sim(a_i,b_j)/τ) ]")
para(
    "其中 a_i 为协同物品表示经对齐投影后的向量，b_i 为内容表示，τ 为温度系数（0.2）。总损失为"
    "BPR 排序损失、对齐损失与 L2 正则的加权和："
)
formula("L = L_BPR + 0.15·L_align + 1e-4·||Θ||²")
para(
    "工程实现上，通用 RecBole Trainer 以 batch 为单位调用 calculate_loss，每个 batch 都要重算一次"
    "图传播，在 CPU 上约 0.36 秒/次，60 轮训练需要十余分钟。本文为 FREEDOM 实现了全批训练器："
    "每轮只做一次图传播，用全部正样本与当轮重采样的负样本计算 BPR，再反传更新。MovieLens 上只有"
    "610 个用户与 9,724 个物品，全批训练完全可行，训练时间降到约 158 秒，而负样本仍然逐轮刷新，"
    "没有退化成静态负采样。"
)

heading("（七）融合排序与 MMR 重排", 2)
para(
    "在线 hybrid 先对多路分数做逐用户 z-score。设第 m 路分数为 s_m(u,i)，标准化为："
)
formula("z_m(u,i) = clip( (s_m(u,i) − μ_m(u)) / σ_m(u), −3, 6 )")
para(
    "其中 μ_m(u)、σ_m(u) 只在该用户的有效候选上统计，历史物品与 PAD 统一置为 −3。融合分数为"
    "Σ_m w_m z_m(u,i)，权重由工程经验或验证集搜索确定。融合后候选仍可能同质化，因此加入 MMR："
)
formula("MMR = argmax_{i∈R\\S} [ λ·sim(u,i) − (1−λ)·max_{j∈S} sim(i,j) ]")
para(
    "其中 R 为候选池，S 为已选集合，sim(u,i) 为归一化相关性，sim(i,j) 为物品内容相似度，λ=0.6。"
    "MMR 每次选择“相关性高且与已选物品不相似”的物品，从而在相关性与多样性之间取平衡。系统从 60 个"
    "候选中选 20 个，保证重排有足够的替换空间，而不是只把同一批物品重新排序。"
)

heading("（八）大模型推荐理由", 2)
para(
    "推荐理由模块支持两种模式。默认模式使用模板：根据推荐来源、题材命中、平均评分与评分人数拼接"
    "一句可解释的理由，完全可复现且零延迟。增强模式加载本地 Qwen2.5-0.5B-Instruct，把用户画像与"
    "候选物品信息填入提示词，让模型生成自然语言解释；若模型不可用或生成失败，自动回退到模板。"
    "大模型只用于离线演示与理由生成，不进入在线排序主链路，以避免 CPU 推理延迟和幻觉对推荐结果的"
    "影响。"
)

heading("（九）本章小结", 2)
para(
    "本章从问题定义出发，依次说明了多视图内容特征、基于内容的推荐、ItemKNN/BPR/EASE、LightGCN/"
    "SGL/NCL/DGCF、FREEDOM 式多视图融合、hybrid 融合与 MMR 重排，以及大模型理由生成。重点给出了"
    "各算法的目标函数与工程实现取舍，为下一章的实验分析提供依据。"
)

# ------------------------------------------------------------------ 5 实验
heading("五、实验结果与分析", 1)
heading("（一）数据集与统计", 2)
para(
    "三个数据集的基本统计如表 6 所示。MovieLens 是主实验集，规模适中、时间戳完整；Goodbooks-10k "
    "用于图书域在线演示，ETL 使用全量评分，业务库只导入交互最活跃的 4,000 名用户以控制体积；"
    "Book-Crossing 用作大规模对照，经过“用户至少 5 条评分”过滤后仍有 2.2 万用户与 25.7 万物品，"
    "稀疏度高达 99.984%，用于观察长尾与规模对算法的影响。"
)
table(
    "三个数据集的统计特征",
    ["数据集", "领域", "用户数", "物品数", "交互数", "稀疏度", "评分范围"],
    [
        ["MovieLens", "电影", "610", "9,724", "100,836", "98.300%", "0.5–5.0"],
        ["Goodbooks-10k", "图书", "53,424", "10,000", "5,976,479", "98.881%", "1.0–5.0"],
        ["Book-Crossing", "图书", "22,593", "257,815", "929,723", "99.984%", "1.0–10.0"],
    ],
    widths=[3.4, 1.7, 2.6, 2.6, 2.9, 2.4, 2.2], font_size=9,
)
fig(C.FIGURES / "02_dataset_stats.png", "三个数据集的规模对比（对数坐标）", 14.6)
para(
    "图 8 进一步给出三个数据集的物品长尾分布。MovieLens 的基尼系数约为 0.78，前 1% 物品贡献了"
    "约 28% 的交互；Goodbooks 与 Book-Crossing 的长尾更严重，前 1% 物品分别贡献约 24% 与 35% 的"
    "交互。长尾意味着热门榜能获得不低的 HitRate，但也意味着大量物品永远得不到曝光，这正是需要"
    "内容召回、MMR 重排与多样性指标的原因。"
)
fig(C.FIGURES / "03_long_tail.png", "三个数据集的物品交互长尾分布", 14.8)

heading("（二）实验设置与评价指标", 2)
para(
    "所有模型使用同一份 MovieLens 交互表，按用户分组、按时间排序后以 8:1:1 切分为训练/验证/测试。"
    "训练采用均匀负采样（每正样本 1 负），最多 60 轮，验证集 NDCG@10 连续 10 轮不提升则早停，"
    "随机种子固定为 2026。评测采用全排序 Top-10，报告 Recall、Precision、NDCG、MRR、Hit 与 MAP。"
    "各指标定义如下："
)
formula("Recall@K = |Rel_u ∩ TopK(u)| / |Rel_u|")
formula("Precision@K = |Rel_u ∩ TopK(u)| / K")
formula("NDCG@K = DCG@K / IDCG@K,   DCG@K = Σ_{r=1}^{K} rel_r / log₂(r+1)")
formula("MRR@K = 1 / rank(first relevant item),   MAP@K = (1/|Rel_u|) Σ_{r=1}^{K} P(r)·rel_r")
para(
    "其中 Rel_u 为用户 u 在测试集中的真实交互集合，rel_r 为第 r 位的相关性（0/1），P(r) 为前 r 位"
    "的准确率。NDCG 对位置敏感，是本文的主排序指标；Recall 衡量覆盖率；MRR 关注第一个命中位置的"
    "倒数；MAP 同时考虑多个命中的位置。"
)
table(
    "各模型的训练配置",
    ["模型", "类型", "关键超参", "训练轮数"],
    [
        ["Random", "非学习基线", "—", "1"],
        ["Pop", "非学习基线", "贝叶斯平滑热度", "1"],
        ["ItemKNN", "物品协同过滤", "k=20", "1"],
        ["BPR", "成对排序", "隐因子 64", "60"],
        ["NeuMF", "神经协同过滤", "embedding=64", "60"],
        ["LightGCN", "图卷积", "embedding=64, layers=3", "60"],
        ["SGL", "自监督图卷积", "embedding=64, layers=3", "60"],
        ["NCL", "邻域对比图卷积", "embedding=64, layers=3", "60"],
        ["DGCF", "解耦图卷积", "embedding=64, layers=3", "60"],
        ["EASE", "线性自编码器", "reg_weight=250", "1"],
        ["FREEDOM", "多视图融合（本文）", "embedding=64, layers=3, align=0.15", "60"],
    ],
    widths=[2.6, 4.5, 6.8, 2.2], font_size=9,
)

heading("（三）基准模型对比结果", 2)
para(
    "11 个模型在 MovieLens 测试集上的结果如表 8 与图 9 所示，按 NDCG@10 降序排列。"
)
res_rows = []
for r in rows:
    t = r["test"]
    res_rows.append([
        r["model"],
        f"{t.get('recall@10', 0):.4f}",
        f"{t.get('precision@10', 0):.4f}",
        f"{t.get('ndcg@10', 0):.4f}",
        f"{t.get('mrr@10', 0):.4f}",
        f"{t.get('map@10', 0):.4f}",
        f"{t.get('hit@10', 0):.4f}",
        f"{r.get('train_seconds', 0):,.0f}",
    ])
table(
    "MovieLens 全排序评测结果（Top-10，按 NDCG@10 降序）",
    ["模型", "Recall", "Precision", "NDCG", "MRR", "MAP", "Hit", "耗时(s)"],
    res_rows,
    widths=[2.4, 1.9, 2.0, 1.9, 1.9, 1.9, 1.8, 2.2], font_size=9,
)
fig(C.FIGURES / "01_benchmark_ndcg.png", "MovieLens 各模型 NDCG@10 对比", 14.8)

heading("（四）结果分析", 2)
para(
    "第一，EASE 取得最佳效果（NDCG@10=0.0688，Recall@10=0.0602，MRR@10=0.1267）。EASE 的优势"
    "来自闭式解与强正则：在 610 个用户、9,724 个物品、稀疏度 98.3% 的数据上，低秩线性模型不容易"
    "过拟合，且直接优化物品间的全局相似度；相比之下，神经模型需要大量交互才能学到稳定表征。EASE "
    "的代价是一次 9,724×9,724 矩阵求逆，训练耗时 14,588 秒（约 4 小时），但在线推理只需一次矩阵"
    "乘法，完美契合“离线贵、在线快”的架构。"
)
para(
    "第二，ItemKNN 与 BPR 构成性价比最高的两条基线。ItemKNN 的 NDCG@10 为 0.0628，训练 130 秒；"
    "BPR 为 0.0576，训练仅 24 秒。ItemKNN 说明在稀疏数据中共现信号仍然很强；BPR 说明成对排序目标"
    "在隐式反馈上非常高效。若线上预算有限，BPR 或 ItemKNN 是比复杂图模型更稳妥的选择。"
)
para(
    "第三，图神经网络整体未超过线性/协同基线。LightGCN 为 0.0416，DGCF 为 0.0413，SGL 仅 0.0189，"
    "NCL 为 0.0580。原因主要有三点：其一，数据规模小，610 个用户的二部图很容易在 3 层传播后过平滑，"
    "用户表示趋于相似；其二，均匀负采样与固定 60 轮的训练预算对对比学习模型不友好，SGL 的增广强度"
    "和温度需要更细的网格搜索，否则对比项会压过 BPR 主损失；其三，DGCF 的意图解耦需要更多数据才能"
    "学到有意义的通道，否则容易退化为普通图卷积。NCL 在把 faiss 聚类替换为 sklearn KMeans 后可以"
    "正常运行，NDCG 达到 0.0580，但 6,353 秒的训练耗时使其性价比明显低于 BPR。"
)
para(
    "第四，本文实现的 FREEDOM 为 0.0390，低于 EASE、ItemKNN、BPR、NeuMF 与 NCL，但仍高于 SGL 与"
    "Random。这个结果并不意外，原因可以从三个方面解释。其一是内容视图权重过高：训练后的门控"
    "softmax 为 [0.480, 0.520]，尺度为 [1.046, 4.165]，有效贡献约为协同 18.8%、内容 81.2%。内容"
    "视图的用户表示是交互物品内容的平均，容易把细粒度偏好抹平，导致模型更像一个内容推荐器。其二，"
    "本文没有实现原文的图像模态、图剪枝与多层门控，内容图仅由 TF-IDF、类别与数值特征构成，"
    "信息量弱于原文的多模态特征。其三，MovieLens 的物品内容以题材和标题为主，同题材内部差异很大，"
    "内容相似度噪声较高，内容图传播反而可能引入错误邻居。该结果提醒我们：多视图融合不是“加了内容"
    "就一定更好”，视图质量、融合方式和数据规模共同决定收益。"
)
para(
    "第五，Pop 的 NDCG@10 为 0.0437，超过 LightGCN、DGCF、FREEDOM 与 SGL。这不是说热度推荐更好，"
    "而是说明在强长尾、稀疏交互的数据上，热门物品本身就有较高的命中概率；同时也暴露了全排序评测"
    "对流行度偏置的敏感性。Random 的 NDCG@10 仅 0.0020，验证了评测流程没有泄漏，指标量级合理。"
)

heading("（五）训练效率分析", 2)
para(
    "图 10 给出训练耗时与 NDCG@10 的关系，绿色虚线为 5 分钟预算线。BPR（24 秒）、Pop（30 秒）、"
    "ItemKNN（130 秒）、LightGCN（139 秒）、FREEDOM（158 秒）都在预算线内；EASE（14,588 秒）、"
    "NCL（6,353 秒）、DGCF（3,644 秒）则远超预算。若以“单位时间收益”衡量，BPR 在 24 秒内达到"
    "0.0576，是最划算的模型；EASE 虽然最准，但训练成本是 BPR 的 600 倍，适合离线批量更新而不是"
    "频繁重训。FREEDOM 的训练时间控制得较好（158 秒），说明全批训练器的工程优化有效，但其精度"
    "尚未达到预期，后续应优先调整融合权重与内容图质量，而不是继续堆训练轮数。"
)
fig(C.FIGURES / "07_time_quality.png", "训练耗时与 NDCG@10 的关系", 14.6)

heading("（六）FREEDOM 融合权重与训练过程", 2)
para(
    "图 11 展示了 FREEDOM 训练结束后的融合权重。门控 softmax 为 [0.480, 0.520]，两个视图看起来"
    "接近；但尺度 exp(log_scale) 为 [1.046, 4.165]，内容视图的尺度是协同视图的约 4 倍，因此有效"
    "贡献为协同 18.8%、内容 81.2%。这说明模型在训练中把大部分决策权交给了内容视图。结合 5.4 节的"
    "分析，内容视图的表示过于平滑，是 FREEDOM 精度受损的直接原因。改进方向包括：给融合尺度加"
    "更强的正则、对内容视图做 dropout、在验证集上约束内容权重上限，或直接改用“协同为主、内容为辅”"
    "的固定权重。"
)
fig(C.FIGURES / "05_freedom_fusion.png", "FREEDOM 自适应融合权重", 12.8)
para(
    "图 12 对比了 LightGCN 与 FREEDOM 的训练损失与验证 NDCG。两者都在前 10 轮快速下降，随后进入"
    "平台；FREEDOM 的验证 NDCG 在约 0.055 附近波动，明显低于 EASE/ItemKNN 的 0.08 量级。训练损失"
    "持续下降而验证指标不再提升，说明模型开始过拟合训练集的成对排序信号。早停机制在验证指标连续"
    "10 轮不提升后终止训练，避免了更严重的过拟合。"
)
fig(C.FIGURES / "04_training_curves.png", "LightGCN 与 FREEDOM 的训练过程", 14.8)

heading("（七）多源融合推荐评测", 2)
para(
    "为验证线上 hybrid 的实际收益，本文使用与基准相同的时间序切分，对 EASE、ItemKNN、BPR、NeuMF、"
    "LightGCN、FREEDOM 六个模型的测试集全量打分矩阵，叠加内容画像与热度两路信号，逐用户做 z-score "
    "后按验证集搜索的权重融合，再在测试集上评测。需要说明的是，该脚本对历史屏蔽与 PAD 的处理比 "
    "RecBole 官方 evaluator 更严格，单模型数值与表 8 存在小幅差异（例如 EASE 为 0.0726 而非 0.0688），"
    "因此表 9 只在同一脚本内部做相对比较，不与表 8 的绝对值直接混用。"
)
if hybrid:
    w = hybrid["weights"]
    table(
        "多源融合权重（验证集随机搜索 + 坐标下降）",
        ["信号", "权重", "信号", "权重"],
        [
            ["EASE", f"{w.get('EASE', 0):.4f}", "FREEDOM", f"{w.get('FREEDOM', 0):.4f}"],
            ["ItemKNN", f"{w.get('ItemKNN', 0):.4f}", "Content", f"{w.get('Content', 0):.4f}"],
            ["BPR", f"{w.get('BPR', 0):.4f}", "Popularity", f"{w.get('Popularity', 0):.4f}"],
            ["NeuMF", f"{w.get('NeuMF', 0):.4f}", "LightGCN", f"{w.get('LightGCN', 0):.4f}"],
        ],
        widths=[3.0, 3.0, 3.0, 3.0], font_size=9.5,
    )
    ft = hybrid["fusion_test"]
    ease = hybrid["single"]["EASE"]["test"]
    ndcg_gain = (ft["ndcg@10"] / ease["ndcg@10"] - 1) * 100
    recall_gain = (ft["recall@10"] / ease["recall@10"] - 1) * 100
    mrr_gain = (ft["mrr@10"] / ease["mrr@10"] - 1) * 100
    para(
        f"融合后的测试集指标为 NDCG@10={ft['ndcg@10']:.4f}、Recall@10={ft['recall@10']:.4f}、"
        f"MRR@10={ft['mrr@10']:.4f}、Hit@10={ft['hit@10']:.4f}。与同一脚本下最强的单模型 EASE 相比，"
        f"NDCG@10 提升 {ndcg_gain:.1f}%，Recall@10 提升 {recall_gain:.1f}%，MRR@10 提升 {mrr_gain:.1f}%。"
        "权重分布也提供了有价值的信息：内容画像获得最高权重 0.4517，说明在稀疏数据上内容信号确实是"
        "协同信号的有效补充；NeuMF 与 ItemKNN 分别获得 0.1966 与 0.1121，EASE 为 0.0939；"
        "LightGCN 仅 0.001，说明其分数在当前数据上与融合目标几乎正交。需要强调的是，融合权重是在"
        "验证集上搜索得到的，测试集只用于最终报告，不存在测试集调参；但权重对验证集规模仍有一定"
        "敏感性，后续应使用交叉验证或更多用户做稳健性检验。"
    )
else:
    para("融合评测脚本尚未运行，相关结果在补齐 experiments/results/hybrid_eval.json 后自动生成。")

heading("（八）多样性与 MMR 重排", 2)
para(
    "为评估 MMR 的作用，本文在 MovieLens 的 120 名用户与 Goodbooks 的 60 名用户上，对 hybrid 的"
    "60 个候选做 60 选 20 的重排（λ=0.6），统计列表内平均相似度、最大单一题材占比、Top-20 题材"
    "覆盖数与归一化相关性保留率。结果如表 10 与图 13 所示。"
)
m = mmr["movielens"]
b = mmr["goodbooks"]
table(
    "MMR 重排前后的多样性指标",
    ["数据集", "指标", "重排前", "重排后", "变化"],
    [
        ["MovieLens", "列表内平均相似度", f"{m['intra_sim_before']:.3f}", f"{m['intra_sim_after']:.3f}",
         f"{(m['intra_sim_after'] / m['intra_sim_before'] - 1) * 100:+.1f}%"],
        ["MovieLens", "最大单一题材占比", f"{m['dominant_share_before'] * 100:.1f}%",
         f"{m['dominant_share_after'] * 100:.1f}%",
         f"{(m['dominant_share_after'] / m['dominant_share_before'] - 1) * 100:+.1f}%"],
        ["MovieLens", "Top-20 覆盖题材数", f"{m['genre_coverage_before']:.1f}",
         f"{m['genre_coverage_after']:.1f}",
         f"{(m['genre_coverage_after'] / m['genre_coverage_before'] - 1) * 100:+.1f}%"],
        ["MovieLens", "归一化相关性", f"{m['relevance_before']:.3f}", f"{m['relevance_after']:.3f}",
         f"{m['relevance_retention'] * 100:.1f}% 保留"],
        ["Goodbooks", "列表内平均相似度", f"{b['intra_sim_before']:.3f}", f"{b['intra_sim_after']:.3f}",
         f"{(b['intra_sim_after'] / b['intra_sim_before'] - 1) * 100:+.1f}%"],
        ["Goodbooks", "Top-20 覆盖题材数", f"{b['genre_coverage_before']:.1f}",
         f"{b['genre_coverage_after']:.1f}",
         f"{(b['genre_coverage_after'] / b['genre_coverage_before'] - 1) * 100:+.1f}%"],
        ["Goodbooks", "归一化相关性", f"{b['relevance_before']:.3f}", f"{b['relevance_after']:.3f}",
         f"{b['relevance_retention'] * 100:.1f}% 保留"],
    ],
    widths=[2.8, 4.8, 2.8, 2.8, 3.0], font_size=8.8, align_first_left=True,
)
para(
    "MovieLens 上，列表内平均相似度从 0.826 降到 0.818（−1.0%），最大单一题材占比从 52.8% 降到"
    "48.2%（−8.6%），Top-20 覆盖题材数从 14.3 升到 15.2（+6.4%），而归一化相关性保留 97.9%。"
    "这说明 MMR 用不到 2.1% 的相关性代价换来了明显的题材多样性，尤其是“单一题材刷屏”问题得到"
    "缓解。Goodbooks 上相似度仅从 0.749 降到 0.743，覆盖率从 60.0 升到 63.7，相关性保留 99.0%；"
    "由于图书的 genres 字段是整段标签串而非按“|”切分的类别，最大单一题材占比恒为 100%，该指标"
    "在图书域不具解释力，后续应先把标签拆分为独立 token 再统计。"
)
fig(C.FIGURES / "06_mmr_diversity.png", "MMR 重排前后的推荐多样性", 15.4)

heading("（九）大模型重排与理由生成", 2)
para(
    "本文使用本地 Qwen2.5-0.5B-Instruct 做了一次小规模演示：加载模型 34.3 秒，为 2 名用户各生成"
    "3 条推荐理由，并对 6 个候选做重排。CPU 上单条理由生成耗时 5.0–13.3 秒，重排 6 个候选耗时"
    "3.6–4.1 秒。表 11 给出部分样例。"
)
llm_rows = []
for s in llm.get("samples", [])[:5]:
    reason = s["llm_reason"].replace("\n", " ")[:60]
    tmpl = s["template_reason"].replace("\n", " ")[:40]
    llm_rows.append([str(s["user_id"]), s["title"][:34], reason, tmpl, f"{s['latency_s']:.2f}"])
table(
    "本地大模型推荐理由生成样例",
    ["用户", "推荐物品", "LLM 理由（节选）", "模板理由（节选）", "延迟(s)"],
    llm_rows,
    widths=[1.3, 4.5, 6.2, 4.2, 1.5], font_size=8.2, align_first_left=True,
)
para(
    "从样例看，0.5B 模型能够生成通顺的理由，但也出现了明显幻觉：例如把《海底城》说成“由詹姆斯·"
    "卡梅隆执导、杰森·斯坦森主演”，与事实不符；部分理由只是复述标题与题材，信息增益有限。因此"
    "本文的在线主链路仍然使用模板理由，大模型仅作为离线演示与可选增强。若要在生产中使用，需要"
    "更大的模型、结构化事实约束（如把导演、演员、年份作为不可修改字段）以及人工审核或事实校验。"
    "这也说明“大模型 + 推荐”并不是简单替换文案，而是需要一整套可信生成与评测体系。"
)

heading("（十）案例分析", 2)
para(
    "回到 3.5 节的用户 1。该用户的历史评分全部为 5 分，题材集中在动作、冒险、剧情与战争，属于"
    "“高偏好、窄题材”用户。hybrid 推荐的前 8 名中，动作/冒险类占 6 席，剧情类 2 席，与历史画像"
    "一致；同时列表中没有出现用户已看过的 12 部作品，说明历史过滤生效。第 3 名《肖申克的救赎》"
    "是唯一的纯剧情片，其入选依赖协同信号与高评分，而不是题材硬匹配，这体现了多路融合的价值。"
    "从 MMR 角度看，前 8 名覆盖动作、冒险、犯罪、剧情、科幻、动画、喜剧 7 种题材，没有出现"
    "《指环王》三部曲连续霸榜的情况，说明重排层在真实请求中确实起了作用。"
)
para(
    "再看图书域用户 7。其历史集中在科幻与反乌托邦，系统推荐的前 6 名全部命中科幻/奇幻，且覆盖"
    "《安德的游戏》《银河系漫游指南》《基地》《饥饿游戏》《火星编年史》《使女的故事》等不同子类型，"
    "既有硬科幻也有反乌托邦青少年小说。这说明内容画像能够捕捉“科幻”这一上层题材下的细粒度差异，"
    "而热度与协同信号则负责把同题材中更受欢迎的作品排到前面。两个案例共同说明：推荐结果的可解释性"
    "不仅来自理由文案，更来自“历史—画像—候选—排序”的可追溯链路。"
)

heading("（十一）局限与改进方向", 2)
para("本系统仍存在以下局限，需要在后续工作中改进：")
bullet("数据规模与算力受限。MovieLens 只有 610 名用户，深度图模型容易过平滑；Book-Crossing 虽然"
       "规模大，但噪声重、缺少时间戳，本文只做了最小清洗。后续可在更大规模、带真实时间戳的数据上"
       "复验结论。")
bullet("FREEDOM 为简化实现。未纳入图像模态、图剪枝、多层自适应门控与模态内对比，内容图仅由文本、"
       "类别与数值特征构成；融合权重偏向内容视图，导致精度低于强基线。后续应引入封面/海报图像、"
       "对内容图做去噪与剪枝，并在验证集上约束融合权重。")
bullet("超参搜索不充分。SGL、DGCF 等对比学习模型对增广强度、温度、层数与负采样策略敏感，本文"
       "统一使用 60 轮与固定超参，未做逐模型网格搜索，因而不能据此断言这些模型在本数据上必然弱。")
bullet("评测以准确性为主。虽然加入了 MMR 多样性与 LLM 理由，但尚未实现在线 A/B 测试、用户满意度"
       "与长期留存评估；feedback_log 已预留行为日志表，后续可接入点击/点赞数据做增量训练。")
bullet("静态镜像与动态站点存在数据同步成本。每次重跑实验都需要重新构建 site/ 并同步 JSON；后续"
       "可以把构建流程接入 GitHub Actions，做到提交即部署。")

heading("（十二）本章小结", 2)
para(
    "本章在统一数据切分与评测口径下比较了 11 个模型，得到“EASE 最准、BPR 最划算、图模型受限于"
    "数据规模、FREEDOM 内容视图过强”的结论；随后从训练效率、融合权重、训练曲线、MMR 多样性、"
    "大模型理由与两个真实案例六个角度展开分析，并给出局限与改进方向。实验结果既验证了系统的"
    "工程完整性，也暴露了多视图融合在小规模数据上的真实困难。"
)

# ------------------------------------------------------------------ 6 结论
heading("六、结论", 1)
para(
    "本文围绕电影与图书两个应用域，设计并实现了一个从数据 ETL、特征工程、模型训练与评测，到"
    "离线预计算、在线服务、多样性重排与静态部署的完整推荐系统。系统以 RecBole 为算法底座，"
    "统一了 11 个模型的训练与全排序评测口径；以多视图内容特征和内容相似图为补充，解决了冷启动"
    "与长尾覆盖；以“离线预计算 + 在线查表 + 内容/热度兜底”的分层架构，在单台 CPU 服务器上实现了"
    "毫秒级推荐；以 MMR 重排和模板/大模型理由，提升了列表多样性与可解释性。"
)
para(
    "实验结果表明：在 MovieLens 的 8:1:1 时间序切分与 Top-10 全排序协议下，EASE 的 NDCG@10 最高"
    "（0.0688），ItemKNN（0.0628）与 BPR（0.0576）次之；BPR 仅需 24 秒训练，是性价比最高的模型；"
    "LightGCN、DGCF、SGL 等图模型受数据规模与超参影响，未超过强基线；本文实现的 FREEDOM 为"
    "0.0390，融合权重分析显示内容视图贡献约 81.2%，是精度受损的主要原因。多源融合在自定义同口径"
    "评测中取得 NDCG@10=0.0764、Recall@10=0.0672，较同脚本下最强的单模型 EASE 分别提升 5.2% 与"
    "8.6%。MMR 在保留 97.9% 相关性"
    "的同时，使最大单一题材占比下降 8.6%、题材覆盖提升 6.4%，验证了重排层的实际价值。"
)
para(
    "本文的主要收获有三点。其一，推荐系统的效果不仅取决于模型复杂度，更取决于数据规模、切分"
    "方式、负采样与评测口径；脱离统一口径的“模型对比”没有意义。其二，离线指标与在线体验之间"
    "存在差距，多样性、可解释性与响应延迟同样重要，工程上需要通过重排、兜底与缓存来平衡。其三，"
    "多视图融合需要尊重视图质量：内容视图在元数据丰富、图像质量高的场景可能有效，但在本文的"
    "文本/类别特征上反而会稀释协同信号。"
)
para(
    "后续工作将从四个方向展开：引入图像模态与图去噪，完善 FREEDOM 的实现；在更大规模数据上做"
    "逐模型超参搜索，给出更公平的模型排序；接入在线反馈日志，实现在线 A/B 测试与增量训练；把"
    "实验、构建与部署接入 CI/CD，进一步降低复现与运维成本。"
)

# ------------------------------------------------------------------ 参考文献
page_break()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(8)
r = p.add_run("参考文献")
set_run_font(r, "黑体", 14, bold=True)

refs = [
    "[1] 项亮. 推荐系统实践[M]. 北京: 人民邮电出版社, 2012: 1-200.",
    "[2] 李航. 统计学习方法[M]. 2版. 北京: 清华大学出版社, 2019: 1-460.",
    "[3] 王喆. 深度学习推荐系统[M]. 北京: 电子工业出版社, 2020: 1-350.",
    "[4] RENDLE S, FREUDENTHALER C, GANTNER Z, et al. BPR: Bayesian personalized ranking from "
    "implicit feedback[C]//Proceedings of the 25th Conference on Uncertainty in Artificial "
    "Intelligence. Montreal: AUAI Press, 2009: 452-461.",
    "[5] HE X, LIAO L, ZHANG H, et al. Neural collaborative filtering[C]//Proceedings of the 26th "
    "International Conference on World Wide Web. Perth: ACM, 2017: 173-182.",
    "[6] HE X, DENG K, WANG X, et al. LightGCN: simplifying and powering graph convolution network "
    "for recommendation[C]//Proceedings of the 43rd International ACM SIGIR Conference on Research "
    "and Development in Information Retrieval. Xi'an: ACM, 2020: 639-648.",
    "[7] WU J, WANG X, FENG F, et al. Self-supervised graph learning for recommendation[C]//"
    "Proceedings of the 44th International ACM SIGIR Conference on Research and Development in "
    "Information Retrieval. 2021: 726-735.",
    "[8] LIN Z, TIAN C, HOU Y, et al. Improving graph collaborative filtering with neighborhood-"
    "enriched contrastive learning[C]//Proceedings of the ACM Web Conference 2022. 2022: 2320-2329.",
    "[9] WANG X, JIN H, ZHANG A, et al. Disentangled graph collaborative filtering[C]//Proceedings "
    "of the 43rd International ACM SIGIR Conference on Research and Development in Information "
    "Retrieval. 2020: 1001-1010.",
    "[10] ZHOU X, SHEN Z. A tale of two graphs: freezing and denoising graph structures for "
    "multimodal recommendation[C]//Proceedings of the 31st ACM International Conference on "
    "Multimedia. Ottawa: ACM, 2023: 935-943.",
    "[11] STECK H. Embarrassingly shallow autoencoders for sparse data[C]//Proceedings of the World "
    "Wide Web Conference. San Francisco: ACM, 2019: 3251-3257.",
    "[12] SARWAR B, KARYPIS G, KONSTAN J, et al. Item-based collaborative filtering recommendation "
    "algorithms[C]//Proceedings of the 10th International Conference on World Wide Web. Hong Kong: "
    "ACM, 2001: 285-295.",
    "[13] CARBONELL J, GOLDSTEIN J. The use of MMR, diversity-based reranking for reordering "
    "documents and producing summaries[C]//Proceedings of the 21st Annual International ACM SIGIR "
    "Conference on Research and Development in Information Retrieval. Melbourne: ACM, 1998: 335-336.",
    "[14] ZHAO W X, MU S, HOU Y, et al. RecBole: towards a unified, comprehensive and efficient "
    "framework for recommendation algorithms[C]//Proceedings of the 30th ACM International "
    "Conference on Information & Knowledge Management. 2021: 4653-4664.",
    "[15] GAO C, ZHENG Y, LI N, et al. Graph neural networks for recommender systems: challenges, "
    "methods, and directions[J]. ACM Transactions on Recommender Systems, 2023, 1(1): 1-51.",
    "[16] YU J, YIN H, XIA X, et al. Self-supervised learning for recommender systems: a survey[J]. "
    "IEEE Transactions on Knowledge and Data Engineering, 2024, 36(1): 335-355.",
    "[17] WU L, ZHENG Z, QIU Z, et al. A survey on large language models for recommendation[J]. "
    "World Wide Web, 2024, 27(5): 60.",
    "[18] ZHAO Z, FAN W, LI J, et al. Recommender systems in the era of large language models "
    "(LLMs)[J]. IEEE Transactions on Knowledge and Data Engineering, 2024, 36(11): 6889-6907.",
    "[19] HARPER F M, KONSTAN J A. The MovieLens datasets: history and context[J]. ACM Transactions "
    "on Interactive Intelligent Systems, 2015, 5(4): 1-19.",
]
for ref in refs:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(20)
    p.paragraph_format.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(ref)
    set_run_font(r, "仿宋", 10.5)

# ------------------------------------------------------------------ 附录
page_break()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(8)
r = p.add_run("附录")
set_run_font(r, "黑体", 14, bold=True)

heading("附录 A 主要运行命令", 2)
for cmd in [
    "python -m venv venv",
    r"venv\Scripts\activate",
    "pip install -r requirements.txt",
    "python -m recsys.etl",
    "python scripts/01_build_features.py",
    "python scripts/03_build_db.py",
    "python scripts/02_run_benchmark.py --dataset movielens",
    "python scripts/08_sync_metrics.py --dataset movielens",
    "python scripts/04_generate_recs.py --dataset movielens",
    "python scripts/04_generate_recs.py --dataset goodbooks --models \"\"",
    "python scripts/05_make_figures.py",
    "python scripts/10_build_static.py",
    "python run.py",
]:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(18)
    p.paragraph_format.left_indent = Pt(12)
    r = p.add_run(cmd)
    set_run_font(r, "Consolas", 9.5, ascii_font="Consolas")

heading("附录 B 项目目录结构", 2)
for line in [
    "app/                 Flask 应用（页面、REST API、ORM、推荐服务）",
    "recsys/              ETL、特征工程、统一训练器、融合模型、MMR/LLM",
    "scripts/             01–11 流水线与报告生成脚本",
    "data/raw/            原始数据集",
    "data/processed/      清洗后的交互、物品、特征与相似图",
    "experiments/results/ 基准结果、checkpoint、融合评测、LLM 演示",
    "figures/             报告图表",
    "screenshots/         系统运行截图",
    "site/                Cloudflare Pages 静态镜像",
    "report/              课程设计报告",
    "instance/            SQLite 业务库",
]:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = Pt(18)
    p.paragraph_format.left_indent = Pt(12)
    r = p.add_run(line)
    set_run_font(r, "Consolas", 9.5, ascii_font="Consolas")

heading("附录 C 主要 REST API", 2)
table(
    "主要 REST API 一览",
    ["方法", "路径", "说明"],
    [
        ["GET", "/api/health", "服务健康检查"],
        ["GET", "/api/overview?dataset=", "数据集概览与热门题材"],
        ["GET", "/api/items?dataset=&page=&size=&genre=&q=", "物品分页/筛选"],
        ["GET", "/api/items/<id>?dataset=", "物品详情与相似物品"],
        ["GET", "/api/users?dataset=&limit=", "演示用户列表"],
        ["GET", "/api/history/<uid>?dataset=", "用户真实历史"],
        ["GET", "/api/recommend/<uid>?dataset=&algo=&k=&genre=", "个性化推荐"],
        ["GET", "/api/popular?dataset=&k=&genre=", "热门榜"],
        ["GET", "/api/similar/<id>?dataset=", "相似物品"],
        ["GET", "/api/metrics?dataset=", "算法指标"],
        ["POST", "/api/feedback", "记录点击/浏览反馈"],
    ],
    widths=[1.6, 9.4, 4.5], font_size=9,
)

# 保存
OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(f"[REPORT] 已生成 {OUT}")
print(f"[REPORT] 图 {FIG_NO} 幅，表 {TAB_NO} 张")
