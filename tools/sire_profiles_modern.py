"""最新の種牡馬プロファイル（2026-10-12）: 亀谷『血統の教科書』（2018年頃）以降の種牡馬を、産駒の実績から本の枠組みに当てはめる.

- 種牡馬ごとに: 芝率・平均勝ち距離（芝/ダ, SMILE区分）・人気からの3着内A/E（芝/ダ・距離帯・良/道悪・坂/平坦・直線長/短・延長/短縮・2〜3歳/4歳以上）。
- 実績タイプ: 芝率40%未満→ダート型（米国型の働き）、芝で道悪A/Eが良より0.08以上高い→タフ馬場型（欧州型の働き）、芝で直線長A/Eが高く道悪で落ちる→瞬発型（日本型の働き）。
- サンデー系（大系統）は T/P/D（本 p56）: 芝率45%未満→D、芝の平均勝ち距離1800m以上→T、それ以外→P。
- 最新の傾向: 2024年 と 2025-26年 の両方で A/E 1.15以上（○）/0.85以下（▼）の 種牡馬×条件（各60走以上）。
出力: data/knowledge/sire_profiles_modern.json, docs/analysis/sire_profiles_modern.md
使い方: python3 tools/sire_profiles_modern.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

SS_LINES = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
            "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}
SLOPE = {"中山", "阪神", "中京", "東京"}


def smile(d):
    return "S" if d <= 1300 else "M" if d <= 1899 else "I" if d <= 2100 else "L" if d <= 2700 else "E"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    hist = {}
    for date, rid, co, su, dist, going, hid, fin, pop, age, sire, sl in c.execute(
            """select ra.date, ra.race_id, ra.course, ra.surface, ra.distance, ra.going, r.horse_id, r.finish, r.popularity, r.age, h.sire, h.sire_line
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        prev = hist.get(hid); hist[hid] = dist
        rows.append((date, co, su, dist or 1600, going or "良", fin, p, age, sire, sl, prev))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    S = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0]))     # sire -> cond -> [n, top3, exp]
    CROP = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0]))  # sire -> 生まれ年（世代） -> [n, top3, exp]
    R = defaultdict(lambda: defaultdict(lambda: [[0, 0, 0.0], [0, 0, 0.0]]))  # sire -> cond -> [2024, 2025-]
    win = defaultdict(lambda: {"芝": [], "ダ": []}); line = {}; tot = defaultdict(lambda: [0, 0])
    for date, co, su, dist, going, fin, p, age, sire, sl, prev in rows:
        if not sire:
            continue
        line[sire] = sl; tot[sire][0] += 1; tot[sire][1] += su == "芝"
        if fin == 1:
            win[sire][su].append(dist)
        e = exp[p]; good = going.startswith("良")
        if age == 3:   # 世代比較は同じ年齢（3歳時）で揃える（若い世代ほど勝ち上がった馬だけが7R以降に出る偏りを避ける）
            cr = CROP[sire][int(date[:4]) - age]; cr[0] += 1; cr[1] += fin <= 3; cr[2] += e
        bd = (("芝〜1400" if dist <= 1400 else "芝1600-1800" if dist <= 1800 else "芝2000〜") if su == "芝"
              else ("ダ〜1400" if dist <= 1400 else "ダ1600〜"))
        conds = [su, bd, f"{su}・{'良' if good else '道悪'}", f"{su}・{'坂' if co in SLOPE else '平坦'}",
                 f"{su}・直線{'長' if co in LONG else '短'}", f"{su}・{'2-3歳' if (age or 9) <= 3 else '4歳以上'}"]
        if prev and abs(dist - prev) >= 200:
            conds.append(f"{su}・{'延長' if dist > prev else '短縮'}")
        for cd in conds:
            x = S[sire][cd]; x[0] += 1; x[1] += fin <= 3; x[2] += e
            if date >= "2024-01-01":
                y = R[sire][cd][0 if date < "2025-01-01" else 1]; y[0] += 1; y[1] += fin <= 3; y[2] += e
    prof = {}
    for sire, (n, nt) in tot.items():
        if n < 200:
            continue
        A = {cd: round(v[1] / v[2], 2) for cd, v in S[sire].items() if v[0] >= 40 and v[2]}
        tr = nt / n
        wt = sorted(win[sire]["芝"]); wd = sorted(win[sire]["ダ"])
        avg_t = round(sum(wt) / len(wt)) if wt else None
        sl = line.get(sire)
        if tr < 0.40:
            work = "ダート型（米国型の働き）"
        elif A.get("芝・道悪") and A.get("芝・良") and A["芝・道悪"] - A["芝・良"] >= 0.08:
            work = "タフ馬場型（欧州型の働き）"
        elif A.get("芝・直線長") and A.get("芝・道悪") and A.get("芝・良") and A["芝・良"] - A["芝・道悪"] >= 0.08:
            work = "高速馬場型（日本型の働き）"
        else:
            work = "中間"
        tpd = None
        if sl in SS_LINES:
            tpd = "Dサンデー" if tr < 0.45 else "Tサンデー" if (avg_t or 0) >= 1800 else "Pサンデー"
        recent = []
        for cd, (a, b) in R[sire].items():
            if a[0] >= 60 and b[0] >= 60 and a[2] and b[2]:
                ra, rb = a[1] / a[2], b[1] / b[2]
                if (ra >= 1.15 and rb >= 1.15) or (ra <= 0.85 and rb <= 0.85):
                    recent.append({"cond": cd, "ae": [round(ra, 2), round(rb, 2)], "n": [a[0], b[0]]})
        crops = {str(y): [v[0], round(v[1] / v[2], 2)] for y, v in sorted(CROP[sire].items()) if v[0] >= 40 and v[2]}
        trend = None
        ys = sorted(crops)
        if len(ys) >= 3:
            new = crops[ys[-1]][1]; old = sum(crops[y][1] for y in ys[:-1]) / (len(ys) - 1)
            trend = "上昇（最新世代が前の世代より良い）" if new >= old + 0.15 else "下降（最新世代が前の世代より悪い）" if new <= old - 0.15 else None
        prof[sire] = {"crops": crops, "crop_trend": trend, "line": sl, "line_type": country_type(sl) if sl else None, "work_type": work, "tpd": tpd, "n": n,
                      "turf_rate": round(tr, 2), "avg_win_turf": avg_t, "smile_turf": smile(avg_t) if avg_t else None,
                      "avg_win_dirt": round(sum(wd) / len(wd)) if wd else None, "ae": A, "recent": recent}
    (ROOT / "data" / "knowledge" / "sire_profiles_modern.json").write_text(json.dumps(
        {"_meta": "産駒実績からの種牡馬プロファイル（亀谷『血統の教科書』の枠組みを最新種牡馬に適用）。tools/sire_profiles_modern.py", "sires": prof},
        ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# 最新の種牡馬プロファイル（産駒実績から本の枠組みに当てはめ, 自動生成 tools/sire_profiles_modern.py）", "",
         "- 系統タイプ＝系統名からの機械的な国別タイプ。実績タイプ＝産駒の芝率・良/道悪の A/E から見た実際の働き。T/P/D＝サンデー系の3分類（産駒の芝率と芝の平均勝ち距離から）。",
         "- 最新の傾向＝2024年 と 2025-26年 の両方で A/E 1.15以上（○）/0.85以下（▼）の条件。", "",
         "- 世代別＝産駒の生まれ年ごとの3歳時の3着内A/E（同じ年齢で比較, 40走以上の世代）。上昇/下降＝最新世代が前の世代の平均より0.15以上良い/悪い（重賞馬が出て繁殖牝馬の質が変わる等）。", "",
         "| 種牡馬 | 系統 | 系統タイプ | 実績タイプ | T/P/D | 走数 | 芝率 | 芝の平均勝ち距離 | 芝・良/道悪 A/E | 最新の傾向 | 世代別A/E |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for sire, p in sorted(prof.items(), key=lambda x: -x[1]["n"]):
        crop_s = " ".join(str(y) + "年生" + format(v[1], ".2f") for y, v in p["crops"].items()) + (" →" + p["crop_trend"] if p["crop_trend"] else "")
        rec = "、".join(f"{'○' if r['ae'][0] >= 1 else '▼'}{r['cond']} {r['ae'][0]:.2f}/{r['ae'][1]:.2f}" for r in p["recent"])
        L.append(f"| {sire} | {p['line']} | {p['line_type']} | {p['work_type']} | {p['tpd'] or ''} | {p['n']} | {p['turf_rate']:.0%} | "
                 f"{p['avg_win_turf'] or '-'}（{p['smile_turf'] or '-'}） | {p['ae'].get('芝・良', '-')}/{p['ae'].get('芝・道悪', '-')} | {rec} | {crop_s} |")
    (ROOT / "docs" / "analysis" / "sire_profiles_modern.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:70]))


if __name__ == "__main__":
    main()
