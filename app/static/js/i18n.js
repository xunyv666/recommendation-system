/* 中英双语切换（默认英文，可切中文）
 * - 静态文案：模板里用 data-i18n="key" 标记，本文件按字典替换
 * - 动态文案：app.js 通过 I18N.t(key, 中文兜底) 取词
 * - 语言偏好存 localStorage，切换后刷新页面
 */
(function () {
  const STORE = "rs-lang";

  const EN = {
    /* 顶栏 / 页脚 */
    "brand": 'Intelligent Recommender<small>Course Design 2026</small>',
    "nav.home": "Home",
    "nav.recommend": "Recommendations",
    "nav.dashboard": "Benchmarks",
    "nav.about": "About",
    "ds.movie": "Movies",
    "ds.book": "Books",
    "footer.course": "Recommender Systems Course Project · Nanjing University of Finance and Economics",
    "footer.arch": "Offline training + online lookup architecture",
    "health.checking": "Checking service status…",

    /* 首页 */
    "home.h1": "Picking what each user<br><em>actually wants to watch</em>",
    "home.cta1": "Try personalized recommendations",
    "home.cta2": "Compare algorithms",
    "stat.items": "Items",
    "stat.users": "Users",
    "stat.ratings": "Ratings",
    "home.pipeline": "Recommendation pipeline",
    "pipe.1.t": "Multi-source recall",
    "pipe.1.d": "FREEDOM multi-view / LightGCN / content profile / popularity",
    "pipe.2.t": "Fusion ranking",
    "pipe.2.d": "Merge, dedupe and normalize candidate scores",
    "pipe.3.t": "Re-ranking & explanation",
    "pipe.3.d": "MMR diversity + LLM/template reasons",
    "pipe.4.t": "Online serving",
    "pipe.4.d": "Precomputed offline, millisecond responses",
    "home.popular": "Popular",
    "chip.all": "All",

    /* 推荐页 */
    "rec.h2": "Personalized Recommendations",
    "rec.desc": "Pick a user and an algorithm to compare recommendation strategies and explanations",
    "rec.user": "User",
    "rec.algo": "Algorithm",
    "rec.k": "Count",
    "rec.run": "Generate",
    "opt.hybrid": "Hybrid (default)",
    "opt.content": "Content-based",
    "opt.pop": "Popularity",
    "opt.lightgcn": "LightGCN (graph)",
    "opt.itemknn": "ItemKNN (collaborative)",
    "opt.freedom": "FREEDOM (multi-view)",
    "rec.loading": 'Choose options and click "Generate"',
    "rec.history": "Rating history of this user",

    /* 看板 */
    "dash.h2": "Algorithm Benchmark",
    "dash.desc": "Full-ranking evaluation on identical splits (8:1:1 temporal split, Top-10 full ranking)",
    "th.model": "Model",
    "th.recall": "Recall@10",
    "th.ndcg": "NDCG@10",
    "th.mrr": "MRR@10",
    "th.prec": "Precision@10",
    "th.time": "Train time (s)",
    "dash.chart": "NDCG@10 comparison",

    /* 关于页 */
    "about.h1": "About This System",
    "about.badge": "Course Project",
    "about.s1": "1. Positioning",
    "about.p1": "This is a general-purpose recommender system covering two scenarios: <strong>movies</strong> and <strong>books</strong>. Users pick a domain to get personalized recommendations, browse item details and similar items, and compare the offline evaluation results of different models in the benchmark dashboard.",
    "about.s2": "2. Architecture",
    "about.li.fe": "<b>Frontend</b>: vanilla HTML/CSS/JS, zero external dependencies, deployable as a static site",
    "about.li.be": "<b>Backend</b>: Flask REST API, Waitress as the production WSGI server",
    "about.li.algo": "<b>Algorithm layer</b>: unified training and evaluation on the open-source RecBole platform",
    "about.li.store": "<b>Storage</b>: SQLAlchemy + SQLite (dev) / MySQL (production)",
    "about.li.deploy": "<b>Deployment</b>: GitHub → Cloudflare Pages (frontend) + Cloudflare Tunnel (backend)",
    "about.s3": "3. Recommendation Pipeline",
    "about.p3": "The system uses a two-stage <strong>offline training + online lookup</strong> architecture:",
    "about.li.off": "<b>Offline</b>: train graph-convolution models on historical interactions, precompute Top-N recommendations for every user and persist them; also compute the item content-similarity matrix",
    "about.li.on": "<b>Online</b>: query precomputed results directly, add content-profile recall and a popularity fallback, then apply MMR diversity re-ranking in hybrid mode — millisecond responses without a GPU",
    "about.s4": "4. Algorithms",
    "about.li.lightgcn": "<b>LightGCN</b>: linear propagation on the user–item bipartite graph without nonlinear transforms — effective and fast to train",
    "about.li.sgl": "<b>SGL / NCL</b>: self-supervised contrastive learning to mitigate representation degradation under sparse interactions",
    "about.li.itemknn": "<b>ItemKNN</b>: classic item co-occurrence collaborative filtering, used as a strong baseline",
    "about.li.ease": "<b>EASE</b>: closed-form linear autoencoder, often stronger than deep models on sparse data",
    "about.li.freedom": "<b>FREEDOM (this work)</b>: multi-view graph fusion — collaborative-graph propagation + content-graph propagation, cross-view contrastive alignment and adaptive fusion",
    "about.li.content": "<b>Content-based</b>: TF-IDF text semantics + multi-hot categories + structured features, addressing cold start",
    "about.li.fusion": "<b>Fusion & re-ranking</b>: normalized fusion of multi-source recall, MMR diversity re-ranking, optional LLM-generated explanations",
    "about.s5": "5. Datasets",
    "about.li.ml": "<b>MovieLens</b> (movies, live demo): 610 users / 9,724 movies / 100,836 ratings",
    "about.li.gb": "<b>Goodbooks-10k</b> (books, live demo): 10,000 books / 5,976,479 ratings; the demo uses the 4,000 most active users",
    "about.li.bc": "<b>Book-Crossing</b> (books, large-scale reference): 22,593 users / 257,815 books / 929,723 ratings",
    "about.copy": "© 2026 Recommender Systems Course Project · Nanjing University of Finance and Economics",

    /* 动态文案 */
    "dyn.loading": "Loading…",
    "dyn.failed": "Failed to load",
    "dyn.empty": "No data",
    "dyn.computing": "Computing…",
    "dyn.recFailed": "Recommendation failed",
    "dyn.noHistory": "No rating history yet",
    "dyn.sourceLine": "Recall source:",
    "dyn.avgRating": "Average rating",
    "dyn.ratingCount": "Ratings",
    "dyn.popularity": "Popularity score",
    "dyn.itemId": "Item ID",
    "dyn.noDesc": "No description available for this item.",
    "dyn.similar": "Similar items",
    "dyn.similarDesc": "Three-view cosine similarity over text semantics + categories + structured features",
    "dyn.itemMissing": "Item not found or offline",
    "dyn.noMetrics": "No experiment data yet — run the benchmark first",
    "dyn.healthy": "Service online",
    "dyn.offline": "Service offline",
    "dyn.userOption": "User {id} ({n} ratings)",
  };

  const TITLES = {
    "/": "Home · RecSys 2026",
    "/recommend": "Recommendations · RecSys 2026",
    "/dashboard": "Benchmarks · RecSys 2026",
    "/about": "About · RecSys 2026",
  };

  let lang = localStorage.getItem(STORE) || "en";

  function t(key, zh) {
    if (lang === "zh") return zh != null ? zh : key;
    return EN[key] != null ? EN[key] : (zh != null ? zh : key);
  }

  function updateTitle() {
    if (lang !== "en") return;
    const p = location.pathname.replace(/\/+$/, "") || "/";
    const key = p.indexOf("/item/") === 0 ? "/item" : p;
    document.title = TITLES[key] || "Item Detail · RecSys 2026";
  }

  function applyStatic() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    if (lang === "zh") return;
    document.querySelectorAll("[data-i18n]").forEach((n) => {
      const v = EN[n.getAttribute("data-i18n")];
      if (v != null) n.innerHTML = v;
    });
    updateTitle();
  }

  /* 推荐理由的中译英（只处理已知模板，其余原样返回） */
  function reason(s) {
    if (lang !== "en" || !s) return s;
    let m;
    if ((m = s.match(/^你偏好的类型是「(.+?)」，该物品同属「(.+?)」，且评分 ([\d.]+)$/))) {
      return `You prefer "${m[1].replace(/、/g, ", ")}"; this item is also "${m[2].replace(/、/g, ", ")}"; rated ${m[3]}`;
    }
    if ((m = s.match(/^内容相似度 ([\d.]+)$/))) return `Content similarity ${m[1]}`;
    if ((m = s.match(/^综合多路召回信号后排序靠前(?:，题材同属「(.+?)」)?(?:，评分 ([\d.]+)（(\d+) 人评）)?$/))) {
      let out = "Ranked high after fusing multi-source recall";
      if (m[1]) out += `; genre matches "${m[1].replace(/、/g, ", ")}"`;
      if (m[2]) out += `; rated ${m[2]} (${m[3]} ratings)`;
      return out;
    }
    return s;
  }

  function buildSwitch() {
    const bar = document.querySelector(".topbar-inner");
    if (!bar || bar.querySelector(".lang-switch")) return;
    const box = document.createElement("div");
    box.className = "lang-switch";
    box.innerHTML =
      '<button data-lang="en" class="' + (lang === "en" ? "on" : "") + '">EN</button>' +
      '<button data-lang="zh" class="' + (lang === "zh" ? "on" : "") + '">中文</button>';
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      const next = b.dataset.lang;
      if (next === lang) return;
      localStorage.setItem(STORE, next);
      location.reload();
    });
    bar.appendChild(box);
  }

  window.I18N = { t, reason, get lang() { return lang; } };

  function boot() {
    buildSwitch();
    applyStatic();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
