/* 前端交互逻辑：纯原生 JS，无任何 CDN 依赖，可直接部署到 Cloudflare Pages */
(function () {
  const DS = document.body.dataset.dataset || "movielens";

  /* ---------------- 工具 ---------------- */
  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  };
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

  /* 文案取词：默认英文，I18N 不可用时回落到中文 */
  const T = (k, zh) => (window.I18N ? I18N.t(k, zh) : zh);
  const Tf = (k, zh, vars) =>
    T(k, zh).replace(/\{(\w+)\}/g, (_, n) => (vars[n] != null ? vars[n] : ""));
  const RSN = (s) => (window.I18N ? I18N.reason(s) : s);

  async function get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }

  /* 确定性渐变色：同一 id 永远同一颜色，视觉上稳定且区分度高 */
  const PALETTES = [
    ["#3b5bdb", "#7048e8"], ["#0c8599", "#1864ab"], ["#c2255c", "#862e9c"],
    ["#a61e4d", "#d9480f"], ["#2b8a3e", "#0b7285"], ["#5f3dc4", "#364fc7"],
    ["#e8590c", "#c92a2a"], ["#00838f", "#2e7d32"], ["#4527a0", "#ad1457"],
    ["#37474f", "#546e7a"],
  ];
  function palette(id) {
    const p = PALETTES[Math.abs(Number(id) || 0) % PALETTES.length];
    return `linear-gradient(150deg,${p[0]},${p[1]})`;
  }
  function posterChar(title) {
    const t = String(title || "?").trim();
    // 英文取首字母，中文取首字
    const m = t.match(/[A-Za-z0-9]/);
    return m ? m[0].toUpperCase() : t.slice(0, 1);
  }
  function stars(v) {
    const n = Math.round((Number(v) || 0) / 2);
    return "★".repeat(Math.max(0, Math.min(5, n))) + "☆".repeat(Math.max(0, 5 - n));
  }

  /* ---------------- 卡片 ---------------- */
  function card(item, opts = {}) {
    const a = el("a", "card");
    a.href = `/item/${item.id}?dataset=${DS}`;
    a.dataset.itemId = item.id;

    let flags = null;
    if (item.image_url) {
      const poster = el("div", "poster", "");
      poster.style.background = `url('${item.image_url}') center/cover, ${palette(item.id)}`;
      if (opts.rank != null) poster.appendChild(el("div", "rank-badge", String(opts.rank)));
      if (item.score != null && opts.showScore)
        poster.appendChild(el("div", "score-badge", Number(item.score).toFixed(3)));
      a.appendChild(poster);
    } else {
      // 电影域没有封面图：不再占一块纯色占位，直接做成以标题为主体的文本卡片
      a.classList.add("no-poster");
      flags = el("div", "card-flags");
      if (opts.rank != null) flags.appendChild(el("span", "rank-badge", String(opts.rank)));
      if (item.score != null && opts.showScore)
        flags.appendChild(el("span", "score-badge", Number(item.score).toFixed(3)));
    }

    const body = el("div", "card-body");
    // 无封面时把序号/分数放在标题上方单独一行，避免绝对定位压住标题
    if (flags && flags.children.length) body.appendChild(flags);
    const showZh = I18N.lang === "zh" && item.title_zh;
    const titleEl = el("div", "card-title", esc(showZh ? item.title_zh : item.title));
    if (showZh) titleEl.title = item.title;
    body.appendChild(titleEl);

    const meta = el("div", "card-meta");
    const genres = String(item.genres || "").split(/[| ]/).filter(Boolean).slice(0, 2);
    genres.forEach((g) => meta.appendChild(el("span", "tag", esc(I18N.genre(g)))));
    if (item.year) meta.appendChild(el("span", "", esc(item.year)));
    if (item.avg_rating) {
      meta.appendChild(el("span", "stars", stars(item.avg_rating)));
      meta.appendChild(el("span", "", Number(item.avg_rating).toFixed(1)));
    }
    body.appendChild(meta);

    if (opts.showReason && item.reason)
      body.appendChild(el("div", "reason", esc(RSN(item.reason))));

    a.appendChild(body);

    a.addEventListener("click", () => {
      fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: opts.userId || 0, item_id: item.id,
          action: "click", algo: opts.algo || "", position: opts.rank || 0,
        }),
      }).catch(() => {});
    });
    return a;
  }

  function renderGrid(target, items, opts = {}) {
    target.innerHTML = "";
    if (!items || !items.length) {
      target.appendChild(el("div", "empty", T("dyn.empty", "暂无数据")));
      return;
    }
    items.forEach((it, i) =>
      target.appendChild(card(it, { ...opts, rank: opts.noRank ? null : i + 1 }))
    );
  }

  /* ---------------- 首页 ---------------- */
  async function initHome() {
    try {
      const ov = await get(`/api/overview?dataset=${DS}`);
      $("#statItems").textContent = (ov.n_items || 0).toLocaleString();
      $("#statUsers").textContent = (ov.n_users || 0).toLocaleString();
      $("#statRatings").textContent = (ov.n_ratings || 0).toLocaleString();

      const chips = $("#genreChips");
      (ov.top_genres || []).slice(0, 9).forEach((g) => {
        const b = el("button", "chip", esc(I18N.genre(g)));
        b.dataset.genre = g;
        chips.appendChild(b);
      });
      chips.addEventListener("click", (e) => {
        const b = e.target.closest(".chip");
        if (!b) return;
        chips.querySelectorAll(".chip").forEach((x) => x.classList.remove("on"));
        b.classList.add("on");
        loadPopular(b.dataset.genre);
      });
    } catch (e) {
      console.error(e);
    }
    loadPopular("");
    bindSearch();
  }

  let currentGenre = "";
  const hint = () => $("#searchHint");
  function setHint(text) {
    const h = hint();
    if (h) h.textContent = text;
  }

  async function loadPopular(genre) {
    currentGenre = genre || "";
    const grid = $("#itemGrid");
    grid.innerHTML = '<div class="loading">' + esc(T("dyn.loading", "加载中…")) + "</div>";
    const q = new URLSearchParams({ dataset: DS, k: 24 });
    if (genre) q.set("genre", genre);
    setHint(T("search.hint", "输入片名、题材或年份，检索全部条目"));
    try {
      const d = await get("/api/popular?" + q);
      renderGrid(grid, d.items, { showScore: false });
    } catch (e) {
      grid.innerHTML = '<div class="empty">' + esc(T("dyn.failed", "加载失败")) + "</div>";
    }
  }

  /* ---------------- 关键词检索 ---------------- */
  let searchTimer = null;

  async function runSearch(q) {
    const grid = $("#itemGrid");
    grid.innerHTML = '<div class="loading">' + esc(T("dyn.loading", "加载中…")) + "</div>";
    setHint(T("search.searching", "检索中…"));
    try {
      const p = new URLSearchParams({ dataset: DS, q, k: 48 });
      const d = await get("/api/search?" + p);
      renderGrid(grid, d.items, { showScore: false, noRank: true });
      setHint(
        d.total
          ? T("search.found", "「{q}」找到 {n} 条结果").replace("{q}", q).replace("{n}", d.total)
          : T("search.none", "「{q}」没有匹配结果，换个关键词试试").replace("{q}", q)
      );
    } catch (e) {
      grid.innerHTML = '<div class="empty">' + esc(T("dyn.failed", "加载失败")) + "</div>";
      setHint(T("search.hint", "输入片名、题材或年份，检索全部条目"));
    }
  }

  function bindSearch() {
    const input = $("#searchInput");
    const clear = $("#searchClear");
    const chips = $("#genreChips");
    if (!input) return;

    const reset = () => {
      input.value = "";
      clear.hidden = true;
      chips.style.display = "";
      loadPopular(currentGenre);
    };

    input.addEventListener("input", () => {
      const q = input.value.trim();
      clear.hidden = !q;
      chips.style.display = q ? "none" : "";
      clearTimeout(searchTimer);
      if (!q) {
        loadPopular(currentGenre);
        return;
      }
      searchTimer = setTimeout(() => runSearch(q), 220);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape") reset();
    });

    clear.addEventListener("click", () => {
      reset();
      input.focus();
    });
  }

  /* ---------------- 个性化推荐 ---------------- */
  async function initRecommend() {
    const userSel = $("#userSelect");
    const params = new URLSearchParams(location.search);
    const wantUid = params.get("uid");
    const wantAlgo = params.get("algo");
    const wantK = params.get("k");
    if (wantAlgo && [...$("#algoSelect").options].some((o) => o.value === wantAlgo))
      $("#algoSelect").value = wantAlgo;
    if (wantK && [...$("#kSelect").options].some((o) => o.value === wantK))
      $("#kSelect").value = wantK;

    try {
      const d = await get(`/api/users?dataset=${DS}&limit=200`);
      const dense = (d.users || []).filter((u) => u.n_ratings >= 20).slice(0, 30);
      (dense.length ? dense : d.users || []).forEach((u) => {
        const o = el("option", "", esc(Tf("dyn.userOption", "用户 {id}（{n} 条评分）", {
          id: u.user_id, n: u.n_ratings,
        })));
        o.value = u.user_id;
        userSel.appendChild(o);
      });
      if (wantUid && [...userSel.options].some((o) => o.value === wantUid))
        userSel.value = wantUid;
    } catch (e) {
      console.error(e);
    }

    const run = async () => {
      const uid = userSel.value;
      const algo = $("#algoSelect").value;
      const k = $("#kSelect").value;
      const grid = $("#recGrid");
      grid.innerHTML = '<div class="loading">' + esc(T("dyn.computing", "计算中…")) + '</div>';
      $("#sourceLine").textContent = "";

      try {
        const d = await get(
          `/api/recommend/${uid}?dataset=${DS}&algo=${encodeURIComponent(algo)}&k=${k}`
        );
        renderGrid(grid, d.items, { showReason: true, showScore: true, userId: uid, algo });
        $("#sourceLine").innerHTML =
          `${esc(T("dyn.sourceLine", "召回来源："))} <b>${esc(d.source)}</b> · ` +
          `${esc(T("rec.user", "用户"))} ${esc(uid)} · ${esc(T("rec.algo", "算法"))} ${esc(algo)}`;
        loadHistory(uid);
      } catch (e) {
        grid.innerHTML = '<div class="empty">' + esc(T("dyn.recFailed", "推荐失败")) + '</div>';
      }
    };

    $("#runBtn").addEventListener("click", () => {
      const url = new URL(location.href);
      url.searchParams.set("uid", userSel.value);
      url.searchParams.set("algo", $("#algoSelect").value);
      url.searchParams.set("k", $("#kSelect").value);
      history.replaceState(null, "", url);
      run();
    });
    if (userSel.options.length) run();
  }

  async function loadHistory(uid) {
    const box = $("#historyList");
    box.innerHTML = "";
    try {
      const d = await get(`/api/history/${uid}?dataset=${DS}&limit=12`);
      (d.items || []).forEach((it) => {
        const n = el("div", "hitem");
        n.appendChild(el("span", "", esc(String(it.title).slice(0, 26))));
        n.appendChild(el("span", "stars", `${stars(it.user_rating)} ${Number(it.user_rating).toFixed(1)}`));
        box.appendChild(n);
      });
      if (!d.items || !d.items.length)
        box.innerHTML = '<div class="empty">' + esc(T("dyn.noHistory", "暂无行为记录")) + '</div>';
    } catch (e) {
      box.innerHTML = '<div class="empty">' + esc(T("dyn.noHistory", "暂无行为记录")) + '</div>';
    }
  }

  /* ---------------- 详情页 ---------------- */
  async function initDetail(itemId) {
    const root = $("#detailRoot");
    try {
      const d = await get(`/api/items/${itemId}?dataset=${DS}`);
      const showZh = I18N.lang === "zh" && d.title_zh;
      const titleText = showZh ? d.title_zh : d.title;
      root.innerHTML = `
        <div class="detail${d.image_url ? "" : " no-cover"}">
          ${
            d.image_url
              ? `<div class="detail-cover">
            <div class="poster" style="border-radius:16px;overflow:hidden;
              background:url('${d.image_url}') center/cover, ${palette(d.id)}"></div>
          </div>`
              : ""
          }
          <div>
            <h1>${esc(titleText)}</h1>
            ${showZh ? `<p class="muted" style="margin:-6px 0 14px">${esc(d.title)}</p>` : ""}
            <div class="detail-meta">
              ${String(d.genres || "").split("|").filter(Boolean)
                .map((g) => `<span class="tag">${esc(I18N.genre(g))}</span>`).join("")}
              ${d.year ? `<span class="tag">${esc(d.year)}</span>` : ""}
            </div>
            <div class="kv">
              <div><span>${esc(T("dyn.avgRating", "平均评分"))}</span><b>${Number(d.rating_avg || 0).toFixed(2)}</b></div>
              <div><span>${esc(T("dyn.ratingCount", "评分人数"))}</span><b>${Number(d.rating_count || 0).toLocaleString()}</b></div>
              <div><span>${esc(T("dyn.popularity", "热度分"))}</span><b>${Number(d.popularity || 0).toFixed(4)}</b></div>
              <div><span>${esc(T("dyn.itemId", "物品 ID"))}</span><b>${d.id}</b></div>
            </div>
            <p class="muted">${esc(d.description || T("dyn.noDesc", "该物品暂无简介。"))}</p>
          </div>
        </div>
        <div class="section-head" style="margin-top:46px"><h2>${esc(T("dyn.similar", "内容相似的物品"))}</h2>
          <p class="muted">${esc(T("dyn.similarDesc", "基于文本语义 + 类别 + 结构化特征的三视图余弦相似度"))}</p></div>
        <div class="grid" id="simGrid"></div>`;
      renderGrid($("#simGrid"), d.similar, { showScore: true });
    } catch (e) {
      root.innerHTML = '<div class="empty">' + esc(T("dyn.itemMissing", "物品不存在或已下线")) + '</div>';
    }
  }

  /* ---------------- 算法看板 ---------------- */
  async function initDashboard() {
    const tbody = $("#metricTable").querySelector("tbody");
    const bars = $("#ndcgBars");
    try {
      const d = await get(`/api/metrics?dataset=${DS}`);
      const entries = Object.entries(d.metrics || {});
      if (!entries.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">' +
          esc(T("dyn.noMetrics", "暂无实验数据，请先运行基准脚本")) + '</td></tr>';
        bars.innerHTML = '<div class="empty">' + esc(T("dyn.empty", "暂无数据")) + '</div>';
        return;
      }
      const rows = entries.map(([m, v]) => ({
        model: m,
        recall: v["recall@10"] || 0,
        ndcg: v["ndcg@10"] || 0,
        mrr: v["mrr@10"] || 0,
        prec: v["precision@10"] || 0,
        secs: v["train_seconds"] || 0,
      })).sort((a, b) => b.ndcg - a.ndcg);

      const best = rows.length ? rows[0].ndcg : 0;
      tbody.innerHTML = rows.map((r, i) => `
        <tr>
          <td><div class="model-name">
            <span class="medal">${i + 1}</span><b>${esc(r.model)}</b>
          </div></td>
          <td>${r.recall.toFixed(4)}</td>
          <td class="${r.ndcg === best ? "best" : ""}">${r.ndcg.toFixed(4)}</td>
          <td>${r.mrr.toFixed(4)}</td>
          <td>${r.prec.toFixed(4)}</td>
          <td>${r.secs ? r.secs.toFixed(1) : "—"}</td>
        </tr>`).join("");

      const max = Math.max(...rows.map((r) => r.ndcg), 1e-9);
      bars.innerHTML = rows.map((r) => `
        <div class="bar-row">
          <span class="name">${esc(r.model)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${(r.ndcg / max) * 100}%"></div></div>
          <span class="val">${r.ndcg.toFixed(4)}</span>
        </div>`).join("");
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">' +
        esc(T("dyn.failed", "加载失败")) + '</td></tr>';
    }
  }

  /* ---------------- 全局 ---------------- */
  document.querySelectorAll(".domain-switch button").forEach((b) => {
    b.addEventListener("click", () => {
      const url = new URL(location.href);
      url.searchParams.set("dataset", b.dataset.ds);
      location.href = url.toString();
    });
  });

  fetch("/api/health").then((r) => r.json()).then(() => {
    const t = $("#healthTag");
    if (t) t.textContent = T("dyn.healthy", "服务正常");
  }).catch(() => {
    const t = $("#healthTag");
    if (t) { t.textContent = T("dyn.offline", "服务离线"); t.style.color = "#fbbf24"; }
  });

  window.App = { initHome, initRecommend, initDetail, initDashboard };
})();
