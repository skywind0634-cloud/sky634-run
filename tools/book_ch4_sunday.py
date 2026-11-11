"""第4章 サンデー系（p196-207）の検証（2026-10-12）.
- 父ディープ系: 芝・実際の瞬発/消耗、直線長/短、函館/札幌、福島の1-3番人気（勝率/3着内）、芝1400未満/2500以上、
  ニックス（母父ストームバード系・ヴァイスリージェント系・欧州型ミスプロ・ダンチヒ系）
- 父フジキセキ系: 芝の内枠（1-3枠）/外枠
- 父ステイゴールド系: 芝・中山阪神/その他、内回り（直線短）、道悪、実際の消耗、中3週以内、父ディープ系の1-3番人気が凡走（4着以下）したレースでの3着内
使い方: python3 tools/book_ch4_sunday.py → docs/analysis/book_ch4_sunday.md
"""
import datetime as dt, json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LONG = {"東京", "新潟", "阪神", "京都", "中京"}
STORM = {"ヘネシー系", "テイルオブザキャット系", "ジャイアンツコーズウェイ系", "フォレストリー系", "ハーランズホリデー系", "スキャットダディ系", "ストームキャット系"}
EUMP = {"キングカメハメハ系", "キングマンボ系", "マキャヴェリアン系"}
DANZIG = {"デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); races = defaultdict(list)
    for rid, date, co, su, dist, going, pt, hid, fin, pop, num, gate, sl, dsl, pay in c.execute(
            """select ra.race_id, ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number, r.gate,
                      h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface='芝' and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        races[rid].append((date, co, dist or 1600, going or "良", pt, hid, fin, p, pop, num, gate, sl, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); last = {}
    for rid in sorted(races, key=lambda r: (races[r][0][0], r)):
        rs = races[rid]
        deep_fail = any(x[11] == "ディープインパクト系" and x[8] <= 3 and x[6] >= 4 for x in rs)
        pay = rs[0][13]; fk = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        for date, co, dist, going, pt, hid, fin, p, pop, num, gate, sl, dsl, _ in rs:
            prev = last.get(hid); last[hid] = date
            K = []
            if sl == "ディープインパクト系":
                if pt:
                    K.append(("父ディープ系", f"実際のペース{pt}"))
                K.append(("父ディープ系", f"直線{'長' if co in LONG else '短'}"))
                if co in ("函館", "札幌"):
                    K.append(("父ディープ系", co))
                if co == "福島" and pop <= 3:
                    K.append(("父ディープ系", "福島の1-3番人気"))
                K.append(("父ディープ系", "芝1400未満" if dist < 1400 else "芝2500以上" if dist >= 2500 else "芝1400-2400"))
                for nm, s in (("母父ストームバード系", STORM), ("母父ヴァイスリージェント系", {"デピュティミニスター系"}), ("母父欧州型ミスプロ系", EUMP), ("母父ダンチヒ系", DANZIG)):
                    if dsl in s:
                        K.append(("父ディープ系×" + nm, "芝"))
            if sl == "フジキセキ系" and gate:
                K.append(("父フジキセキ系", "内枠1-3" if gate <= 3 else "外枠6-8" if gate >= 6 else "中枠"))
            if sl == "ステイゴールド系":
                K.append(("父ステイゴールド系", "中山・阪神" if co in ("中山", "阪神") else "その他の場"))
                K.append(("父ステイゴールド系", f"直線{'長' if co in LONG else '短'}"))
                K.append(("父ステイゴールド系", "良" if going.startswith("良") else "道悪"))
                if pt:
                    K.append(("父ステイゴールド系", f"実際のペース{pt}"))
                if prev and (dt.date.fromisoformat(date) - dt.date.fromisoformat(prev)).days <= 28:
                    K.append(("父ステイゴールド系", "中3週以内"))
                if deep_fail:
                    K.append(("父ステイゴールド系", "ディープ系の1-3番人気が4着以下のレース"))
            for k in K:
                x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk.get(str(num), 0)
    L = ["# 第4章 サンデー系（p196-207）の検証（自動生成 tools/book_ch4_sunday.py）", "",
         "- 芝のみ。A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_sunday.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
