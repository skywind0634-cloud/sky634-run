"""第4章 サンデー系その他（p208-221）の検証（2026-10-12）.
ゴールドアリュール系: ダート特別戦/平場、東京ダ1600・京都ダ1400・中山ダ1200 / ネオユニヴァース系: 芝の中山・札幌、道悪、ダートの特別戦、勝ち切れず2-3着
ハーツクライ系: 芝2200以上×4歳以上、東京芝、芝2500、1番人気/2番人気以下 / マンハッタンカフェ: 芝の非根幹(1400/1800/2200)、函館芝、前走中団より前×芝1800
ダイワメジャー: 芝1400以下×2歳-3歳前半/3歳後半以降、ダ1400、芝の道悪 / ブラックタイド系: 平坦ダート・京都ダ1800、芝の非根幹、芝の特別戦
アグネスタキオン(母父): 芝の京都 / ダンスインザダーク(母父): 芝1800以下 / スペシャルウィーク(母父): OP以上
使い方: python3 tools/book_ch4_sunday2.py → docs/analysis/book_ch4_sunday2.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAT = {"京都", "新潟", "札幌", "函館", "小倉", "福島"}
OPEN = {"OP", "L", "G3", "G2", "G1"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); wbase = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, grade, name, n, hid, fin, pop, num, age, pas, sire, sl, ds, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.grade, ra.name, ra.n_runners, r.horse_id, r.finish, r.popularity, r.number, r.age, r.passing,
                      h.sire, h.sire_line, h.damsire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3; w = wbase[p]; w[0] += 1; w[1] += fin == 1
        rows.append((date, co, su, dist or 1600, going or "良", grade, name or "", n or 16, hid, fin, p, pop, num, age, pas, sire, sl, ds, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}; wexp = {p: v[1] / v[0] for p, v in wbase.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0, 0.0] for _ in range(3)]); pc = {}; last = {}
    for date, co, su, dist, going, grade, name, n, hid, fin, p, pop, num, age, pas, sire, sl, ds, pay in rows:
        prev = last.get(hid)
        try:
            pos = int(str(pas).split("-")[0]) / n
        except (ValueError, TypeError):
            pos = None
        last[hid] = pos
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        tok = "特別" if ("クラス" not in name or grade in OPEN) else "平場"
        good = going.startswith("良")
        K = []
        if sl == "ゴールドアリュール系" and su == "ダ":
            K.append(("父ゴールドアリュール系", f"ダ・{tok}"))
            if (co, dist) in (("東京", 1600), ("京都", 1400), ("中山", 1200)):
                K.append(("父ゴールドアリュール系", "東京ダ1600・京都ダ1400・中山ダ1200"))
        if sl == "ネオユニヴァース系":
            if su == "芝":
                K.append(("父ネオユニヴァース系", "芝・中山札幌" if co in ("中山", "札幌") else "芝・その他"))
                K.append(("父ネオユニヴァース系", f"芝・{'良' if good else '道悪'}"))
            else:
                K.append(("父ネオユニヴァース系", f"ダ・{tok}"))
        if sl == "ハーツクライ系" and su == "芝":
            if dist >= 2200 and (age or 0) >= 4:
                K.append(("父ハーツクライ系", "芝2200以上×4歳以上"))
            if co == "東京":
                K.append(("父ハーツクライ系", "東京芝"))
            K.append(("父ハーツクライ系", "芝・1番人気" if pop == 1 else "芝・2番人気以下"))
        if sire == "マンハッタンカフェ" or sl == "マンハッタンカフェ系":
            if su == "芝":
                K.append(("父マンハッタンカフェ系", "芝・非根幹(1400/1800/2200)" if dist in (1400, 1800, 2200) else "芝・その他の距離"))
                if co == "函館":
                    K.append(("父マンハッタンカフェ系", "函館芝"))
        if sire == "ダイワメジャー" and su == "芝":
            if dist <= 1400:
                young = (age or 9) == 2 or ((age or 9) == 3 and date[5:7] <= "06")
                K.append(("ダイワメジャー", "芝1400以下×" + ("2歳-3歳前半" if young else "3歳後半以降")))
            K.append(("ダイワメジャー", f"芝・{'良' if good else '道悪'}"))
        if sire == "ダイワメジャー" and su == "ダ" and dist == 1400:
            K.append(("ダイワメジャー", "ダ1400"))
        if sl == "ブラックタイド系":
            if su == "ダ":
                K.append(("父ブラックタイド系", "平坦ダート" if co in FLAT else "坂のあるダート"))
            else:
                K.append(("父ブラックタイド系", "芝・非根幹" if dist not in (1200, 1600, 2000, 2400) else "芝・根幹"))
                K.append(("父ブラックタイド系", f"芝・{tok}"))
        if ds == "アグネスタキオン" and su == "芝":
            K.append(("母父アグネスタキオン", "芝・京都" if co == "京都" else "芝・その他"))
        if ds == "ダンスインザダーク" and su == "芝":
            K.append(("母父ダンスインザダーク", "芝1800以下" if dist <= 1800 else "芝2000以上"))
        if ds == "スペシャルウィーク":
            K.append(("母父スペシャルウィーク", f"{su}・{'OP以上' if grade in OPEN else '条件戦'}"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += fin == 1; x[5] += wexp[p]
    L = ["# 第4章 サンデー系その他（p208-221）の検証（自動生成 tools/book_ch4_sunday2.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数（勝ちA/Eは1着）。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | 3着内A/E | 勝ちA/E | 複勝回収 |", "|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[4]/x[5]:.2f}" for x in A) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_sunday2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
