"""推荐结果自检：是否混入历史物品、分数是否正常、覆盖率是否合理。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
con = sqlite3.connect(ROOT / "instance" / "recsys.db")

ds = sys.argv[1] if len(sys.argv) > 1 else "movielens"
uid = int(sys.argv[2]) if len(sys.argv) > 2 else 1

seen = {
    r[0]
    for r in con.execute(
        "select item_id from ratings where user_id=? and dataset=?", (uid, ds)
    )
}
print(f"dataset={ds} user={uid} history={len(seen)}")

algos = [r[0] for r in con.execute(
    "select distinct algo from recommendations where dataset=?", (ds,)
)]
for algo in algos:
    rows = con.execute(
        "select item_id, score, rank from recommendations "
        "where user_id=? and dataset=? and algo=? order by rank",
        (uid, ds, algo),
    ).fetchall()
    ids = [r[0] for r in rows]
    scores = [r[1] for r in rows]
    ranks = [r[2] for r in rows]
    overlap = len(seen & set(ids))
    ordered = ranks == sorted(ranks) and ranks == list(range(1, len(ranks) + 1))
    print(
        f"{algo:<10} n={len(ids):>3} overlap_history={overlap:<2} "
        f"rank_ok={ordered} score=[{min(scores) if scores else 0:.3f},"
        f"{max(scores) if scores else 0:.3f}]"
    )
