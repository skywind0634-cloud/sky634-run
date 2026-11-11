"""5代血統表の祖先・クロスと、コースの形（大箱／小回り）・上がりの関係（2026-10-26, 坂上氏の血統査定の「血の特徴」を検証）.
例: マルゼンスキー・Nijinsky・Princequillo → 大箱向き、Seattle Slew・A.P. Indy → ストライドで東京向き、サンデーサイレンス3×3 → 末脚と気難しさ、
His Majesty/Graustark・Roberto → 馬力・底力（小回り・ハイペース向き）、Fair Trial → 機動力。
芝のみ。3着内A/E（人気からの見込みとの比）と、上がり3位以内の率を、大箱（東京・新潟外・京都外・阪神外）と小回り（中山・福島・小倉・札幌・函館ほか内回り）で比べる。
3期（2021-23 / 2024 / 2025-26）。使い方: python3 tools/ancestor_traits.py <ped5_full.json> → docs/analysis/ancestor_traits.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

ANC = {"マルゼンスキー": ["マルゼンスキー"], "Nijinsky": ["Nijinsky"], "Princequillo": ["Princequillo"],
       "Seattle Slew": ["Seattle Slew"], "A.P. Indy": ["A.P. Indy", "A.P.Indy"], "His Majesty": ["His Majesty"], "Graustark": ["Graustark"],
       "Roberto": ["Roberto"], "Fair Trial": ["Fair Trial"], "トニービン": ["トニービン"], "Lyphard": ["Lyphard"], "Nureyev": ["Nureyev"],
       "Danzig": ["Danzig"], "Sadler's Wells": ["Sadler's Wells"], "Storm Cat": ["Storm Cat"], "Mr. Prospector": ["Mr. Prospector"],
       "ノーザンテースト": ["ノーザンテースト"], "Hyperion": ["Hyperion"], "Busted": ["Busted"]}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pf):
    P = json.load(open(pf)); pos = P["pos"]
    gen = [len(p) for p in pos]
    tags = {}
    for hid, anc in P["horses"].items():
        t = set()
        for k, names in ANC.items():
            if any(a in names for a in anc):
                t.add(k)
        # サンデーサイレンスのクロス（父方・母方の両方にいて、近い方が3代以内）
        ss = [(g, p[0]) for g, p, a in zip(gen, pos, anc) if a == "サンデーサイレンス"]
        if any(s == "S" for _, s in ss) and any(s == "D" for _, s in ss):
            gs = sorted({g for g, s in ss if s == "S"})[0], sorted({g for g, s in ss if s == "D"})[0]
            t.add(f"サンデー{gs[0]}×{gs[1]}" if max(gs) <= 3 else "サンデーのクロス（4代以上）")
        tags[hid] = t
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: r[1:] for r in c.execute("select race_id,date,course,distance,layout from races where surface='芝'")}
    rows = c.execute("select r.race_id,r.horse_id,r.finish,r.popularity,r.last3f from results r where r.finish and r.popularity").fetchall()
    l3 = defaultdict(list)
    for rid, hid, fin, pop, l in rows:
        if rid in races and l:
            l3[rid].append(l)
    base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, l in rows:
        if rid in races:
            b = base[min(pop, 16)]; b[0] += 1; b[1] += fin <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    BIG = {"東京"}; OUTER = {"新潟", "京都", "阪神"}; SMALL = {"中山", "福島", "小倉", "札幌", "函館"}
    agg = defaultdict(lambda: [[0, 0.0, 0, 0] for _ in range(3)])
    for rid, hid, fin, pop, l in rows:
        if rid not in races or hid not in tags:
            continue
        d, co, dist, lay = races[rid]
        lay = lay or ""
        shape = "大箱" if co in BIG or (co in OUTER and "外" in lay) else "小回り" if co in SMALL or "内" in lay else None
        if not shape:
            continue
        top = sorted(l3[rid])[:3]
        for t in tags[hid] | {"（全馬）"}:
            for k in ((t, shape), (t, "東京") if co == "東京" else None):
                if not k:
                    continue
                a = agg[k][per(d)]
                a[0] += fin <= 3; a[1] += exp[min(pop, 16)]; a[2] += 1; a[3] += bool(l and top and l <= top[-1])
    L = ["# 祖先・クロスとコースの形（tools/ancestor_traits.py）", "",
         "芝のみ。3着内A/E（3期: 2021-23 / 2024 / 2025-26）と、上がり3位以内の率。大箱＝東京・新潟/京都/阪神の外回り、小回り＝中山・福島・小倉・札幌・函館と内回り。", "",
         "| 血 | 大箱 A/E（3期） | 大箱 上がり3位内 | 小回り A/E（3期） | 小回り 上がり3位内 | 東京 A/E（3期） | 走数（大箱/小回り） |", "|---|---|---|---|---|---|---|"]
    def f(cs):
        return " / ".join(f"{x[0] / x[1]:.2f}" if x[1] and x[2] >= 40 else "-" for x in cs)
    def tot(cs):
        s = [sum(x[i] for x in cs) for i in range(4)]
        return s
    keys = sorted({k[0] for k in agg}, key=lambda t: -tot(agg[(t, "大箱")])[2])
    for t in keys:
        b, s, tk = agg.get((t, "大箱")), agg.get((t, "小回り")), agg.get((t, "東京"))
        if not b or not s or tot(b)[2] < 150:
            continue
        L.append(f"| {t} | {f(b)} | {tot(b)[3] / tot(b)[2]:.1%} | {f(s)} | {tot(s)[3] / tot(s)[2]:.1%} | {f(tk) if tk else '-'} | {tot(b)[2]}/{tot(s)[2]} |")
    (ROOT / "docs" / "analysis" / "ancestor_traits.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
