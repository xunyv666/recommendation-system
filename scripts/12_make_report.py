# -*- coding: utf-8 -*-
"""生成课程设计报告 docx，并调用 Word COM 转成 .doc。

格式依据《南京财经大学本科毕业论文（设计）规范化要求》：
  - A4，上/下 2.5 cm，左 3.0 cm，右 2.0 cm
  - 正文小四仿宋，固定行距 28 磅，首行缩进 2 字符
  - 题目二号黑体，一级标题四号黑体
  - 摘要、参考文献五号仿宋
  - 页眉右对齐“南京财经大学本科毕业论文（设计）”五号仿宋
  - 页脚居中页码
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ------------------------------------------------------------------ 基本信息
STUDENT_ID = os.environ.get("STUDENT_ID", "2020601616")
STUDENT_NAME = os.environ.get("STUDENT_NAME", "________")
ADVISOR = os.environ.get("ADVISOR", "________")
MAJOR = os.environ.get("MAJOR", "计算机科学与技术")
COLLEGE = os.environ.get("COLLEGE", "信息工程学院")
DATE = os.environ.get("REPORT_DATE", "2026 年 11 月")

TITLE = "融合多视图与大模型重排的双域推荐系统"
TITLE_EN = ("Design and Implementation of a Dual-Domain Recommender System "
            "Fusing Multi-View Features and LLM Reranking")

REPORT_DIR = ROOT / "report"
REPORT_DIR.mkdir(exist_ok=True)
DOCX_PATH = REPORT_DIR / f"{STUDENT_ID}.docx"
DOC_PATH = REPORT_DIR / f"{STUDENT_ID}.doc"
PDF_PATH = REPORT_DIR / f"{STUDENT_ID}.pdf"

# ------------------------------------------------------------------ 内容与数据
spec = importlib.util.spec_from_file_location("report_content", ROOT / "scripts" / "report_content.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)
BLOCKS = rc.BLOCKS

hyb = json.loads((ROOT / "experiments" / "results" / "hybrid_eval.json")
                 .read_text(encoding="utf-8"))
eq = hyb.get("fusion_equal", {})
eq_test = eq.get("test", hyb["fusion_test"])
eq_valid = eq.get("valid", {})
ease_test = hyb["single"]["EASE"]["test"]
gain = (eq_test["ndcg@10"] / ease_test["ndcg@10"] - 1) * 100
TOKENS = {
    "[[FUSION_NDCG]]": f"{eq_test['ndcg@10']:.4f}",
    "[[FUSION_NDCG_EN]]": f"{eq_test['ndcg@10']:.4f}",
    "[[FUSION_RECALL]]": f"{eq_test['recall@10']:.4f}",
    "[[FUSION_MRR]]": f"{eq_test['mrr@10']:.4f}",
    "[[FUSION_GAIN]]": f"+{gain:.1f}%",
    "[[EQ_VALID]]": f"{eq_valid.get('ndcg@10', 0):.4f}",
    "[[W_EASE]]": "0.2500",
    "[[W_ITEMKNN]]": "0.2500",
    "[[W_NEUMF]]": "0.2500",
    "[[W_CONTENT]]": "0.2500",
}


def fill(text: str) -> str:
    for k, v in TOKENS.items():
        text = text.replace(k, v)
    return text


# ------------------------------------------------------------------ 字体工具
def set_run_font(run, size_pt: float, east="仿宋", latin="Times New Roman",
                 bold: bool = False, color=None):
    run.font.name = latin
    run.font.size = Pt(size_pt)
    run.bold = bold
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), latin)
    rFonts.set(qn("w:hAnsi"), latin)
    rFonts.set(qn("w:eastAsia"), east)
    if color:
        run.font.color.rgb = color


def style_paragraph(p, first_indent=True, line=28, before=0, after=0,
                    align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    pf = p.paragraph_format
    pf.line_spacing = Pt(line)
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.alignment = align
    pf.first_line_indent = Pt(24) if first_indent else Pt(0)


def add_body(doc, text, size=12, first=True):
    p = doc.add_paragraph()
    style_paragraph(p, first_indent=first)
    run = p.add_run(fill(text))
    set_run_font(run, size)
    return p


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = Pt(28)
    pf.keep_with_next = True
    if level == 1:
        pf.page_break_before = True
        pf.space_before = Pt(6)
        pf.space_after = Pt(12)
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(fill(text))
        set_run_font(run, 14, east="黑体", bold=True)
    else:
        pf.space_before = Pt(8)
        pf.space_after = Pt(4)
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(fill(text))
        set_run_font(run, 12, east="黑体", bold=True)
    # 让 Word 的目录识别标题层级
    pPr = p._p.get_or_add_pPr()
    outline = OxmlElement("w:outlineLvl")
    outline.set(qn("w:val"), str(level - 1))
    pPr.append(outline)
    return p


def add_center(doc, text):
    p = doc.add_paragraph()
    style_paragraph(p, first_indent=False, align=WD_ALIGN_PARAGRAPH.CENTER)
    run = p.add_run(fill(text))
    set_run_font(run, 12)
    return p


def add_caption(doc, text, above=False):
    p = doc.add_paragraph()
    style_paragraph(p, first_indent=False, before=6 if above else 2,
                    after=2 if above else 6,
                    align=WD_ALIGN_PARAGRAPH.CENTER)
    run = p.add_run(fill(text))
    set_run_font(run, 10.5, east="宋体")
    return p


def crop_top(path: Path, bottom: int) -> Path:
    """截取整页长截图的上部，避免一张图占满整页、正文被挤成大段空白。"""
    out_dir = REPORT_DIR / "_figs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{path.stem}_top{bottom}.png"
    from PIL import Image
    with Image.open(path) as im:
        im.crop((0, 0, im.width, min(bottom, im.height))).save(out)
    return out


CROP_TOP = {
    "01_home_movie.png": 1360,
    "02_recommend_movie.png": 1650,
    "04_home_book.png": 1450,
    "05_recommend_book.png": 1650,
    "07_about.png": 1050,
}


def add_figure(doc, path: Path, caption: str, width_cm: float):
    if not path.exists():
        add_body(doc, f"[缺图：{path.name}]", size=10.5, first=False)
        return
    if path.name in CROP_TOP:
        path = crop_top(path, CROP_TOP[path.name])
    p = doc.add_paragraph()
    style_paragraph(p, first_indent=False, before=6, after=2,
                    align=WD_ALIGN_PARAGRAPH.CENTER)
    # 图片段落必须使用单倍行距：正文的“固定值 28 磅”会把内嵌图片
    # 裁剪成一条细线，只显示图片顶部的一小条。
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    # 高图按高度限制，避免跨页
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    ratio = h / max(w, 1)
    if ratio > 1.2:
        run.add_picture(str(path), height=Cm(19.0))
    else:
        run.add_picture(str(path), width=Cm(width_cm))
    add_caption(doc, caption, above=False)


def shade_cell(cell, color="EDF1F7"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def set_cell_margins(table, top=40, bottom=40, left=80, right=80):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for tag, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tblPr.append(mar)


def add_table(doc, caption: str, header, rows, widths):
    cap = add_caption(doc, caption, above=True)
    cap.paragraph_format.keep_with_next = True
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_cell_margins(table)
    # 跨页时重复表头，避免续表没有列名
    trPr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    trPr.append(tbl_header)
    for i, text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing = Pt(20)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(fill(str(text)))
        set_run_font(run, 10.5, east="黑体", bold=True)
        shade_cell(cell, "E8EDF5")
    for row in rows:
        tr = table.add_row()
        row_pr = tr._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        row_pr.append(cant_split)
        cells = tr.cells
        for i, text in enumerate(row):
            cell = cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = (WD_ALIGN_PARAGRAPH.LEFT if i == len(row) - 1
                           else WD_ALIGN_PARAGRAPH.CENTER)
            p.paragraph_format.line_spacing = Pt(20)
            run = p.add_run(fill(str(text)))
            set_run_font(run, 10.5, east="宋体")
    for i, w in enumerate(widths):
        for row in table.rows:
            row.cells[i].width = Cm(w)
    # 表后空一行，避免与正文粘连
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(6)
    return table


def add_code(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = Pt(14)
    pf.space_before = Pt(4)
    pf.space_after = Pt(6)
    pf.left_indent = Cm(0.4)
    run = p.add_run(text)
    set_run_font(run, 9, east="宋体", latin="Consolas")
    return p


# ------------------------------------------------------------------ 页眉页脚
def add_page_field(paragraph):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t")
    txt.text = "1"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(txt)
    run._r.append(fld_end)
    set_run_font(run, 10.5)


def add_header_border(paragraph):
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "999999")
    pBdr.append(bottom)
    pPr.append(pBdr)


def setup_page(doc):
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    sec.left_margin = Cm(3.0)
    sec.right_margin = Cm(2.0)
    sec.header_distance = Cm(1.4)
    sec.footer_distance = Cm(1.4)
    sec.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "仿宋")
    normal.paragraph_format.line_spacing = Pt(28)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    # 页眉
    header = sec.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hp.paragraph_format.space_after = Pt(0)
    run = hp.add_run("南京财经大学本科毕业论文（设计）")
    set_run_font(run, 10.5, east="仿宋")
    add_header_border(hp)

    # 页脚页码
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_field(fp)

    # 首页（封面）无页眉页脚
    sec.first_page_header.paragraphs[0].text = ""
    sec.first_page_footer.paragraphs[0].text = ""


# ------------------------------------------------------------------ 封面/目录
def build_cover(doc):
    for _ in range(2):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = Pt(28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("南京财经大学")
    set_run_font(run, 26, east="黑体", bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("本科毕业论文（设计）")
    set_run_font(run, 22, east="黑体", bold=True)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(60)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(TITLE)
    set_run_font(run, 22, east="黑体", bold=True)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(TITLE_EN)
    set_run_font(run, 15, east="Times New Roman", latin="Times New Roman", bold=True)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(70)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("学    院： " + COLLEGE)
    set_run_font(run, 14, east="仿宋")
    for label, value in [("专    业： ", MAJOR), ("姓    名： ", STUDENT_NAME),
                         ("学    号： ", STUDENT_ID), ("指导教师： ", ADVISOR)]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(label + value)
        set_run_font(run, 14, east="仿宋")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(70)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(DATE)
    set_run_font(run, 14, east="仿宋")


def build_toc(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.page_break_before = True
    p.paragraph_format.space_after = Pt(18)
    run = p.add_run("目    录")
    set_run_font(run, 16, east="黑体", bold=True)

    p = doc.add_paragraph()
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-2" \\h \\z \\u '
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t")
    t.text = "右键选择“更新域”生成目录"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(t)
    run._r.append(fld_end)
    set_run_font(run, 12)


# ------------------------------------------------------------------ 参考文献/附录
REFS = [
    "He X, Deng K, Wang X, et al. LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation[C]//Proceedings of the 43rd International ACM SIGIR Conference on Research and Development in Information Retrieval. 2020: 639-648.",
    "Wu J, Wang X, Feng F, et al. Self-supervised Graph Learning for Recommendation[C]//Proceedings of the 44th International ACM SIGIR Conference on Research and Development in Information Retrieval. 2021: 726-735.",
    "Lin Z, Tian C, Hou Y, et al. Improving Graph Collaborative Filtering with Neighborhood-enriched Contrastive Learning[C]//Proceedings of the ACM Web Conference 2022. 2022: 2320-2329.",
    "Wang X, Jin H, Zhang A, et al. Disentangled Graph Collaborative Filtering[C]//Proceedings of the 43rd International ACM SIGIR Conference on Research and Development in Information Retrieval. 2020: 1001-1010.",
    "Steck H. Embarrassingly Shallow Autoencoders for Sparse Data[C]//Proceedings of the World Wide Web Conference. 2019: 3251-3257.",
    "Rendle S, Freudenthaler C, Gantner Z, et al. BPR: Bayesian Personalized Ranking from Implicit Feedback[C]//Proceedings of the 25th Conference on Uncertainty in Artificial Intelligence. 2009: 452-461.",
    "He X, Liao L, Zhang H, et al. Neural Collaborative Filtering[C]//Proceedings of the 26th International Conference on World Wide Web. 2017: 173-182.",
    "Zhou X, Shen Z. A Tale of Two Graphs: Freezing and Denoising Graph Structures for Multimodal Recommendation[C]//Proceedings of the 31st ACM International Conference on Multimedia. 2023. DOI: 10.1145/3581783.3611943.",
    "Carbonell J, Goldstein J. The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries[C]//Proceedings of the 21st Annual International ACM SIGIR Conference on Research and Development in Information Retrieval. 1998: 335-336.",
    "Sarwar B, Karypis G, Konstan J, et al. Item-based Collaborative Filtering Recommendation Algorithms[C]//Proceedings of the 10th International Conference on World Wide Web. 2001: 285-295.",
    "Harper F M, Konstan J A. The MovieLens Datasets: History and Context[J]. ACM Transactions on Interactive Intelligent Systems, 2015, 5(4): 1-19.",
    "Wan M, McAuley J. Item Recommendation on Monotonic Behavior Chains[C]//Proceedings of the 12th ACM Conference on Recommender Systems. 2018: 86-94.",
    "Ziegler C N, McNee S M, Konstan J A, et al. Improving Recommendation Lists Through Topic Diversification[C]//Proceedings of the 14th International Conference on World Wide Web. 2005: 22-32.",
    "Zhao W X, Mu S, Hou Y, et al. RecBole: Towards a Unified, Comprehensive and Efficient Framework for Recommendation Algorithms[C]//Proceedings of the 30th ACM International Conference on Information & Knowledge Management. 2021: 4653-4664.",
    "Hou Y, Zhang J, Lin Z, et al. Large Language Models are Zero-Shot Rankers for Recommender Systems[C]//Proceedings of the 46th European Conference on Information Retrieval. 2024: 364-381.",
    "Ji J, Li Y, Yin S, et al. A Survey on Large Language Models for Recommendation[EB/OL]. arXiv:2305.19860, 2023.",
    "Rajput S, Mehta N, Singh A, et al. Recommender Systems with Generative Retrieval[C]//Advances in Neural Information Processing Systems 36. 2023.",
    "Li J, Wang M, Li J, et al. Text Is All You Need: Learning Language Representations for Sequential Recommendation[C]//Proceedings of the 29th ACM SIGKDD Conference on Knowledge Discovery and Data Mining. 2023: 1258-1267.",
    "Bao K, Zhang J, Wang H, et al. LLMRec: Large Language Models with Graph Augmentation for Recommendation[C]//Proceedings of the 17th ACM International Conference on Web Search and Data Mining. 2024: 806-815.",
    "Lin J, Dai X, Xi Y, et al. How Can Recommender Systems Benefit from Large Language Models: A Survey[EB/OL]. arXiv:2306.05817, 2023.",
    "黄立威, 江碧涛, 吕守业, 等. 基于深度学习的推荐系统研究综述[J]. 计算机学报, 2018, 41(7): 1619-1647.",
    "朱郁筱, 吕琳媛. 推荐系统评价指标综述[J]. 电子科技大学学报, 2012, 41(2): 163-175.",
]


def build_refs(doc):
    add_heading(doc, "参考文献", 1)
    for i, ref in enumerate(REFS, 1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = Pt(28)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.left_indent = Cm(0.74)
        pf.first_line_indent = Cm(-0.74)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run = p.add_run(f"[{i}] {ref}")
        set_run_font(run, 10.5, east="仿宋")


def build_appendix(doc):
    add_heading(doc, "附录 A  工程目录与复现命令", 1)
    add_body(doc, "本附录给出复现实验所需的主要命令。完整命令与说明见仓库 README。")
    add_code(doc, "\n".join([
        "# 1. 安装依赖",
        "python -m venv venv",
        "venv\\Scripts\\activate",
        "pip install -r requirements.txt",
        "",
        "# 2. 准备数据与特征（或直接使用 data/processed）",
        "python -m recsys.etl",
        "python scripts/01_build_features.py",
        "",
        "# 3. 建库并导入三个数据集",
        "python scripts/03_build_db.py",
        "",
        "# 4. 训练与评测（以 MovieLens 为例）",
        "python scripts/02_run_benchmark.py --dataset movielens --models EASE ItemKNN BPR NeuMF LightGCN SGL NCL DGCF",
        "python scripts/06_train_freedom.py",
        "python scripts/08_sync_metrics.py --dataset movielens",
        "",
        "# 5. 生成离线推荐并落库",
        "python scripts/04_generate_recs.py --dataset movielens --models EASE ItemKNN NeuMF hybrid --topk-hybrid 60",
        "python scripts/04_generate_recs.py --dataset goodbooks --models hybrid --topk-hybrid 60",
        "",
        "# 6. 启动服务与静态镜像",
        "python -m waitress --host=127.0.0.1 --port=8080 run:app",
        "python scripts/10_build_static.py",
    ]))
    add_body(doc, "说明：Book-Crossing 用于大规模统计与鲁棒性对照，不在 Web 前端直接展示；Goodbooks 主展示库按活跃度裁剪到 4000 名用户，以控制 SQLite 体积。EASE checkpoint 约 379 MB，未提交到 GitHub，可通过 Release 或脚本重新训练获得。")


# ------------------------------------------------------------------ 主流程
def build_docx():
    doc = Document()
    setup_page(doc)
    doc.core_properties.title = TITLE
    doc.core_properties.author = STUDENT_NAME
    doc.core_properties.subject = "推荐系统课程设计 2026"

    build_cover(doc)
    build_toc(doc)

    for block in BLOCKS:
        kind = block[0]
        if kind == "h1":
            add_heading(doc, block[1], 1)
        elif kind == "h2":
            add_heading(doc, block[1], 2)
        elif kind == "p":
            add_body(doc, block[1])
        elif kind == "center":
            add_center(doc, block[1])
        elif kind == "fig":
            add_figure(doc, ROOT / block[1], block[2], block[3])
        elif kind == "table":
            add_table(doc, block[1], block[2], block[3], block[4])
        elif kind == "code":
            add_code(doc, block[1])
        elif kind == "pagebreak":
            doc.add_page_break()

    build_refs(doc)
    build_appendix(doc)
    doc.save(DOCX_PATH)
    print(f"[REPORT] docx -> {DOCX_PATH} ({DOCX_PATH.stat().st_size/1024/1024:.1f} MB)")
    return DOCX_PATH


def convert_to_doc():
    import win32com.client as win32

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(DOCX_PATH))
        # 更新目录与所有域（页码、引用）
        d.Fields.Update()
        if d.TablesOfContents.Count:
            toc = d.TablesOfContents(1)
            toc.Update()
            # Word 生成的目录默认继承正文 28 磅固定行距，会把目录撑到 3 页；
            # 这里直接改 TOC 样式为 20 磅固定行距，再刷新一次页码。
            for style_name in ("TOC 1", "TOC 2"):
                try:
                    st = d.Styles(style_name)
                    st.ParagraphFormat.LineSpacingRule = 4  # wdLineSpaceExactly
                    st.ParagraphFormat.LineSpacing = 20
                    st.ParagraphFormat.SpaceBefore = 0
                    st.ParagraphFormat.SpaceAfter = 0
                except Exception:
                    pass
            toc.Update()
            d.Repaginate()
            toc.Update()
        d.Repaginate()
        d.Save()  # 把更新后的目录一起写回 docx
        d.SaveAs2(str(DOC_PATH), FileFormat=0)  # wdFormatDocument
        d.SaveAs2(str(PDF_PATH), FileFormat=17)  # wdFormatPDF
        d.Close(False)
    finally:
        word.Quit()
    print(f"[REPORT] doc  -> {DOC_PATH} ({DOC_PATH.stat().st_size/1024/1024:.1f} MB)")
    print(f"[REPORT] pdf  -> {PDF_PATH} ({PDF_PATH.stat().st_size/1024/1024:.1f} MB)")


def count_chars():
    body = sum(len(re.findall(r"[\u4e00-\u9fff]", fill(b[1])))
               for b in BLOCKS if b[0] in ("p", "center", "h1", "h2", "h3"))
    return body


if __name__ == "__main__":
    print(f"[REPORT] 正文汉字数（不含表格/参考文献）：{count_chars()}")
    build_docx()
    convert_to_doc()
    print("[REPORT] 完成")
