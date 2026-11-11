"""第4章 名牝系・ニジンスキー系・ヴァイスリージェント系（p222-235）の検証（2026-10-12）.
- 5代にニジンスキー/マルゼンスキー: 芝の道悪/良、ダート
- 父サンデー系×5代にカーリアン（ニックス）
- 父/母父ヴァイスリージェント系（デピュティミニスター系・クロフネ等）: 2-3歳/4歳以上、牝/セン/牡、ダートの良/道悪（軽い馬場）、東京ダ1600、
  ダートで前走ダ1700以上からの短縮、芝1200以下、芝の距離短縮
使い方: python3 tools/book_ch4_nd1.py <ped5_full.json> → docs/analysis/book_ch4_nd1.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, hid, fin, pop, num, age, sex, sl, dsl, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, r.horse_id, r.finish, r.popularity, r.number, r.age, r.sex,
                      h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, going or "良", hid, fin, p, num, age, sex or "", sl, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, co, su, dist, going, hid, fin, p, num, age, sex, sl, dsl, pay in rows:
        prev = last.get(hid); last[hid] = (su, dist)
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        names = set(n for n in (H.get(hid) or []) if n)
        good = going.startswith("良")
        K = []
        if names & {"Nijinsky", "ニジンスキー", "マルゼンスキー"}:
            K.append(("5代にニジンスキー/マルゼンスキー", f"{su}・{'良' if good else '道悪'}"))
        if sl in SS and names & {"Caerleon", "カーリアン"}:
            K.append(("父サンデー系×5代にカーリアン", su))
        for who, ln in (("父", sl), ("母父", dsl)):
            if ln != "デピュティミニスター系":
                continue
            w = f"{who}ヴァイスリージェント系"
            K.append((w, f"{su}・{'2-3歳' if (age or 9) <= 3 else '4歳以上'}"))
            K.append((w, f"{su}・{'牝' if sex.startswith('牝') else 'セン' if sex.startswith('セ') else '牡'}"))
            K.append((w, f"{su}・{'良' if good else '道悪'}"))
            if su == "ダ" and co == "東京" and dist == 1600:
                K.append((w, "東京ダ1600"))
            if su == "ダ" and prev and prev[0] == "ダ" and prev[1] >= 1700 and dist <= prev[1] - 200:
                K.append((w, "ダ・前走1700以上から短縮"))
            if su == "芝" and dist <= 1200:
                K.append((w, "芝1200以下"))
            if su == "芝" and prev and dist <= prev[1] - 200:
                K.append((w, "芝・距離短縮"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 名牝系・ニジンスキー系・ヴァイスリージェント系（p222-235）の検証（自動生成 tools/book_ch4_nd1.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_nd1.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
