"""坂上明大「重賞血統査定」の★（適性・能力）が当たっているか（2026-10-27, ユーザー指示「過去の★5を検証して」）.
sky634-run の ratings ブランチ sakagami.json（各記事の馬名と★の数だけ。本文は保存しない）を、DB の結果と馬名＋記事日付から1週間以内のレースで突き合わせる。
★ごとに 3着内率・A/E（人気からの見込みとの比）・単勝/複勝回収率を出す。
使い方: python3 tools/sakagami_check.py <sakagami.json> → docs/analysis/sakagami_check.md
"""
import json, sqlite3, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def main(pf):
    arts = json.load(open(pf))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0])
    for p, f in c.execute("select popularity,finish from results where popularity and finish"):
        b = base[min(p, 16)]; b[0] += 1; b[1] += f <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    agg = defaultdict(lambda: [0, 0, 0.0, 0, 0, 0])
    hits, miss = 0, 0
    detail = []
    for a in arts:
        if not a.get("date"):
            continue
        d0 = date.fromisoformat("-".join(f"{int(x):02d}" if i else x for i, x in enumerate(a["date"].split("-"))))
        for h in a["horses"]:
            if not h.get("name"):
                continue
            r = c.execute("""select r.finish,r.popularity,r.odds,r.number,ra.payouts,ra.name,ra.date from results r join horses hs using(horse_id) join races ra using(race_id)
                             where hs.name=? and ra.date between ? and ? and ra.grade is not null order by ra.date limit 1""",
                          (h["name"], d0.isoformat(), (d0 + timedelta(days=8)).isoformat())).fetchone()
            if not r or not r[0] or not r[1]:
                miss += 1; continue
            hits += 1
            fin, pop, odds, num, pay, rname, rdate = r
            fk = {x: y for x, y in (json.loads(pay) if pay else {}).get("複勝", [])}
            for k in (f"適性★{h['fit']}", f"能力★{h['ability']}", f"適性+能力={h['fit'] + h['ability']}",
                      "適性★5×4番人気以下" if h["fit"] == 5 and pop >= 4 else None, "適性★5×能力★5" if h["fit"] == 5 and h["ability"] == 5 else None):
                if not k:
                    continue
                x = agg[k]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[min(pop, 16)]; x[3] += (odds or 0) * 100 if fin == 1 else 0; x[4] += fk.get(str(num), 0); x[5] += fin == 1
            if h["fit"] == 5:
                detail.append(f"| {rdate} {rname} | {h['name']} | ★{h['fit']}/★{h['ability']} | {pop}番人気 | {fin}着 |")
    L = ["# 坂上明大「重賞血統査定」の★の成績（tools/sakagami_check.py）", "",
         f"記事 {len(arts)}本・DBで結果と結べた馬 {hits}頭（結べなかった {miss}頭: 7R未満・地方・海外・取消など）。A/E＝3着内の実数÷人気からの見込み。", "",
         "| 区分 | 頭数 | 勝ち | 3着内率 | A/E | 単勝回収 | 複勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg, key=lambda k: (k[:2], k)):
        x = agg[k]
        L.append(f"| {k} | {x[0]} | {x[5]} | {x[1] / x[0]:.1%} | {x[1] / x[2]:.2f} | {x[3] / x[0]:.0f}% | {x[4] / x[0]:.0f}% |")
    L += ["", "## 適性★5の馬", "", "| レース | 馬 | ★ | 人気 | 着順 |", "|---|---|---|---|---|"] + sorted(detail)
    (ROOT / "docs" / "analysis" / "sakagami_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:30]))


if __name__ == "__main__":
    main(sys.argv[1])
