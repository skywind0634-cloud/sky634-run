"""5代以内のクロス（インブリード）の分析（data/ped5.json が貯まると自動で集計）.

祖先ごと・濃さ（世代の和: 3×3=6 … 5×5=10）ごとに、人気×頭数から期待される3着内数に対する実際の比（人気比）を、
〜2023年 と 2024年〜 で分けて、同じ向きかを確認する。
"""
from __future__ import annotations

from collections import defaultdict

from . import tailfemale as TF

MIN_HORSES = 2000


def _fb(n):
    n = n or 0
    return 0 if n <= 10 else 1 if n <= 14 else 2


def report(conn) -> str:
    h5 = TF.load5()
    L = ["# クロス（インブリード）の分析（自動生成）", ""]
    if len(h5) < MIN_HORSES:
        return "\n".join(L + [f"5代血統表の補完中（{len(h5)} 頭 / 分析開始は {MIN_HORSES} 頭から, tail-female.yml）。", ""])
    rows = conn.execute("""
        SELECT r.horse_id, r.finish, r.popularity, ra.date, ra.n_runners, ra.surface
        FROM results r JOIN races ra ON ra.race_id = r.race_id
        WHERE r.finish > 0 AND r.popularity > 0 AND ra.surface IN ('芝','ダ')""").fetchall()
    pr = defaultdict(lambda: [0, 0])
    for r in rows:
        x = pr[(min(r["popularity"], 16), _fb(r["n_runners"]))]
        x[0] += 1
        x[1] += r["finish"] <= 3
    pe = {k: t / n for k, (n, t) in pr.items()}
    agg = defaultdict(lambda: [0, 0.0, 0])
    nh = defaultdict(set)
    for r in rows:
        h = h5.get(r["horse_id"])
        if h is None:
            continue
        e, top = pe[(min(r["popularity"], 16), _fb(r["n_runners"]))], 1 if r["finish"] <= 3 else 0
        per = "A" if r["date"] < "2024-01-01" else "B"
        xs = [(n, g) for n, g in h["x"] if len(g.split("×")) >= 2]
        keys = [("有無", "クロスあり" if xs else "クロスなし")]
        best = min((sum(int(v) for v in g.split("×")) for _, g in xs), default=None)
        if best is not None:
            keys.append(("最も濃いクロス", f"世代の和 {best}" if best >= 7 else "世代の和 6以下（3×3など）"))
        for n, g in xs[:3]:
            keys.append(("祖先", n))
            keys.append(("祖先×芝ダ", f"{n} / {r['surface']}"))
        for k in keys:
            for p in (per, "all"):
                x = agg[(p,) + k]
                x[0] += top
                x[1] += e
                x[2] += 1
            nh[k].add(r["horse_id"])
    L += [f"- 5代血統表のある馬: {len(h5)} 頭。**人気比** = 実際の3着内数 / 人気×頭数から期待される数。", "",
          "| 区分 | 値 | 頭数 | 走 | 人気比(全) | 〜2023 | 2024〜 |", "|---|---|--:|--:|--:|--:|--:|"]
    items = []
    for k, x in agg.items():
        if k[0] != "all" or x[2] < 150:
            continue
        a, b = agg.get(("A",) + k[1:]), agg.get(("B",) + k[1:])
        ra = a[0] / a[1] if a and a[2] >= 60 else None
        rb = b[0] / b[1] if b and b[2] >= 60 else None
        order = {"有無": 0, "最も濃いクロス": 1, "祖先": 2, "祖先×芝ダ": 3}[k[1]]
        items.append((order, -x[2], k, x, ra, rb))
    for order, _, k, x, ra, rb in sorted(items)[:80]:
        same = "◎" if ra and rb and (ra - 1) * (rb - 1) > 0 and abs(ra - 1) >= 0.04 and abs(rb - 1) >= 0.04 else ""
        f = lambda v: f"{v:.2f}" if v else "-"
        L.append(f"| {k[1]} | {k[2]} | {len(nh[k[1:]])} | {x[2]} | {x[0] / x[1]:.2f} | {f(ra)} | {f(rb)}{same} |")
    L += ["", "◎ = 両期間で同じ向きに±4%以上。", ""]
    return "\n".join(L)
