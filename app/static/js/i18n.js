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
    "search.ph": "Search title, genre or year",
    "search.hint": "Search the full catalogue by title, genre or year",
    "search.searching": "Searching…",
    "search.found": "「{q}」— {n} results",
    "search.none": "「{q}」— no matches, try another keyword",

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

  // 默认中文交互；用户可点顶栏 EN 切回英文，偏好存入 localStorage
  let lang = localStorage.getItem(STORE) || "zh";

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

  /* 题材标签中文化：只覆盖常见标签，查不到就显示原文 */
  const GENRE_ZH = {
    "action": "动作", "adventure": "冒险", "animation": "动画", "children": "儿童",
    "comedy": "喜剧", "crime": "犯罪", "documentary": "纪录", "drama": "剧情",
    "fantasy": "奇幻", "film-noir": "黑色电影", "horror": "恐怖", "imax": "IMAX",
    "musical": "歌舞", "mystery": "悬疑", "romance": "爱情", "sci-fi": "科幻",
    "thriller": "惊悚", "war": "战争", "western": "西部",
    "fiction": "小说", "young-adult": "青春", "historical-fiction": "历史小说",
    "classics": "经典", "non-fiction": "非虚构", "biography": "传记",
    "fantasy-paranormal": "奇幻", "science-fiction": "科幻", "history": "历史",
    "philosophy": "哲学", "poetry": "诗歌", "psychology": "心理",
    "self-help": "自我提升", "business": "商业", "humor": "幽默",
    "short-stories": "短篇", "graphic-novels": "图像小说", "comics": "漫画",
    "manga": "日漫", "mystery-thriller": "悬疑惊悚", "romance-love": "爱情",
    "adventure-action": "冒险动作", "horror-gothic": "哥特恐怖",
  };

  function genre(g) {
    if (lang !== "zh") return g;
    return GENRE_ZH[String(g).toLowerCase()] || g;
  }

  /* ------------------------------------------------------------------
   * 电影 / 图书标题中文化
   * - 优先用 titles_zh.json 里的人工/翻译记忆入库译名（最准确）
   * - 没有入库译名时用本地词典做规则翻译，保证中文模式下每条都有中文可看
   * ------------------------------------------------------------------ */

  /* 高频词组优先整段替换，避免逐词翻译语序生硬 */
  const TITLE_PHRASES = [
    ["harry potter", "哈利·波特"], ["sorcerer's stone", "魔法石"],
    ["chamber of secrets", "密室"], ["prisoner of azkaban", "阿兹卡班的囚徒"],
    ["goblet of fire", "火焰杯"], ["order of the phoenix", "凤凰社"],
    ["half-blood prince", "混血王子"], ["deathly hallows", "死亡圣器"],
    ["hunger games", "饥饿游戏"], ["catching fire", "燃烧的火焰"],
    ["mockingjay", "嘲笑鸟"], ["twilight", "暮光之城"],
    ["new moon", "新月"], ["breaking dawn", "破晓"], ["eclipse", "月食"],
    ["the lord of the rings", "指环王"], ["fellowship of the ring", "护戒使者"],
    ["the two towers", "双塔奇兵"], ["return of the king", "王者归来"],
    ["star wars", "星球大战"], ["the matrix", "黑客帝国"],
    ["the godfather", "教父"], ["the dark knight", "黑暗骑士"],
    ["shawshank redemption", "肖申克的救赎"], ["pulp fiction", "低俗小说"],
    ["forrest gump", "阿甘正传"], ["green mile", "绿里奇迹"],
    ["the shining", "闪灵"], ["jurassic park", "侏罗纪公园"],
    ["back to the future", "回到未来"], ["the terminator", "终结者"],
    ["the silence of the lambs", "沉默的羔羊"], ["schindler's list", "辛德勒的名单"],
    ["saving private ryan", "拯救大兵瑞恩"], ["the lion king", "狮子王"],
    ["beauty and the beast", "美女与野兽"], ["aladdin", "阿拉丁"],
    ["toy story", "玩具总动员"], ["finding nemo", "海底总动员"],
    ["spirited away", "千与千寻"], ["princess mononoke", "幽灵公主"],
    ["my neighbor totoro", "龙猫"],
    ["civil war", "内战"], ["iron man", "钢铁侠"], ["spider-man", "蜘蛛侠"],
    ["black panther", "黑豹"], ["avengers", "复仇者联盟"],
    ["captain america", "美国队长"], ["thor", "雷神"],
    ["guardians of the galaxy", "银河护卫队"], ["ant-man", "蚁人"],
    ["wonder woman", "神奇女侠"], ["superman", "超人"], ["batman", "蝙蝠侠"],
    ["joker", "小丑"], ["interstellar", "星际穿越"], ["inception", "盗梦空间"],
    ["the prestige", "致命魔术"], ["memento", "记忆碎片"],
    ["fight club", "搏击俱乐部"], ["the social network", "社交网络"],
    ["goodfellas", "好家伙"], ["casino", "赌城风云"],
    ["taxi driver", "出租车司机"], ["raging bull", "愤怒的公牛"],
    ["the departed", "无间道风云"], ["catch me if you can", "猫鼠游戏"],
    ["almost famous", "几近成名"], ["dead man walking", "死囚漫步"],
    ["carlito's way", "情枷爱锁"], ["donnie brasco", "忠奸人"],
    ["the great gatsby", "了不起的盖茨比"],
    ["catcher in the rye", "麦田里的守望者"],
    ["animal farm", "动物庄园"], ["nineteen eighty-four", "一九八四"],
    ["to kill a mockingbird", "杀死一只知更鸟"],
    ["pride and prejudice", "傲慢与偏见"], ["jane eyre", "简·爱"],
    ["wuthering heights", "呼啸山庄"], ["the odyssey", "奥德赛"],
    ["the diary of a young girl", "安妮日记"],
    ["the girl with the dragon tattoo", "龙纹身的女孩"],
    ["the da vinci code", "达·芬奇密码"], ["angels and demons", "天使与魔鬼"],
    ["divergent", "分歧者"], ["insurgent", "反叛者"], ["allegiant", "忠诚者"],
    ["the fault in our stars", "星运里的错"],
    ["the book thief", "偷书贼"], ["the hunger games", "饥饿游戏"],
    ["the witcher", "巫师"], ["game of thrones", "权力的游戏"],
  ];

  /* Title 词表：只放标题常见词，查不到的英文词原样保留 */
  const TITLE_WORDS = {
    "the": "", "a": "", "an": "", "and": "与", "&": "与", "of": "之",
    "in": "在", "on": "之上", "at": "在", "to": "致", "for": "为了",
    "with": "与", "from": "来自", "by": "由", "into": "进入",
    "over": "之上", "under": "之下", "through": "穿越", "between": "之间",
    "before": "之前", "after": "之后", "without": "没有", "against": "对抗",
    "love": "爱", "loves": "爱", "loving": "爱", "story": "故事", "stories": "故事",
    "tales": "故事集", "man": "男人", "men": "男人们", "woman": "女人",
    "women": "女人们", "boy": "男孩", "boys": "男孩们", "girl": "女孩",
    "girls": "女孩们", "child": "孩子", "children": "儿童", "people": "人们",
    "life": "人生", "lives": "人生", "time": "时间", "times": "时代",
    "world": "世界", "house": "房子", "home": "家", "family": "家庭",
    "father": "父亲", "mother": "母亲", "brother": "兄弟", "sister": "姐妹",
    "son": "儿子", "daughter": "女儿", "husband": "丈夫", "wife": "妻子",
    "friend": "朋友", "friends": "朋友", "enemy": "敌人",
    "king": "国王", "queen": "女王", "prince": "王子", "princess": "公主",
    "president": "总统", "doctor": "医生", "teacher": "老师", "student": "学生",
    "police": "警察", "detective": "侦探", "killer": "杀手", "thief": "小偷",
    "pirate": "海盗", "cowboy": "牛仔", "soldier": "士兵", "hero": "英雄",
    "heroes": "英雄", "god": "上帝", "angel": "天使", "devil": "魔鬼",
    "ghost": "幽灵", "spirit": "灵魂", "death": "死亡", "dying": "死去",
    "war": "战争", "peace": "和平", "game": "游戏", "games": "游戏",
    "night": "夜", "day": "白天", "sun": "太阳", "moon": "月亮",
    "star": "星星", "stars": "星辰", "sky": "天空", "sea": "海",
    "ocean": "海洋", "river": "河流", "mountain": "山", "city": "城市",
    "town": "小镇", "village": "村庄", "country": "乡村", "road": "路",
    "train": "火车", "car": "汽车", "plane": "飞机", "ship": "船",
    "book": "书", "books": "书籍", "letter": "信", "letters": "书信",
    "diary": "日记", "secret": "秘密", "secrets": "秘密", "dream": "梦",
    "dreams": "梦想", "hope": "希望", "fear": "恐惧", "fears": "恐惧",
    "heart": "心", "soul": "灵魂", "blood": "血", "fire": "火",
    "ice": "冰", "stone": "石", "ring": "戒指", "sword": "剑",
    "knight": "骑士", "kingdom": "王国", "castle": "城堡", "tower": "塔",
    "dark": "黑暗", "black": "黑", "white": "白", "red": "红",
    "blue": "蓝", "green": "绿", "golden": "金色", "silver": "银色",
    "great": "伟大", "big": "大", "small": "小", "little": "小",
    "beautiful": "美丽", "lovely": "可爱", "strange": "奇异",
    "last": "最后", "first": "第一", "new": "新", "old": "老",
    "young": "年轻", "final": "最终", "lost": "迷失", "hidden": "隐藏",
    "true": "真实", "real": "真实", "happy": "快乐", "sad": "悲伤",
    "angry": "愤怒", "crazy": "疯狂", "silent": "寂静", "wild": "狂野",
    "hot": "热", "cold": "冷", "deep": "深", "high": "高", "long": "长",
    "best": "最佳", "worst": "最差", "better": "更好", "future": "未来",
    "past": "过去", "history": "历史", "legend": "传奇", "myth": "神话",
    "space": "太空", "planet": "星球", "earth": "地球", "universe": "宇宙",
    "heaven": "天堂", "hell": "地狱", "paradise": "天堂",
    "return": "归来", "revenge": "复仇", "escape": "逃脱",
    "rebellion": "反抗", "awakening": "觉醒", "apocalypse": "启示录",
    "machine": "机器", "running": "奔跑", "walking": "行走",
    "dancing": "跳舞", "singing": "歌唱", "falling": "坠落",
    "burning": "燃烧", "fighting": "战斗", "hunting": "狩猎",
    "waiting": "等待", "searching": "寻找", "finding": "寻找",
    "remembering": "回忆", "forgetting": "遗忘", "chasing": "追逐",
    "part": "篇", "chapter": "章", "episode": "集", "volume": "卷",
    "series": "系列", "collection": "合集", "complete": "完整",
    "guide": "指南", "handbook": "手册", "beginner": "入门",
  };

  function escapeRe(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function guessZh(title) {
    if (!title) return "";
    let s = String(title).trim();
    // 末尾括注（年份 / 系列编号）原样保留在中文名之后
    let tail = "";
    const m = s.match(/\s*[（(][^（()）]*[)）]\s*$/);
    if (m) {
      tail = " " + m[0].trim().replace(/^(.*)$/, "（$1）");
      // 若原本已是中文括号就别重复包裹
      if (/^[（(]/.test(m[0].trim())) tail = " " + m[0].trim();
      s = s.slice(0, m.index).trim();
    }
    // "American President, The" -> "American President"
    s = s.replace(/,\s*[Tt]he\s*$/, "");
    for (const [en, zh] of TITLE_PHRASES) {
      s = s.replace(new RegExp(escapeRe(en), "gi"), zh);
    }
    // 词组已替换成中文，剩余按词翻译；英文专有名词原样保留
    let out = s.split(/(\s+)/).map((tok) => {
      if (!tok.trim()) return " ";
      const zh = TITLE_WORDS[tok.toLowerCase().replace(/^[^A-Za-z\u4e00-\u9fff]+|[^A-Za-z\u4e00-\u9fff]+$/g, "")];
      return zh === "" ? "" : (zh || tok);
    }).join("").replace(/\s+/g, " ").trim();
    // 中文之间不留空格："哈利·波特 与 魔法石" -> "哈利·波特与魔法石"
    out = out.replace(/\s+([\u4e00-\u9fff·])/g, "$1")
             .replace(/([\u4e00-\u9fff·])\s+/g, "$1");
    return (out + tail).trim();
  }

  function itemTitle(item) {
    if (!item) return "";
    if (lang === "zh") {
      if (item.title_zh) return item.title_zh;
      const guess = guessZh(item.title);
      if (guess && guess !== item.title) return guess;
    }
    return item.title || "";
  }

  function applyStatic() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
    if (lang === "zh") return;
    document.querySelectorAll("[data-i18n]").forEach((n) => {
      const v = EN[n.getAttribute("data-i18n")];
      if (v != null) n.innerHTML = v;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => {
      const v = EN[n.getAttribute("data-i18n-placeholder")];
      if (v != null) n.setAttribute("placeholder", v);
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

  window.I18N = { t, reason, genre, itemTitle, guessZh, get lang() { return lang; } };

  function boot() {
    buildSwitch();
    applyStatic();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
