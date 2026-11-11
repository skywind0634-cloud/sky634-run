"""7R・8Rで「そのレースの収支がプラスになる確率」が高く、続けても減りにくい買い方を探す（2026-10-24, ユーザー「7R・8Rで当てないと以降は買えない」）.
races.payouts（実払戻）で、人気順だけで組める形（単勝・ワイド・馬連・3連複）を1番人気の単勝オッズ帯ごとに比べる。
「プラス率」＝払戻が投資を上回ったレースの割合。期間は 2021-23 / 2024 / 2025-26。
使い方: python3 tools/early_race_hit.py → docs/analysis/early_race_hit.md
"""
import json, sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pays(p, kind):
    out = {}
    for it in p.get(kind) or []:
        out[tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split()))] = it[1]
    return out


def forms(f):
    """人気→馬番 f から買い目（券種, 組）を作る形の一覧."""
    g = lambda *ps: all(p in f for p in ps)
    F = {}
    if g(1): F["単勝 1人気"] = [("単勝", (f[1],))]
    if g(1): F["複勝 1人気"] = [("複勝", (f[1],))]
    if g(1, 2): F["馬連 1-2人気"] = [("馬連", tuple(sorted((f[1], f[2]))))]
    if g(1, 2, 3): F["ワイド 1-2・1-3・2-3人気"] = [("ワイド", tuple(sorted(c))) for c in combinations((f[1], f[2], f[3]), 2)]
    if g(1, 2, 3): F["ワイド 1-2・1-3人気"] = [("ワイド", tuple(sorted((f[1], f[x])))) for x in (2, 3)]
    if g(1, 2, 3): F["馬連 1-2・1-3・2-3人気"] = [("馬連", tuple(sorted(c))) for c in combinations((f[1], f[2], f[3]), 2)]
    if g(1, 2, 3): F["3連複 1-2-3人気"] = [("3連複", tuple(sorted((f[1], f[2], f[3]))))]
    if g(1, 2, 3, 4): F["3連複 1-2人気-3〜4人気"] = [("3連複", tuple(sorted((f[1], f[2], f[x])))) for x in (3, 4)]
    if g(1, 2, 3, 4, 5, 6): F["3連複 1-2人気-3〜6人気"] = [("3連複", tuple(sorted((f[1], f[2], f[x])))) for x in range(3, 7)]
    if g(1, 2, 3, 4, 5): F["3連複 1人気-2〜5人気BOX(6点)"] = [("3連複", tuple(sorted((f[1],) + c))) for c in combinations([f[x] for x in range(2, 6)], 2)]
    if g(1, 2, 3, 4, 5): F["ワイド 1人気-2〜5人気"] = [("ワイド", tuple(sorted((f[1], f[x])))) for x in range(2, 6)]
    if g(1, 2, 3, 4, 5): F["馬連 1人気-2〜5人気"] = [("馬連", tuple(sorted((f[1], f[x])))) for x in range(2, 6)]
    if g(1, 2, 3, 4, 5): F["3連複 1-2-3人気＋1-2人気-4〜5人気"] = [("3連複", tuple(sorted((f[1], f[2], f[x])))) for x in (3, 4, 5)]
    return F


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = c.execute("select race_id,date,race_no,payouts from races where race_no in (7,8) and payouts is not null").fetchall()
    fav = defaultdict(dict); fo = {}
    for rid, pop, num, odds in c.execute("select race_id,popularity,number,odds from results where popularity is not null"):
        fav[rid][pop] = num
        if pop == 1:
            fo[rid] = odds or 0
    agg = defaultdict(lambda: [[0, 0, 0, 0] for _ in range(3)])  # races, plus, cost, back
    for rid, d, rno, pj in races:
        p = json.loads(pj); f = fav.get(rid) or {}
        o = fo.get(rid, 0)
        band = "1人気2.0倍以下" if o <= 2.0 else "1人気2.1〜3.0倍" if o <= 3.0 else "1人気3.1倍以上"
        P = {k: pays(p, k) for k in ("単勝", "複勝", "ワイド", "馬連", "3連複")}
        for name, T in forms(f).items():
            back = sum(P[k].get(t, 0) for k, t in T); cost = 100 * len(T)
            for b in (band, "全部"):
                x = agg[(name, b)][per(d)]
                x[0] += 1; x[1] += back > cost; x[2] += cost; x[3] += back
    out = ["# 7R・8Rで「そのレースで収支プラス」になりやすい買い方（実払戻・人気順だけで組む形）", "",
           "プラス率＝払戻が投資を上回ったレースの割合。回収率とともに 2021-23 / 2024 / 2025-26。", "",
           "| 買い方 | 1番人気のオッズ | 点数 | プラス率 | 回収率 | レース数 |", "|---|---|---|---|---|---|"]
    rows = []
    for (name, b), cs in agg.items():
        if min(x[0] for x in cs) < 30:
            continue
        pr = [x[1] / x[0] for x in cs]; roi = [x[3] / x[2] for x in cs]
        rows.append((min(roi), name, b, pr, roi, cs))
    for m, name, b, pr, roi, cs in sorted(rows, key=lambda r: -r[0]):
        pts = cs[0][2] / cs[0][0] / 100
        out.append(f"| {name} | {b} | {pts:.0f} | " + " / ".join(f"{v:.0%}" for v in pr) + " | " + " / ".join(f"{v:.0%}" for v in roi) + f" | {sum(x[0] for x in cs)} |")
    (ROOT / "docs" / "analysis" / "early_race_hit.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:30]))


if __name__ == "__main__":
    main()
