"""開催の進み具合（開幕週＝馬場がきれい 〜 最終週＝荒れ）で、走る血統・脚質・枠は変わるか（2026-10-11）.

race_id の日次（DD）で 開幕週(1-2日目)・2週目(3-4)・3週目(5-6)・4週目以降(7〜) に分け、競馬場×芝ダごとに
父の国別タイプ（日本型/米国型/欧州型）・父系統・母父の国別タイプ・脚質（通過順）・枠の3着内A/E（人気からの期待比）を出す。
発見＝2021〜2023年、テスト＝2024〜2026年で、同じ向き（両方1.10以上 / 両方0.90以下）のものに印。複勝回収率も併記。
脚質は当日の通過順（結果）なので「どういう競馬が決まるか」の傾向。予想に使うときは過去の走りから予想した脚質を使う。

使い方: python3 tools/meet_stage_blood.py → docs/analysis/meet_stage_blood.md
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
from keiba.trend import meet_stage  # noqa: E402

DB = ROOT / "data" / "keiba.db"
OUT = ROOT / "docs" / "analysis" / "meet_stage_blood.md"
STAGES = ("開幕週", "2週目", "3週目", "4週目以降")


def main():
    c = sqlite3.connect(DB)
    base = defaultdict(lambda: [0, 0])
    rows = []
    for rid, date, co, su, n, pay, fin, num, gate, pas, pop, sl, dsl, going in c.execute(
            """select ra.race_id,ra.date,ra.course,ra.surface,ra.n_runners,ra.payouts,r.finish,r.number,r.gate,r.passing,
                      r.popularity,h.sire_line,h.damsire_line,ra.going
               from results r join races ra using(race_id) left join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14)
        b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((rid, date, co, su, n, pay, fin, num, gate, pas, p, sl, dsl, going))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    paycache = {}
    st = defaultdict(lambda: [0, 0, 0.0, 0])
    for rid, date, co, su, n, pay, fin, num, gate, pas, p, sl, dsl, going in rows:
        stg = meet_stage(rid)
        if not stg:
            continue
        if rid not in paycache:
            paycache[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = paycache[rid].get(str(num), 0)
        per = "発見" if date < "2024-01-01" else "テスト"
        feats = []
        ct = country_type(sl) if sl else None
        if ct:
            feats.append(("父タイプ", ct))
        if sl:
            feats.append(("父系統", sl))
        dct = country_type(dsl) if dsl else None
        if dct:
            feats.append(("母父タイプ", dct))
        try:
            fr = int(str(pas).split("-")[0]) / (n or 16)
            feats.append(("脚質(結果)", "前35%" if fr <= 0.35 else "後ろ45%" if fr >= 0.55 else "中団"))
        except (ValueError, TypeError):
            pass
        if gate:
            feats.append(("枠", "内1-3" if gate <= 3 else "外7-8" if gate >= 7 else "中4-6"))
        good = (going or "").startswith("良")
        for f in feats:
            for g in ("全馬場", "良のみ"):
                if g == "良のみ" and not good:
                    continue
                s = st[(co, su, stg, f, g, per)]
                s[0] += 1; s[1] += fin <= 3; s[2] += exp[p]; s[3] += fk
    L = ["# 開催の進み具合（開幕週〜最終週）× 血統・脚質・枠（自動生成, tools/meet_stage_blood.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数（1.00が人気どおり）。発見＝2021〜23年 / テスト＝2024〜26年。データは各日の7R以降（未勝利除く）。",
         "- ◎＝両期間とも1.10以上、×＝両期間とも0.90以下。複勝回収率は発見/テスト。脚質は結果の通過順（どういう競馬が決まるか）。", ""]
    for co in ("東京", "中山", "京都", "阪神", "中京", "新潟", "福島", "小倉", "札幌", "函館"):
        for su in ("芝", "ダ"):
            block = []
            for kind in ("脚質(結果)", "枠", "父タイプ", "母父タイプ", "父系統"):
                vals = sorted({k[3][1] for k in st if k[0] == co and k[1] == su and k[3][0] == kind})
                for v in vals:
                    cells = []; mark_any = False
                    for stg in STAGES:
                        a = st.get((co, su, stg, (kind, v), "全馬場", "発見")); b = st.get((co, su, stg, (kind, v), "全馬場", "テスト"))
                        if not a or not b or a[0] < 120 or b[0] < 120:
                            cells.append("-"); continue
                        ra, rb = a[1] / a[2], b[1] / b[2]
                        m = "◎" if ra >= 1.1 and rb >= 1.1 else "×" if ra <= 0.9 and rb <= 0.9 else ""
                        mark_any |= bool(m)
                        cells.append(f"{m}{ra:.2f}/{rb:.2f}（複{a[3]/a[0]:.0f}/{b[3]/b[0]:.0f}%）")
                    if kind == "父系統" and not mark_any:
                        continue
                    if all(x == "-" for x in cells):
                        continue
                    block.append(f"| {kind} | {v} | " + " | ".join(cells) + " |")
            if block:
                L += [f"## {co}{su}", "", "| 区分 | 値 | 開幕週 | 2週目 | 3週目 | 4週目以降 |", "|---|---|---|---|---|---|"] + block + [""]
    # 予想で使う: 両期間とも同じ向き（◎/×）の血統×開催の進み具合（レース前に分かるものだけ）
    kb = {}
    for (co, su, stg, (kind, v), g, per), a in st.items():
        if g != "全馬場" or per != "発見" or kind not in ("父タイプ", "母父タイプ", "父系統"):
            continue
        b = st.get((co, su, stg, (kind, v), g, "テスト"))
        if not b or a[0] < 120 or b[0] < 120:
            continue
        ra, rb = a[1] / a[2], b[1] / b[2]
        if (ra >= 1.1 and rb >= 1.1) or (ra <= 0.9 and rb <= 0.9):
            kb.setdefault(f"{co}{su}|{stg}", []).append(
                {"kind": kind, "value": v, "ae": [round(ra, 2), round(rb, 2)], "n": [a[0], b[0]],
                 "fuku": [round(a[3] / a[0]), round(b[3] / b[0])]})
    (ROOT / "data" / "knowledge" / "meet_stage_blood.json").write_text(json.dumps(kb, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
