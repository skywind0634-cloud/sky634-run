"""芝2600m以上（長距離）の血統・枠・脚質・前走の傾向（2026-10-21 菊花賞の分析用）.
人気から見込む3着内数との比（A/E）を 2021-23 / 2024-26 の2期間で出す。対象: 7R以降・未勝利除外（DB の範囲）。
使い方: python3 tools/long_distance.py → docs/analysis/long_distance.md"""
import sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0])
    for p, f in c.execute("select popularity, finish from results where finish is not null and popularity is not null"):
        b = base[min(p, 14)]; b[0] += 1; b[1] += f <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    rows = c.execute("""select ra.race_id, ra.date, ra.course, ra.distance, ra.n_runners, ra.grade, r.horse_id, r.finish, r.popularity, r.gate, r.passing, r.age,
                        h.sire, h.damsire, h.sire_line, h.damsire_line
                        from results r join races ra using(race_id) join horses h using(horse_id)
                        where ra.surface='芝' and ra.distance >= 2600 and r.finish is not null and r.popularity is not null""").fetchall()
    agg = defaultdict(lambda: [[0, 0, 0.0] for _ in range(2)])
    for rid, date, co, dist, n, grade, hid, fin, pop, gate, pas, age, s, ds, sl, dsl in rows:
        p = 0 if date < "2024-01-01" else 1
        e = exp[min(pop, 14)]
        pv = c.execute("select ra.distance, x.finish from results x join races ra using(race_id) where x.horse_id=? and ra.date<? order by ra.date desc limit 1", (hid, date)).fetchone()
        try:
            p0 = int(str(pas).split("-")[0]) / max(n or 16, 1); pl = int(str(pas).split("-")[-1]) / max(n or 16, 1)
        except ValueError:
            p0 = pl = None
        feats = [("父系統", sl), ("母父系統", dsl), ("父", s), ("母父", ds), ("父の国別タイプ", country_type(sl) if sl else None),
                 ("母父の国別タイプ", country_type(dsl) if dsl else None),
                 ("枠", "1-2枠" if gate and gate <= 2 else "7-8枠" if gate and gate >= 7 else "3-6枠" if gate else None),
                 ("最初のコーナー", None if p0 is None else "前15%" if p0 <= 0.15 else "後方40%" if p0 > 0.6 else "中団"),
                 ("最後のコーナー", None if pl is None else "前20%" if pl <= 0.2 else "後方50%" if pl > 0.5 else "中団"),
                 ("前走の距離", None if not pv or not pv[0] else "2400以上" if pv[0] >= 2400 else "2000-2200" if pv[0] >= 2000 else "1800以下"),
                 ("前走の着順", None if not pv or pv[1] is None else "1着" if pv[1] == 1 else "2-3着" if pv[1] <= 3 else "4着以下"),
                 ("年齢", f"{age}歳" if age and age <= 5 else "6歳以上"), ("場", co), ("クラス", grade)]
        for k, v in feats:
            if v:
                a = agg[(k, v)][p]; a[0] += 1; a[1] += fin <= 3; a[2] += e
    L = ["# 芝2600m以上の傾向（自動生成 tools/long_distance.py）", "", f"- 出走 {len(rows)} 頭。A/E＝3着内数÷人気から見込む数。2021-23 / 2024-26。両期間とも1.10以上を◎、0.90以下を×。", "",
         "| 見方 | 値 | 頭数 | 3着内 | A/E |", "|---|---|---|---|---|"]
    for (k, v), A in sorted(agg.items(), key=lambda x: (x[0][0], -sum(a[1] for a in x[1]))):
        if min(a[0] for a in A) < 25:
            continue
        ae = [a[1] / max(a[2], 1e-9) for a in A]
        m = "◎" if min(ae) >= 1.1 else "×" if max(ae) <= 0.9 else ""
        L.append(f"| {k} | {v}{m} | " + "/".join(str(a[0]) for a in A) + " | " + "/".join(str(a[1]) for a in A) + " | " + "/".join(f"{x:.2f}" for x in ae) + " |")
    (ROOT / "docs" / "analysis" / "long_distance.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
