"""亀谷『血統の教科書』p56-61 の検証（2026-10-12）.
1) サンデー系3タイプ: T（芝1800m以上: ディープ・ハーツ・ステゴ・スペシャルウィーク系）/ P（芝1600m以下: ダイワメジャー・タキオン・フジキセキ系・マツリダゴッホ）/ D（ダート: ゴールドアリュール・ネオユニヴァース系）
2) 5代血統表にサドラーズウェルズ・ミルリーフを持つ馬は、日本の良の芝ではマイナス、道悪（タフ）ではプラスか
3) 父ノーザンダンサー系（大系統）は芝の道悪でプラスか
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/sunday_tpd.py <ped5_full.json> → docs/analysis/sunday_tpd.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPD_LINE = {"ディープインパクト系": "Tサンデー", "ハーツクライ系": "Tサンデー", "ステイゴールド系": "Tサンデー", "スペシャルウィーク系": "Tサンデー",
            "ダイワメジャー系": "Pサンデー", "アグネスタキオン系": "Pサンデー", "フジキセキ系": "Pサンデー",
            "ゴールドアリュール系": "Dサンデー", "ネオユニヴァース系": "Dサンデー"}
TPD_SIRE = {"マツリダゴッホ": "Pサンデー"}
ND_LINES = {"デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系", "サドラーズウェルズ系", "ガリレオ系", "リファール系", "マルジュ系",
            "ノーザンダンサー系", "デピュティミニスター系", "ヘネシー系", "テイルオブザキャット系", "ジャイアンツコーズウェイ系", "フォレストリー系",
            "ハーランズホリデー系", "スキャットダディ系", "ストームキャット系"}


def tpd(sire, line):
    return TPD_SIRE.get(sire) or TPD_LINE.get(line)


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    P = json.loads(Path(pedpath).read_text(encoding="utf-8")); pos = P["pos"]; H = P["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for rid, date, co, su, dist, going, hid, fin, pop, num, sire, sl, pay in c.execute(
            """select ra.race_id, ra.date, ra.course, ra.surface, ra.distance, ra.going, r.horse_id, r.finish, r.popularity, r.number, h.sire, h.sire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((rid, date, co, su, dist or 1600, going or "良", hid, fin, p, num, sire, sl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    pc = {}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)])
    for rid, date, co, su, dist, going, hid, fin, p, num, sire, sl, pay in rows:
        if rid not in pc:
            pc[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[rid].get(str(num), 0)
        good = going.startswith("良")
        if su == "芝":
            cond = "芝〜1400" if dist <= 1400 else "芝1600" if dist <= 1600 else "芝1800-2000" if dist <= 2000 else "芝2200〜"
        else:
            cond = "ダート"
        keys = []
        t = tpd(sire, sl)
        if t:
            keys.append(("サンデー3タイプ", t, cond))
        names = H.get(hid)
        if names:
            a = set(n for n in names if n)
            sw = "Sadler's Wells" in a or "サドラーズウェルズ" in a
            mr = "Mill Reef" in a or "ミルリーフ" in a
            lab = "サドラーズウェルズかミルリーフを持つ" if (sw or mr) else "どちらも持たない"
            if su == "芝":
                keys.append(("5代血統表", lab, f"芝・{'良' if good else '道悪'}"))
        if sl in ND_LINES and su == "芝":
            keys.append(("父ノーザンダンサー系", "父ノーザンダンサー系", f"芝・{'良' if good else '道悪'}"))
        for k in keys:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# サンデー系3タイプ・サドラーズウェルズ/ミルリーフ・父ノーザンダンサー系（亀谷『血統の教科書』p56-61, 自動生成 tools/sunday_tpd.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.05以上、×＝0.95以下。", "",
         "| 区分 | 値 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 50:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.05 else "×" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + f" | {m}" + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "sunday_tpd.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
