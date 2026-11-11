"""第4章 ダンチヒ系（p248-255）の検証（2026-10-13）.
- 父ダンチヒ系（デインヒル系・ウォーフロント系等）: 芝/ダ、2-3歳/4歳以上、芝1400以下/1600以上、直線長/短
- ハービンジャー: 母父サンデー系/キングマンボ系 vs その他、芝・中山/その他、芝・直線長/短、芝・実際の瞬発/持続・消耗、道悪
- 母父デインヒル系: 2-3歳/4歳以上、芝/ダ
- 5代にチーフズクラウン/チーフベアハート: 芝・京都外回り(京都芝1600以上)/その他、ダート
使い方: python3 tools/book_ch4_danzig.py <ped5_full.json> → docs/analysis/book_ch4_danzig.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
DZ = {"デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, pt, hid, fin, pop, num, age, sire, sl, dsl, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number, r.age,
                      h.sire, h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, going or "良", pt, hid, fin, p, num, age, sire, sl, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}
    for date, co, su, dist, going, pt, hid, fin, p, num, age, sire, sl, dsl, pay in rows:
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        names = set(n for n in (H.get(hid) or []) if n)
        ag = "2-3歳" if (age or 9) <= 3 else "4歳以上"
        K = []
        if sl in DZ and sire != "ハービンジャー":
            K += [("父ダンチヒ系(ハービンジャー除く)", f"{su}・{ag}"), ("父ダンチヒ系(ハービンジャー除く)", f"{su}・直線{'長' if co in LONG else '短'}")]
            if su == "芝":
                K.append(("父ダンチヒ系(ハービンジャー除く)", "芝1400以下" if dist <= 1400 else "芝1600以上"))
        if sire == "ハービンジャー" and su == "芝":
            K += [("ハービンジャー", "母父サンデー系/キングマンボ系" if dsl in SS | {"キングカメハメハ系", "キングマンボ系"} else "母父その他"),
                  ("ハービンジャー", "芝・中山" if co == "中山" else "芝・その他の場"), ("ハービンジャー", f"芝・直線{'長' if co in LONG else '短'}"),
                  ("ハービンジャー", f"芝・{'良' if going.startswith('良') else '道悪'}")]
            if pt:
                K.append(("ハービンジャー", "芝・実際の瞬発" if pt == "瞬発" else "芝・実際の持続/消耗/平均"))
        if dsl in DZ:
            K.append(("母父ダンチヒ系", f"{su}・{ag}"))
        if names & {"Chief's Crown", "チーフズクラウン", "チーフベアハート"}:
            K.append(("5代にチーフズクラウン系", ("京都芝1600以上" if co == "京都" and dist >= 1600 else "芝その他") if su == "芝" else "ダート"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 ダンチヒ系（p248-255）の検証（自動生成 tools/book_ch4_danzig.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_danzig.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
