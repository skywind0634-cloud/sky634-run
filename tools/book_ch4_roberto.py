"""第4章 ロベルト系（p186-195）の検証（2026-10-12）. 父/母父ロベルト系 × 芝の道悪/良、昇級（前走より上のクラス）、OP以上の6番人気以下（大一番の一発）、
スクリーンヒーロー（1-2勝クラスのダート/芝、ダ1400以下）、エピファネイア・モーリス・シンボリクリスエスの芝道悪/良、母父ブライアンズタイムのOP以上人気薄。
使い方: python3 tools/book_ch4_roberto.py → docs/analysis/book_ch4_roberto.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROB = {"スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"}
GR = {"1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, su, dist, going, grade, hid, fin, pop, num, sire, sl, ds, dsl, pay in c.execute(
            """select ra.date, ra.surface, ra.distance, ra.going, ra.grade, r.horse_id, r.finish, r.popularity, r.number,
                      h.sire, h.sire_line, h.damsire, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, su, dist or 1600, going or "良", grade, hid, fin, p, num, sire, sl, ds, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, su, dist, going, grade, hid, fin, p, num, sire, sl, ds, dsl, pay in rows:
        prev = last.get(hid); last[hid] = grade
        if pay not in pc:
            j = json.loads(pay) if pay else {}
            pc[pay] = ({cc: y for cc, y in j.get("複勝", [])}, {cc: y for cc, y in j.get("単勝", [])})
        fk, tk = pc[pay][0].get(str(num), 0), pc[pay][1].get(str(num), 0)
        g = GR.get(grade, 4); up = prev is not None and g > GR.get(prev, 4)
        K = []
        for who, ln in (("父ロベルト系", sl), ("母父ロベルト系", dsl)):
            if ln in ROB:
                K.append((who, f"{su}・{'良' if going.startswith('良') else '道悪'}"))
                if up:
                    K.append((who, f"{su}・昇級"))
                if g >= 4 and p >= 6:
                    K.append((who, f"{su}・OP以上×6番人気以下"))
        for s in ("エピファネイア", "モーリス", "シンボリクリスエス", "スクリーンヒーロー"):
            if sire == s:
                K.append((s, f"{su}・{'良' if going.startswith('良') else '道悪'}"))
                if up:
                    K.append((s, f"{su}・昇級"))
        if sire == "スクリーンヒーロー" and g <= 2:
            K.append(("スクリーンヒーロー", f"1-2勝クラス・{su}"))
        if sire == "スクリーンヒーロー" and su == "ダ" and dist <= 1400:
            K.append(("スクリーンヒーロー", "ダ1400以下"))
        if ds == "ブライアンズタイム" and g >= 4:
            K.append(("母父ブライアンズタイム", "OP以上×" + ("6番人気以下" if p >= 6 else "5番人気以内")))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    L = ["# 第4章 ロベルト系（p186-195）の検証（自動生成 tools/book_ch4_roberto.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_roberto.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
