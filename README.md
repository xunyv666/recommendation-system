# 双域智能推荐系统

基于 MovieLens、Goodbooks-10k 与 Book-Crossing 的推荐系统课程设计。系统覆盖
**数据 ETL → 多视图特征 → 模型训练/评测 → 离线预计算 → Web 服务 → 静态镜像部署**
的完整链路，支持电影与图书两个应用域。

## 快速开始

```bash
# 1. 安装依赖（Python 3.12；务必保留 numpy/scipy 的版本锁）
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. 原始数据放到 data/raw/{movielens, goodbooks, book-crossing}/ 后
python -m recsys.etl
python scripts/01_build_features.py
python scripts/03_build_db.py

# 3. 训练与评测（CPU 可跑；完整基准约数小时，EASE 最慢）
python scripts/02_run_benchmark.py --dataset movielens
python scripts/08_sync_metrics.py --dataset movielens

# 4. 生成在线推荐并落库
python scripts/04_generate_recs.py --dataset movielens
python scripts/04_generate_recs.py --dataset goodbooks --models ""

# 5. 图表、报告、静态镜像、启动服务
python scripts/05_make_figures.py
python scripts/12_make_report.py
python scripts/10_build_static.py
python run.py            # http://127.0.0.1:5000

# 仅预览无后端静态镜像（自动兼容 /recommend 等干净 URL）：
python scripts/serve_static.py   # http://127.0.0.1:8082
```

生产模式：

```bash
waitress-serve --port 8080 run:app
```

## 目录结构

```text
app/                 Flask 应用（页面 + REST API + ORM）
recsys/              ETL、特征工程、统一训练器、融合模型、LLM/MMR
scripts/             01–10 流水线脚本
data/processed/      清洗后的交互、物品、特征、相似图
experiments/results/ 基准结果、checkpoint、融合评测、LLM 演示
figures/             报告图表
screenshots/         系统运行截图
site/                Cloudflare Pages 静态镜像（由脚本生成）
report/              课程设计报告
```

## 主要结果（MovieLens，8:1:1 时间序切分，Top-10 全排序）

| 模型 | NDCG@10 | Recall@10 | 训练耗时 |
|---|---:|---:|---:|
| EASE | 0.0688 | 0.0602 | 14588 s |
| ItemKNN | 0.0628 | 0.0578 | 130 s |
| NCL | 0.0580 | 0.0501 | 6353 s |
| BPR | 0.0576 | 0.0493 | 24 s |
| NeuMF | 0.0514 | 0.0467 | 470 s |
| Pop | 0.0437 | 0.0345 | 30 s |
| LightGCN | 0.0416 | 0.0334 | 139 s |
| DGCF | 0.0413 | 0.0326 | 3644 s |
| FREEDOM（本文） | 0.0390 | 0.0307 | 158 s |
| SGL | 0.0189 | 0.0222 | 419 s |
| Random | 0.0020 | 0.0011 | 24 s |

完整实验分析见 `report/2020601616.docx`（同目录提供 `.doc` 与 `.pdf`）。

## 中文交互与管理后台

- 前台默认中文，顶栏 `EN / 中文` 可随时切换，偏好保存在浏览器本地。
- 电影 / 图书标题优先显示中文译名库（`data/processed/titles_zh.json`，前后台共用）；
  未入库的标题由前端本地词典即时翻译，保证中文模式下每条都有中文可读。
- 扩充译名：`python scripts/14_expand_zh_titles.py --all --top 800`（MyMemory 批量接口，可续跑）。
- 管理后台：`python run.py` 后访问 `http://127.0.0.1:5000/admin/`。
  演示密码 `recsys2026`（生产环境请用环境变量 `ADMIN_PASSWORD` 覆盖）。
  后台提供数据总览、物品 / 用户浏览、推荐结果预览、行为日志删除、算法指标，
  以及中文译名的在线维护（保存后同时更新 Flask 与静态镜像的译名表）。

## 说明

- RecBole 1.2.0 与 numpy≥2、scipy≥1.13 不兼容，`requirements.txt` 已锁定可用版本。
- NCL 原始实现依赖 faiss-gpu，本项目替换为 sklearn KMeans，语义等价且可在 Windows/CPU 运行。
- FREEDOM 为课程作业中的简化实现：保留协同图 + 内容图双视图、跨视图对比对齐和自适应融合，
  未纳入图像模态与图剪枝；图像视图缺失的原因见报告 4.2 节，FREEDOM 的实现与实验分析见 4.4 节和 6.5 节。
