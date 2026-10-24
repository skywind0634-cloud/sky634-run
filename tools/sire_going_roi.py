"""種牡馬×馬場（良 / 稍重 / 重・不良）の回収率と3着内A/E（2026-10-24, ユーザー「不良馬場で回収率が上がる種牡馬もある」）.
芝・ダート別。3期（2021-23 / 2024 / 2025-26）で、道悪の単勝・複勝回収率と A/E を出し、良のときと比べる。
「道悪で上がる」= 道悪の A/E が3期とも1.0以上（頭数の少ない期は除く）かつ通算で良より0.10以上高い。
使い方: python3 tools/sire_going_roi.py → docs/analysis/sire_going_roi.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def gk(g):
    g = g or "良"
    return "良" if g.startswith("良") else "稍重" if g.startswith("稍") else "重不良"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    pay = {r[0]: json.loads(r[1]) if r[1] else {} for r in c.execute("select race_id,payouts from races")}
    base = defaultdict(lambda: [0, 0])
    rows = c.execute("select r.race_id,ra.date,ra.surface,ra.going,r.number,r.finish,r.popularity,r.odds,h.sire from results r join races ra using(race_id) "
                     "join horses h using(horse_id) where r.finish is not null and r.popularity is not null and ra.surface in ('芝','ダ')").fetchall()
    for x in rows:
        b = base[min(x[6], 16)]; b[0] += 1; b[1] += x[5] <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    agg = defaultdict(lambda: defaultdict(lambda: [[0, 0.0, 0, 0, 0] for _ in range(3)]))  # top3, exp, n, tan, fuku
    for rid, d, su, g, num, fin, pop, odds, sire in rows:
        fk = {a: y for a, y in pay[rid].get("複勝", [])}
        a = agg[(su, sire)][gk(g)][per(d)]
        a[0] += fin <= 3; a[1] += exp[min(pop, 16)]; a[2] += 1
        a[3] += (odds or 0) * 100 if fin == 1 else 0; a[4] += fk.get(str(num), 0)
    def tot(cs):
        s = [sum(x[i] for x in cs) for i in range(5)]
        return s
    L = ["# 種牡馬×馬場の回収率（tools/sire_going_roi.py）", "",
         "道悪（重・不良）と稍重を、良と比べる。A/E＝3着内の実数÷人気からの見込み。3期＝2021-23 / 2024 / 2025-26。", ""]
    know = {}
    for wet in ("重不良", "稍重"):
        for su in ("ダ", "芝"):
            L += [f"## {su}・{wet}で上がる種牡馬", "", f"| 父 | {wet} A/E（3期） | {wet} 通算 A/E | 良 A/E | {wet} 単勝回収 | {wet} 複勝回収 | 良 複勝回収 | {wet} 頭数 |", "|---|---|---|---|---|---|---|---|"]
            out = []
            for (s_, sire), gs in agg.items():
                if s_ != su or wet not in gs or "良" not in gs:
                    continue
                w = gs[wet]; t = tot(w); gd = tot(gs["良"])
                if t[2] < 60 or gd[2] < 100:
                    continue
                pa = [x[0] / x[1] if x[2] >= 12 and x[1] else None for x in w]
                if not all(v is None or v >= 1.0 for v in pa) or sum(v is not None for v in pa) < 2:
                    continue
                wae, gae = t[0] / t[1], gd[0] / gd[1]
                if wae - gae < 0.10:
                    continue
                out.append((wae, sire, pa, gae, t, gd))
            for wae, sire, pa, gae, t, gd in sorted(out, reverse=True):
                if sire:
                    know.setdefault(su, {}).setdefault(wet, {})[sire] = {"ae": [None if v is None else round(v, 2) for v in pa], "wet": round(wae, 2), "good": round(gae, 2),
                                                                          "tan": round(t[3] / t[2]), "fuku": round(t[4] / t[2]), "n": t[2]}
                L.append(f"| {sire} | " + " / ".join("-" if v is None else f"{v:.2f}" for v in pa) + f" | {wae:.2f} | {gae:.2f} | {t[3] / t[2]:.0f}% | {t[4] / t[2]:.0f}% | {gd[4] / gd[2]:.0f}% | {t[2]} |")
            L.append("")
    json.dump(know, open(ROOT / "data" / "knowledge" / "sire_going.json", "w"), ensure_ascii=False, indent=1)
    (ROOT / "docs" / "analysis" / "sire_going_roi.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
