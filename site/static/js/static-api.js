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
    cache[name] = await r.json();
    return cache[name];
  }
  const origFetch = window.fetch.bind(window);
  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

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
      return json({ items: items.slice(0, Number(q.get("k") || 12)) });
    }
    if (p === "/api/users") {
      const d = await load("users");
      return json({ users: d[q.get("dataset") || "movielens"] || [] });
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
      return json({ ...out, items: (out.items || []).slice(0, k) });
    }
    if (p.startsWith("/api/history/")) {
      const uid = p.split("/").pop();
      const ds2 = q.get("dataset") || "movielens";
      const d = await load("history");
      return json({ user_id: Number(uid), items: d[`${ds2}|${uid}`] || [] });
    }
    if (p.startsWith("/api/items/")) {
      const iid = p.split("/").pop();
      const ds2 = q.get("dataset") || "movielens";
      const items = await load(`items_${ds2}`);
      const it = items[iid];
      if (!it) return json({ error: "item not found" }, 404);
      const sim = await load("similar");
      return json({
        ...it,
        rating_avg: it.avg_rating,
        rating_count: it.n_ratings,
        similar: sim[`${ds2}|${iid}`] || [],
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
