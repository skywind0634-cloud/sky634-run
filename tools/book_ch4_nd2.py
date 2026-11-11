"""第4章 リファール系・ノーザンテースト系・ヌレイエフ系（p236-247）の検証（2026-10-12）.
- 父サンデー系×5代にリファール/ダンシングブレーヴ: 芝・実際の瞬発/その他、直線長/短
- 母父キングヘイロー: 距離短縮（とくに1400以下へ）、ダートの外枠
- 5代にノーザンテースト: 3歳 / 4歳 / 5歳以上（二度成長）
- 5代にヌレイエフ: 芝1400-1800 / その他、ダ1400以下 / 母父ヌレイエフ系（ピヴォタル等）・父ファスリエフ
使い方: python3 tools/book_ch4_nd2.py <ped5_full.json> → docs/analysis/book_ch4_nd2.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    P = json.loads(Path(path).read_text(encoding="utf-8")); H = P["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, pt, hid, fin, pop, num, age, sire, sl, ds, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number, r.age,
                      h.sire, h.sire_line, h.damsire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, dist or 1600, pt, hid, fin, p, num, age, sire, sl, ds, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, co, su, dist, pt, hid, fin, p, num, age, sire, sl, ds, pay in rows:
        prev = last.get(hid); last[hid] = (su, dist)
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        names = set(n for n in (H.get(hid) or []) if n)
        K = []
        if sl in SS and su == "芝" and names & {"Lyphard", "リファール", "Dancing Brave", "ダンシングブレーヴ"}:
            K.append(("父サンデー系×5代にリファール系", f"芝・実際のペース{pt}" if pt else "芝・ペース不明"))
            K.append(("父サンデー系×5代にリファール系", f"芝・直線{'長' if co in LONG else '短'}"))
        if ds == "キングヘイロー":
            if prev and dist <= prev[1] - 200:
                K.append(("母父キングヘイロー", f"{su}・距離短縮" + ("（1400以下へ）" if dist <= 1400 else "")))
            if su == "ダ":
                K.append(("母父キングヘイロー", "ダ・外枠（10番以降）" if num >= 10 else "ダ・内中枠"))
        if names & {"Northern Taste", "ノーザンテースト"}:
            K.append(("5代にノーザンテースト", f"{su}・" + ("3歳以下" if (age or 9) <= 3 else "4歳" if age == 4 else "5歳以上")))
        if names & {"Nureyev", "ヌレイエフ"}:
            K.append(("5代にヌレイエフ", ("芝1400-1800" if 1400 <= dist <= 1800 else "芝その他") if su == "芝" else ("ダ1400以下" if dist <= 1400 else "ダ1600以上")))
        if ds in ("ピヴォタル", "Pivotal", "ファスリエフ", "ストラヴィンスキー", "スピニングワールド", "ブラックホーク"):
            K.append(("母父ヌレイエフ系", su))
        if sire == "ファスリエフ" and su == "ダ":
            K.append(("父ファスリエフ", "ダ1400以下" if dist <= 1400 else "ダ1600以上"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 リファール系・ノーザンテースト系・ヌレイエフ系（p236-247）の検証（自動生成 tools/book_ch4_nd2.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_nd2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
