/* 静态镜像的 API 适配层：把 Flask 的 /api/* 映射到预计算 JSON。
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
