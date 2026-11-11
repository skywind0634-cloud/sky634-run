"""新馬戦の予想（data/knowledge/debut_model.json の学習結果で、出馬表カードの各馬に新馬スコアを付ける）.
使い方: python tools/debut_predict.py <カードのフォルダ>（例: predictions/2026-10-11/debut）"""
from __future__ import annotations

import datetime as dt
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import debut_analysis as A  # noqa: E402
from keiba import knowledge as K  # noqa: E402

M = json.loads((ROOT / "data/knowledge/debut_model.json").read_text(encoding="utf-8"))
W = {tuple(k.split("|", 1)): v for k, v in M["weights"].items()}
SIB = A.sibling_index()


def horse_row(card, e):
    ped = e.get("pedigree") or {}
    fam, _ = K.detect_family(ped, e.get("dam"))
    return {"race_id": card["race_id"], "date": card.get("date") or "9999", "course": card["course"],
            "surface": card["surface"], "distance": card["distance"], "gate": e.get("gate"),
            "sex": e.get("sex"), "weight_carried": e.get("weight"), "body_weight": e.get("body_weight"), "jockey": e.get("jockey"), "trainer": e.get("trainer"), "horse_id": e.get("horse_id"),
            "sire": e.get("sire"), "dam": e.get("dam"), "damsire": e.get("damsire"),
            "sire_line": K.resolve_line(e.get("sire"), ped, "S"), "damsire_line": K.resolve_line(e.get("damsire"), ped, "DS"),
            "family": fam}


def book_notes(card, r):
    """亀谷『血統の教科書』p108-110 を新馬戦データで検証して3期間で一貫したもの（tools/book_ch3e.py）."""
    st, dt_ = K.country_type(r["sire_line"]) if r["sire_line"] else None, K.country_type(r["damsire_line"]) if r["damsire_line"] else None
    su, d = card["surface"], card["distance"]
    out = []
    if su == "芝" and d >= 1600 and r["sire_line"] == "ステイゴールド系":
        out.append("▼新馬の芝1600以上×父ステイゴールド系（A/E 0.87/0.69/0.72・叩き良化型）")
    if su == "ダ" and d <= 1300 and st == "米国型":
        out.append("▽新馬ダ1300以下×父米国型（A/E 0.95/0.93/0.93・人気になりすぎ）")
    if su == "ダ" and d >= 1400 and dt_ == "欧州型":
        out.append("▽新馬ダ1400以上×母父欧州型（A/E 0.84/0.91/0.91）")
    if su == "芝" and d >= 1600 and st == "欧州型":
        out.append("○新馬の芝1600以上×父欧州型（A/E 1.05/1.05/1.08）")
    return out


def main(folder):
    for f in sorted(glob.glob(f"{folder}/*.json")):
        card = json.loads(Path(f).read_text(encoding="utf-8"))
        if card.get("grade") != "新馬" and "新馬" not in (card.get("name") or ""):
            continue
        if not card.get("date"):
            card["date"] = Path(f).parent.name if Path(f).parent.name[:2] == "20" else "9999"
        print(f"### {card['course']}{card['race_no']}R {card['name']} {card['surface']}{card['distance']}m {len(card['entries'])}頭")
        rows = []
        for e in card["entries"]:
            r = horse_row(card, e)
            fs = A.feats(r, SIB)
            parts = sorted(((W.get((k, str(v)), 0), k, v) for k, v in fs.items()), key=lambda x: -abs(x[0]))
            sc = sum(p[0] for p in parts)
            rows.append((sc, e, parts, fs.get("兄姉"), book_notes(card, r)))
        for sc, e, parts, sib, notes in sorted(rows, key=lambda x: -x[0]):
            plus = "、".join(f"{k}={v}({w:+.2f})" for w, k, v in parts if w > 0.02)[:220]
            minus = "、".join(f"{k}={v}({w:+.2f})" for w, k, v in parts if w < -0.02)[:160]
            print(f"  {e['number']:>2} {e['name']} {e.get('popularity')}人気 {e.get('odds')}倍 スコア{sc:+.2f} | 父{e.get('sire')}×母父{e.get('damsire')} {e.get('jockey')} | {sib}")
            if plus:
                print(f"      + {plus}")
            if minus:
                print(f"      - {minus}")
            if notes:
                print("      * 本の検証: " + "、".join(notes))


if __name__ == "__main__":
    main(sys.argv[1])
