"""G1（重賞）の過去の傾向（DB 内の同名レース）. 1〜3着馬の人気・父・母父・系統・前走（レース名・着順・人気）・脚質と、
レース全体の前半/後半3F・ペース型を一覧にし、前走のレース・前走着順・父系統・母父系統・脚質ごとの3着内数と人気からの見込み数（A/E）をまとめる.
使い方: python3 tools/g1_history.py <レース名の一部> [出力名] → docs/analysis/<出力名>.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def main(key, name=None):
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0])
    for p, f in c.execute("select popularity, finish from results where finish is not null and popularity is not null"):
        b = base[min(p, 14)]; b[0] += 1; b[1] += f <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    races = c.execute("select race_id,date,course,distance,layout,going,first3f,last3f,pace_type,n_runners from races where name like ? and grade='G1' order by date",
                      (f"%{key}%",)).fetchall()
    L = [f"# {key} の過去の傾向（自動生成 tools/g1_history.py）", ""]
    agg = defaultdict(lambda: [0, 0, 0.0])
    for rid, date, co, dist, lay, going, f3, l3, pt, n in races:
        L += [f"## {date} {co}芝{dist}{'外' if lay == '外' else '内' if lay == '内' else ''} {going} 前半3F{f3} 後半3F{l3}（{pt}）{n}頭", "",
              "| 着 | 馬 | 人気 | 父 | 母父 | 前走 | 位置取り | 上がり |", "|---|---|---|---|---|---|---|---|"]
        rows = c.execute("select r.horse_id,r.finish,r.popularity,r.passing,r.last3f,h.name,h.sire,h.damsire,h.sire_line,h.damsire_line "
                         "from results r join horses h using(horse_id) where r.race_id=? and r.finish is not null order by r.finish", (rid,)).fetchall()
        for hid, fin, pop, pas, hl3, hn, s, ds, sl, dsl in rows:
            pv = c.execute("select ra.name,ra.course,ra.distance,x.finish,x.popularity,ra.grade from results x join races ra using(race_id) "
                           "where x.horse_id=? and ra.date<? order by ra.date desc limit 1", (hid, date)).fetchone()
            pvs = f"{pv[0]}({pv[1]}{pv[2]}) {pv[3]}着{pv[4]}人" if pv else "DBになし"
            if fin <= 3:
                L.append(f"| {fin} | {hn} | {pop} | {s}（{sl}） | {ds}（{dsl}） | {pvs} | {pas} | {hl3} |")
            if pop is None:
                continue
            e = exp[min(pop, 14)]
            try:
                p0 = int(str(pas).split("-")[0]) / max(n or 16, 1)
                sty = "前15%" if p0 <= 0.15 else "後方40%" if p0 > 0.6 else "中団"
            except ValueError:
                sty = None
            feats = [("父系統", sl), ("母父系統", dsl), ("父の国別タイプ", country_type(sl) if sl else None), ("父", s),
                     ("前走のレース", pv[0] if pv else "DBになし（未勝利・6R以前・海外など）"),
                     ("前走の着順", None if not pv else "1着" if pv[3] == 1 else "2-3着" if pv[3] <= 3 else "4-5着" if pv[3] <= 5 else "6着以下"),
                     ("前走のクラス", None if not pv else "G1" if pv[5] == "G1" else "G2-G3" if pv[5] in ("G2", "G3") else "OP・L" if pv[5] in ("OP", "L") else "条件戦"),
                     ("脚質（このレースの最初のコーナー）", sty), ("人気", "1-3番人気" if pop <= 3 else "4-6番人気" if pop <= 6 else "7番人気以下")]
            for k, v in feats:
                if v:
                    a = agg[(k, v)]; a[0] += 1; a[1] += fin <= 3; a[2] += e
        L.append("")
    L += ["## 特徴ごとの3着内数（A/E＝実数÷人気から見込む数。5回分なので参考）", "", "| 見方 | 値 | 頭数 | 3着内 | A/E |", "|---|---|---|---|---|"]
    for (k, v), a in sorted(agg.items(), key=lambda x: (x[0][0], -x[1][1])):
        if a[1] >= 2 or (a[0] >= 8 and a[1] == 0):
            L.append(f"| {k} | {v} | {a[0]} | {a[1]} | {a[1] / a[2]:.2f} |")
    out = name or "g1_" + key
    (ROOT / "docs" / "analysis" / f"{out}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
