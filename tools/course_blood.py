"""コース（競馬場×芝ダ×距離）別・ラップ型別の血統傾向（2026-10-15）.
単位: 父 / 父系統 / 母父 / 母父系統 / 5代の祖先（ped5_flags の各フラグ）。
セル: (1) コース＝競馬場×芝ダ×距離 (2) コース×予想展開（前走で前15%にいた馬の数: 前少0-1/普通2-3/前多4+） (3) 芝ダ×距離帯×実際のペース型（理解用）。
採用: 発見2021-23 と 確認2024-26 の両方で A/E 1.10以上（○）または0.90以下（▼）、発見100走以上・確認33走以上、
  かつ 全期間で 人気から見込む3着内数との差が ±10頭以上。
  緩い基準（各20走・1.15・±3頭）では2021-24年で選んだ傾向が2025-26年も同じ向きに出たのは52%（ほぼ偶然）。
  この基準では65%・上積み+4.5%（2021-24年で選び2025-26年で確認）なので、これだけを採用する。
出力: data/knowledge/course_blood.json（予想で使う (1)(2)）, docs/analysis/course_blood.md
使い方: python3 tools/course_blood.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS = json.loads((ROOT / "data" / "knowledge" / "ped5_flags.json").read_text(encoding="utf-8"))["flags"]


TRAIN = __import__('os').environ.get('COURSE_BLOOD_TRAIN') == '1'


def main():
    c = sqlite3.connect(Path(__import__("os").environ.get("ANALYSIS_DB") or (ROOT / "data" / "keiba.db")))
    races = {}
    for rid, date, co, su, dist, pt, n in c.execute("select race_id,date,course,surface,distance,pace_type,n_runners from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, su=su, dist=dist, pt=pt, n=n or 16)
    rows = defaultdict(list)
    base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, pas, sire, sl, ds, dsl in c.execute(
            """select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.passing,h.sire,h.sire_line,h.damsire,h.damsire_line
               from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, p=min(pop, 14), num=num, pas=pas, sire=sire, sl=sl, ds=ds, dsl=dsl))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    last_pos = {}
    agg = defaultdict(lambda: [[0, 0, 0.0], [0, 0, 0.0]])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; rs = rows[rid]
        known = [last_pos[x["hid"]] for x in rs if x["hid"] in last_pos]
        fc = None
        if len(known) >= 0.7 * len(rs):
            nf = sum(1 for v in known if v <= 0.15)
            fc = "前少" if nf <= 1 else "前多" if nf >= 4 else "普通"
        if TRAIN and R["date"] >= "2025-01-01":
            per = None
        else:
            per = (0 if R["date"] < "2023-01-01" else 1) if TRAIN else (0 if R["date"] < "2024-01-01" else 1)
        course = f"{R['co']}{R['su']}{R['dist']}"
        bd = f"{R['su']}{'〜1400' if R['dist'] <= 1400 else '1600-1800' if R['dist'] <= 1800 else '2000-2400' if R['dist'] <= 2400 else '2500〜'}"
        for x in rs:
            units = [("父", x["sire"]), ("父系統", x["sl"]), ("母父", x["ds"]), ("母父系統", x["dsl"])] + [("5代", f) for f in FLAGS.get(x["hid"], [])]
            cells = [("コース", course)]
            if fc:
                cells.append(("コース×展開", f"{course}|{fc}"))
            if R["pt"]:
                cells.append(("距離帯×ペース", f"{bd}|{R['pt']}"))
            e = exp[x["p"]]
            if per is None:
                continue
            for u in units:
                if not u[1]:
                    continue
                for cl in cells:
                    a = agg[(cl, u)][per]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += e
        for x in rs:
            try:
                last_pos[x["hid"]] = int(str(x["pas"]).split("-")[0]) / R["n"]
            except (ValueError, TypeError):
                pass
    out = []
    for (cl, u), (a, b) in agg.items():
        if a[0] < 100 or b[0] < 33 or not a[2] or not b[2]:
            continue
        ra, rb = a[1] / a[2], b[1] / b[2]
        diff = (a[1] + b[1]) - (a[2] + b[2])
        if ((ra >= 1.10 and rb >= 1.10) or (ra <= 0.90 and rb <= 0.90)) and abs(diff) >= 10:
            out.append({"cell": cl[0], "key": cl[1], "unit": u[0], "name": u[1], "ae": [round(ra, 2), round(rb, 2)], "n": [a[0], b[0]], "diff": round(diff, 1)})
    out.sort(key=lambda o: (o["cell"], o["key"], -abs(o["diff"])))
    if TRAIN:  # 未来を見ない確かめ用（2021-22で見つけ2023-24で確認。2025以降は使わない）
        json.dump({"rows": [o for o in out if o["cell"] in ("コース", "コース×展開")]}, open(ROOT / "data" / "cache" / "course_blood_train.json", "w"), ensure_ascii=False)
        print("train", len(out)); return
    (ROOT / "data" / "knowledge" / "course_blood.json").write_text(json.dumps(
        {"_meta": "コース・コース×展開・距離帯×ペース別の血統傾向（2021-23と2024-26の両方で A/E 1.15以上/0.85以下, tools/course_blood.py）",
         "rows": [o for o in out if o["cell"] in ("コース", "コース×展開")], "pace": [o for o in out if o["cell"] == "距離帯×ペース"]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# コース・展開・ラップ型別の血統傾向（自動生成 tools/course_blood.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024-26 の両方で1.10以上（○）または0.90以下（▼）、発見100走・確認33走以上、見込みとの差±10頭以上。",
         "- 緩い基準（各20走・1.15・±3頭）だと、2021-24年で選んだ傾向が2025-26年も同じ向きなのは52%（偶然と同じ）。この基準で65%・上積み+4.5%。",
         "- 展開＝前走で前15%にいた馬の数（前少0-1頭・普通2-3頭・前多4頭以上）。ペース＝確定ラップの型（結果, 理解用）。", ""]
    for cell in ("コース", "コース×展開", "距離帯×ペース"):
        rs = [o for o in out if o["cell"] == cell]
        L += [f"## {cell}（{len(rs)}件）", "", "| 条件 | | 単位 | 血統 | A/E 発見/確認 | 走数 | 見込みとの差 |", "|---|---|---|---|---|---|---|"]
        for o in rs:
            L.append(f"| {o['key']} | {'○' if o['ae'][0] >= 1 else '▼'} | {o['unit']} | {o['name']} | {o['ae'][0]:.2f}/{o['ae'][1]:.2f} | {o['n'][0]}/{o['n'][1]} | {o['diff']:+.1f} |")
        L.append("")
    (ROOT / "docs" / "analysis" / "course_blood.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print({cell: sum(1 for o in out if o["cell"] == cell) for cell in ("コース", "コース×展開", "距離帯×ペース")})


if __name__ == "__main__":
    main()
