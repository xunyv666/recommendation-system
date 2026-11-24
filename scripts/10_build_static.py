"""构建 Cloudflare Pages 静态镜像。

为什么需要静态镜像
------------------
Flask 后端跑在本地/内网，Cloudflare Pages 只能托管静态文件。为了让
"点开网址就能看"不依赖任何一台长期在线的电脑，本脚本把演示所需的
页面、物品元数据、推荐结果与算法指标全部预计算成 JSON，再用一个
浏览器端的 fetch 适配层把 `/api/*` 映射到这些 JSON。

产物:
    site/index.html          电影域首页
    site/recommend.html      个性化推荐（?dataset= 切换电影/图书）
    site/dashboard.html      算法看板
    site/item.html           物品详情（/item/<id> 由 _redirects 重写）
    site/about.html          关于
    site/static/...          复用 Flask 的 CSS / JS
    site/data/*.json         预计算数据
    site/_redirects          Pages 路由规则

用法:
    python scripts/10_build_static.py
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as C
from app import create_app
from app.extensions import db
from app.models import AlgorithmMetric, Item, Rating
from app.services import recommender as R

SITE = C.ROOT / "site"
MOVIE_ALGOS = ["hybrid", "EASE", "ItemKNN", "BPR", "LightGCN", "FREEDOM"]
BOOK_ALGOS = ["hybrid", "content", "pop"]


def item_payload(it, reason: str | None = None, score: float | None = None) -> dict:
    """同时接受 ORM 对象和 recommender 返回的 dict。"""
    if isinstance(it, dict):
        d = dict(it)
        d["id"] = int(d["id"])
        d["avg_rating"] = round(float(d.get("avg_rating") or 0), 3)
        d["n_ratings"] = int(d.get("n_ratings") or 0)
        d["popularity"] = round(float(d.get("popularity") or 0), 6)
        d["description"] = (d.get("description") or "")[:220]
        d["image_url"] = d.get("image_url") or ""
        d["title"] = d.get("title") or ""
        d["genres"] = d.get("genres") or ""
    else:
        d = {
            "id": int(it.id),
            "title": it.title or "",
            "genres": it.genres or "",
            "year": it.year,
            "avg_rating": round(float(it.avg_rating or 0), 3),
            "n_ratings": int(it.n_ratings or 0),
            "popularity": round(float(it.popularity or 0), 6),
            "image_url": it.image_url or "",
            "description": (it.description or "")[:220],
        }
    if reason is not None:
        d["reason"] = reason
    if score is not None:
        d["score"] = round(float(score), 6)
    return d


def demo_users(dataset: str, n: int) -> list[dict]:
    rows = db.session.execute(
        db.select(Rating.user_id, db.func.count(Rating.id).label("c"))
        .where(Rating.dataset == dataset)
        .group_by(Rating.user_id)
        .order_by(db.desc("c"))
        .limit(n)
    ).all()
    return [{"user_id": int(u), "n_ratings": int(c)} for u, c in rows]


def build_data() -> dict:
    ds_list = ["movielens", "goodbooks"]
    overview, popular, users, recs, history, items, similar, metrics = {}, {}, {}, {}, {}, {}, {}, {}

    for ds in ds_list:
        overview[ds] = R.dataset_overview(ds)
        overview[ds]["top_genres"] = R.top_genres(ds)
        overview[ds]["datasets"] = ["movielens", "goodbooks", "bookcrossing"]

        # 首页热门 + 每个题材 chip 的热门（前端点击 chip 时直接查本地 JSON）
        popular[ds] = {"__all__": [item_payload(x) for x in R.popular_items(ds, 24)]}
        for g in overview[ds]["top_genres"]:
            popular[ds][g] = [item_payload(x) for x in R.popular_items(ds, 24, g)]

        # 演示用户：按评分数取最活跃的一批，保证推荐页有足够历史
        demo = demo_users(ds, 12 if ds == "movielens" else 8)
        users[ds] = demo
        items[ds] = {}
        for it in db.session.scalars(db.select(Item).where(Item.dataset == ds)).all():
            items[ds][str(it.id)] = item_payload(it)

        # 历史行为
        for u in demo:
            rows = db.session.execute(
                db.select(Rating, Item)
                .join(Item, (Item.id == Rating.item_id) & (Item.dataset == Rating.dataset))
                .where(Rating.user_id == u["user_id"], Rating.dataset == ds)
                .order_by(Rating.rating.desc(), Rating.timestamp.desc())
                .limit(12)
            ).all()
            history[f"{ds}|{u['user_id']}"] = [
                {**item_payload(it), "user_rating": float(r.rating)}
                for r, it in rows
            ]

        algos = MOVIE_ALGOS if ds == "movielens" else BOOK_ALGOS
        for u in demo:
            for algo in algos:
                d = R.recommend(u["user_id"], ds, algo, 20)
                recs[f"{ds}|{u['user_id']}|{algo}"] = {
                    "dataset": ds,
                    "algo": algo,
                    "source": d.get("source", ""),
                    "rerank": d.get("rerank", "none"),
                    "items": d.get("items", []),
                }

        # 详情页相似物品：只为会被点开的演示物品生成，避免 100 万对相似度全量导出
        wanted: set[int] = set()
        for group in popular[ds].values():
            wanted.update(int(x["id"]) for x in group)
        for key, val in recs.items():
            if key.startswith(ds + "|"):
                wanted.update(int(x["id"]) for x in val["items"])
        for key, val in history.items():
            if key.startswith(ds + "|"):
                wanted.update(int(x["id"]) for x in val)
        for iid in sorted(wanted):
            sims = R.similar_items(iid, ds, 12)
            if sims:
                similar[f"{ds}|{iid}"] = sims

        # 指标
        rows = db.session.scalars(
            db.select(AlgorithmMetric).where(AlgorithmMetric.dataset == ds)
        ).all()
        table: dict[str, dict] = {}
        for r in rows:
            table.setdefault(r.model, {})[r.metric] = r.value
            table[r.model]["train_seconds"] = r.train_seconds
        metrics[ds] = table

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overview": overview,
        "popular": popular,
        "users": users,
        "recs": recs,
        "history": history,
        "metrics": metrics,
        "similar": similar,
    }
    return payload, items


def render_pages() -> None:
    app = create_app()
    app.config["SERVER_NAME"] = None
    client = app.test_client()
    pages = {
        "index.html": "/",
        "recommend.html": "/recommend",
        "dashboard.html": "/dashboard",
        "about.html": "/about",
        "item.html": "/item/0?dataset=goodbooks",
    }
    for name, url in pages.items():
        html = client.get(url).get_data(as_text=True)
        # 静态镜像里 /static/app.js 之前插入 API 适配层
        html = html.replace(
            '<script src="/static/js/app.js"></script>',
            '<script src="/static/js/static-api.js"></script>\n'
            '<script src="/static/js/app.js"></script>',
        )
        if name == "item.html":
            html = re.sub(
                r"<title>[^<]*</title>",
                "<title>物品详情 · 智能推荐系统</title>",
                html,
                count=1,
            )
            replacement = (
                "<script>\n"
                "  const m = location.pathname.match(/\\/item\\/(\\d+)/);\n"
                "  const q = new URLSearchParams(location.search);\n"
                "  App.initDetail(m ? Number(m[1]) : Number(q.get('id') || 0));\n"
                "</script>"
            )
            html = re.sub(
                r"<script>App\.initDetail\([^)]*\);</script>",
                lambda _m: replacement,
                html,
            )
        (SITE / name).write_text(html, encoding="utf-8")
        print(f"[SITE] {name} ({len(html) / 1024:.0f} KB)")


def write_redirects() -> None:
    (SITE / "_redirects").write_text(
        "\n".join([
            "# Cloudflare Pages 自动把 /xxx.html 映射为 /xxx，不要再反向重写，否则会 308 自跳转死循环。",
            "/item/* /item 200",
            "/* / 404",
        ]) + "\n",
        encoding="utf-8",
    )
    (SITE / "_headers").write_text(
        "/data/*\n  Cache-Control: public, max-age=3600\n"
        "/static/*\n  Cache-Control: public, max-age=604800\n",
        encoding="utf-8",
    )


STATIC_API = r"""/* 静态镜像的 API 适配层：把 Flask 的 /api/* 映射到预计算 JSON。
 * 必须在 app.js 之前加载。
 */
(function () {
  const params = new URLSearchParams(location.search);
  const ds = params.get("dataset") || "movielens";
  document.body.dataset.dataset = ds;
  document.querySelectorAll(".domain-switch button").forEach((b) => {
    b.classList.toggle("on", b.dataset.ds === ds);
  });
  document.querySelectorAll('a[href^="/"]').forEach((a) => {
    if (a.getAttribute("href").startsWith("/item/")) return;
    if (!/dataset=/.test(a.getAttribute("href")) && !a.getAttribute("href").startsWith("/about"))
      a.setAttribute("href", a.getAttribute("href") + (a.getAttribute("href").includes("?") ? "&" : "?") + "dataset=" + ds);
  });

  const cache = {};
  async function load(name) {
    if (cache[name]) return cache[name];
    const r = await origFetch(`/data/${name}.json`);
    if (!r.ok) {
      cache[name] = {};
      return {};
    }
    cache[name] = await r.json();
    return cache[name];
  }
  const origFetch = window.fetch.bind(window);
  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

  /* 中文译名表（只覆盖热门条目，缺的返回空串，前端回落到原名） */
  async function zhTable(ds2) {
    const z = await load("titles_zh");
    return (z && z[ds2]) || {};
  }
  function withZh(items, table) {
    return (items || []).map((it) => ({ ...it, title_zh: table[String(it.id)] || "" }));
  }

  window.fetch = async function (input, init) {
    const raw = typeof input === "string" ? input : input.url;
    const url = new URL(raw, location.origin);
    if (!url.pathname.startsWith("/api/")) return origFetch(input, init);
    const p = url.pathname;
    const q = url.searchParams;

    if (p === "/api/health") return json({ status: "ok", service: "static-mirror" });
    if (p === "/api/overview") {
      const d = await load("overview");
      return json(d[q.get("dataset") || "movielens"]);
    }
    if (p === "/api/popular") {
      const d = await load("popular");
      const ds2 = q.get("dataset") || "movielens";
      const g = q.get("genre") || "__all__";
      const items = (d[ds2] && (d[ds2][g] || d[ds2]["__all__"])) || [];
      return json({ items: withZh(items.slice(0, Number(q.get("k") || 12)), await zhTable(ds2)) });
    }
    if (p === "/api/users") {
      const d = await load("users");
      return json({ users: d[q.get("dataset") || "movielens"] || [] });
    }
    if (p === "/api/search") {
      const ds2 = q.get("dataset") || "movielens";
      const k = Number(q.get("k") || 48);
      const ALIAS = {
        "喜剧": "comedy", "剧情": "drama", "动作": "action", "爱情": "romance",
        "科幻": "sci-fi", "恐怖": "horror", "惊悚": "thriller", "动画": "animation",
        "儿童": "children", "犯罪": "crime", "冒险": "adventure", "奇幻": "fantasy",
        "战争": "war", "纪录片": "documentary", "音乐": "musical", "悬疑": "mystery",
        "西部": "western", "小说": "fiction", "青春": "young-adult",
        "历史": "historical-fiction", "传记": "biography", "非虚构": "non-fiction",
      };
      const rawTerm = (q.get("q") || "").trim();
      if (!rawTerm) return json({ query: "", dataset: ds2, total: 0, items: [] });
      const term = (ALIAS[rawTerm] || rawTerm).toLowerCase();
      const all = await load(`items_${ds2}`);
      const table = await zhTable(ds2);
      const hits = [];
      for (const id in all) {
        const it = all[id];
        const t = (it.title || "").toLowerCase();
        const tz = table[String(it.id)] || "";
        const g = (it.genres || "").toLowerCase();
        let tier = -1;
        if (tz && tz.indexOf(rawTerm) === 0) tier = 0;
        else if (t.startsWith(term)) tier = 0;
        else if (tz && tz.includes(rawTerm)) tier = 1;
        else if (t.includes(term)) tier = 1;
        else if (g.includes(term)) tier = 2;
        else if (String(it.year) === term) tier = 3;
        if (tier >= 0) hits.push([tier, it]);
      }
      hits.sort((a, b) => a[0] - b[0] || (b[1].popularity || 0) - (a[1].popularity || 0));
      return json({
        query: rawTerm, dataset: ds2, total: hits.length,
        items: withZh(hits.slice(0, k).map((x) => x[1]), table),
      });
    }
    if (p.startsWith("/api/recommend/")) {
      const uid = p.split("/").pop();
      const ds2 = q.get("dataset") || "movielens";
      const algo = q.get("algo") || "hybrid";
      const k = Number(q.get("k") || 20);
      const d = await load("recs");
      let key = `${ds2}|${uid}|${algo}`;
      if (!d[key]) key = `${ds2}|${uid}|hybrid`;
      const out = d[key] || { dataset: ds2, algo, source: "static", rerank: "mmr", items: [] };
      return json({ ...out, items: withZh((out.items || []).slice(0, k), await zhTable(ds2)) });
    }
    if (p.startsWith("/api/history/")) {
      const uid = p.split("/").pop();
      const ds2 = q.get("dataset") || "movielens";
      const d = await load("history");
      return json({
        user_id: Number(uid),
        items: withZh(d[`${ds2}|${uid}`] || [], await zhTable(ds2)),
      });
    }
    if (p.startsWith("/api/items/")) {
      const iid = p.split("/").pop();
      const ds2 = q.get("dataset") || "movielens";
      const items = await load(`items_${ds2}`);
      const it = items[iid];
      if (!it) return json({ error: "item not found" }, 404);
      const sim = await load("similar");
      const table = await zhTable(ds2);
      return json({
        ...it,
        title_zh: table[String(iid)] || "",
        rating_avg: it.avg_rating,
        rating_count: it.n_ratings,
        similar: withZh(sim[`${ds2}|${iid}`] || [], table),
      });
    }
    if (p === "/api/metrics") {
      const d = await load("metrics");
      return json({ dataset: q.get("dataset") || "movielens", metrics: d[q.get("dataset") || "movielens"] || {} });
    }
    if (p === "/api/feedback") return json({ ok: true, id: 0 });
    return json({ error: "not found" }, 404);
  };
})();
"""


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "static").mkdir(parents=True, exist_ok=True)
    (SITE / "data").mkdir(parents=True, exist_ok=True)

    app = create_app()
    with app.app_context():
        payload, items = build_data()

    (SITE / "data" / "overview.json").write_text(
        json.dumps(payload["overview"], ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "popular.json").write_text(
        json.dumps(payload["popular"], ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "users.json").write_text(
        json.dumps(payload["users"], ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "recs.json").write_text(
        json.dumps(payload["recs"], ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "history.json").write_text(
        json.dumps(payload["history"], ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "metrics.json").write_text(
        json.dumps(payload["metrics"], ensure_ascii=False), encoding="utf-8")
    (SITE / "data" / "similar.json").write_text(
        json.dumps(payload["similar"], ensure_ascii=False), encoding="utf-8")
    for ds, table in items.items():
        (SITE / "data" / f"items_{ds}.json").write_text(
            json.dumps(table, ensure_ascii=False), encoding="utf-8")
    if (C.RESULTS / "llm_demo.json").exists():
        shutil.copy(C.RESULTS / "llm_demo.json", SITE / "data" / "llm_demo.json")

    shutil.copytree(C.ROOT / "app" / "static", SITE / "static", dirs_exist_ok=True)
    (SITE / "static" / "js" / "static-api.js").write_text(STATIC_API, encoding="utf-8")
    render_pages()
    write_redirects()

    total = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"[SITE] 完成：{SITE}  合计 {total / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
