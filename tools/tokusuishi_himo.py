"""★特推しの3連複・ワイドの相手（紐）の取り方で、的中率・回収率がどう変わるか（2026-10-31, ユーザー指示）.
10/31 東京8R（3連複5-7-10 20,780円, 3着が5番人気）・京都12R（2-9-11 36,300円, 2着が7番人気）で、★特推しの穴馬は来たのに
3連複の相手（1番人気−2・3番人気）から外れて取りこぼした反省。

★特推しの判定は本番（keiba/digest.py の star_ok・star_boost）と同じ: ★血統穴で、単勝50倍未満かつ13頭以上（重賞は外さない）、
専門家・検証済み・開催×血統○・7〜9番人気の走る条件のどれかと重なる馬。data/cache/tag_rows.json（tools/tag_backtest.py, 2025-10〜2026-09）。
前半（〜2026-03）／後半（2026-04〜）で分けて、両方で崩れない取り方だけを採る。
使い方: python3 tools/tokusuishi_himo.py → docs/analysis/tokusuishi_himo.md
"""
import json
import re
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOST = ("専門家", "検証済み", "開催×血統○", "根拠:7-9番人気としては走る条件")
GRADED = ("G1", "G2", "G3")


def pays(p, k):
    return {tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split())): it[1] for it in p.get(k) or []}


# (名前, ワイドの相手の人気, 3連複の組み方)  3連複: ("fix", [(人気,人気),...]) / ("2nd", 2列目, 3列目) / ("box", 人気の範囲)
PLANS = [
    ("今の形: ワイド1〜3／3連複 1人気−2・3人気（5点）", range(1, 4), ("fix", [(1, 2), (1, 3)])),
    ("ワイド1〜3／3連複 1〜3人気の2頭（6点）", range(1, 4), ("box", range(1, 4))),
    ("ワイド1〜3／3連複 1人気−2〜5人気（7点）", range(1, 4), ("2nd", (1,), range(2, 6))),
    ("ワイド1〜3／3連複 1人気−2〜7人気（9点）", range(1, 4), ("2nd", (1,), range(2, 8))),
    ("ワイド1〜3／3連複 1〜2人気−1〜5人気（10点）", range(1, 4), ("2nd", (1, 2), range(1, 6))),
    ("ワイド1〜5／3連複 1〜2人気−1〜4人気（10点）", range(1, 6), ("2nd", (1, 2), range(1, 5))),
    ("ワイド1〜3／3連複 1〜4人気の2頭（9点）", range(1, 4), ("box", range(1, 5))),
    ("ワイド1〜3／3連複 1〜2人気−3〜7人気（13点）", range(1, 4), ("2nd", (1, 2), range(3, 8))),
    ("ワイド1〜3／3連複 1〜5人気の2頭（13点）", range(1, 4), ("box", range(1, 6))),
    ("ワイド1〜3だけ（3点）", range(1, 4), None),
    ("ワイド1〜5だけ（5点）", range(1, 6), None),
]


def tickets(ax, num, wide, trio):
    tk = [("W", tuple(sorted((num[ax], num[q])))) for q in wide if q in num and q != ax]
    if trio:
        if trio[0] == "fix":
            pairs = set(trio[1])
        elif trio[0] == "2nd":
            pairs = {tuple(sorted((x, y))) for x in trio[1] for y in trio[2] if x != y}
        else:
            pairs = set(combinations(trio[1], 2))
        tk += list({("T", tuple(sorted((num[ax], num[x], num[y])))) for x, y in pairs if ax not in (x, y) and x in num and y in num})
    return tk


def main():
    rows = [r for r in json.load(open(ROOT / "data" / "cache" / "tag_rows.json")) if r.get("pop")]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: (r[1], json.loads(r[2]) if r[2] else {}) for r in c.execute("select race_id,grade,payouts from races")}
    num = {(r[0], r[1]): r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
    by_race = defaultdict(list)
    for r in rows:
        by_race[r["rid"]].append(r)
    agg = defaultdict(lambda: [[0, 0, 0, 0, []] for _ in range(2)])   # races, cost, back, hit, backs
    n_ax = [0, 0]
    for rid, hs in by_race.items():
        if rid not in info:
            continue
        grade, p = info[rid]
        if not p.get("3連複"):
            continue
        W, T = pays(p, "ワイド"), pays(p, "3連複")
        nm = {q: num[(rid, q)] for q in range(1, 19) if (rid, q) in num}
        half = 0 if hs[0]["date"] < "2026-04-01" else 1
        for h in hs:
            tags = h["tags"]
            if "★血統穴" not in tags:
                continue
            if grade not in GRADED and ((h.get("odds") or 999) >= 50 or h["n"] <= 12):
                continue
            if not any(t.startswith(b) for t in tags for b in BOOST):
                continue
            n_ax[half] += 1
            for name, wide, trio in PLANS:
                tk = tickets(h["pop"], nm, wide, trio)
                back = sum((W if k == "W" else T).get(t, 0) for k, t in tk)
                x = agg[name][half]
                x[0] += 1; x[1] += 100 * len(tk); x[2] += back; x[3] += back > 0
                if back:
                    x[4].append(back)
    L = ["# ★特推しの紐（相手）の取り方（tools/tokusuishi_himo.py）", "",
         f"★特推し {n_ax[0]} 頭（前半 2025-10〜2026-03）／{n_ax[1]} 頭（後半 2026-04〜09）。実際の払戻。的中＝1点でも当たった割合。", "",
         "| 紐の取り方 | 1頭あたりの点数 | 回収率（前半/後半） | 的中率（前半/後半） | 的中時の払戻の中央値 |", "|---|---|---|---|---|"]
    for name, _, _ in PLANS:
        x = agg[name]
        if not x[0][0] and not x[1][0]:
            continue
        pts = sum(v[1] for v in x) / 100 / max(sum(v[0] for v in x), 1)
        bk = sorted(b for v in x for b in v[4])
        med = bk[len(bk) // 2] if bk else 0
        L.append(f"| {name} | {pts:.1f} | " + " / ".join(f"{v[2] / v[1]:.0%}" if v[1] else "-" for v in x)
                 + " | " + " / ".join(f"{v[3] / v[0]:.0%}" if v[0] else "-" for v in x) + f" | {med:,}円 |")
    (ROOT / "docs" / "analysis" / "tokusuishi_himo.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
