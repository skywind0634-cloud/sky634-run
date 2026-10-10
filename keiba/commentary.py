"""1頭ごとの血統考察（文章）と評価（★・距離/スピード/底力/コース）を血統DBから作る.

材料: 父・母父の特徴（sires.json）、父の条件別実績（DB）、兄弟（同じ母）・一族（2代母〜）の成績、
5代以内のクロス（ped5.json）、牝系名（female_families.json）、このレース・コースでの本馬の実績、予想モデルの各要素。
評価は出走馬の中での相対評価（◎ 上位2割 / ○ 次の4割 / △ 残り、★は0.5刻みの5段階）。
"""
from __future__ import annotations

import json
import math

from . import knowledge as K
from . import tailfemale as TF
from .config import distance_band

BAND_JA = {"sprint": "短距離", "mile": "マイル", "middle": "中距離", "long": "長距離"}
OPEN = ("OP", "L", "G3", "G2", "G1")


def _relatives(conn, dam, dd, horse_id, limit=3):
    """兄弟（同じ母）と一族（同じ2代母）の主な成績."""
    out = {"sib": [], "fam": []}
    if conn is None:
        return out
    rows = conn.execute("""
        SELECT h.horse_id, h.name, h.dam, h.pedigree, ra.grade, ra.name AS rname, r.finish, ra.surface, ra.distance
        FROM horses h JOIN results r ON r.horse_id = h.horse_id JOIN races ra ON ra.race_id = r.race_id
        WHERE h.horse_id != ? AND (h.dam = ? OR h.pedigree LIKE ?)""", (horse_id or "", dam or "~", f'%"DD": "{dd}"%' if dd else "~")).fetchall()
    best = {}
    for r in rows:
        rank = {"G1": 6, "G2": 5, "G3": 4, "L": 3, "OP": 2}.get(r["grade"], 1 if r["finish"] == 1 else 0)
        if r["finish"] and r["finish"] <= 3 and rank >= 2 or r["finish"] == 1:
            key = r["horse_id"]
            score = rank * 10 + (4 - min(r["finish"], 3))
            if key not in best or score > best[key][0]:
                best[key] = (score, r)
    for score, r in sorted(best.values(), key=lambda x: -x[0]):
        sib = r["dam"] == dam
        desc = (f"{r['rname']}{'(' + r['grade'] + ')' if r['grade'] in OPEN[2:] else ''}"
                f"{'勝ち' if r['finish'] == 1 else str(r['finish']) + '着'}" if score >= 20 else "勝ち上がり")
        (out["sib"] if sib else out["fam"]).append(f"{r['name']}（{desc}）")
    out["sib"], out["fam"] = out["sib"][:limit], out["fam"][:limit]
    return out


def _sire_cond(conn, sire, card):
    """父の、この芝ダ×距離帯・この競馬場での複勝率（全体平均比）."""
    if conn is None or not sire:
        return None
    s, band = card.get("surface"), distance_band(card.get("distance") or 0)
    lo, hi = {"sprint": (0, 1400), "mile": (1401, 1800), "middle": (1801, 2200), "long": (2201, 9999)}[band]
    q = """SELECT COUNT(*), SUM(r.finish<=3) FROM results r JOIN races ra ON ra.race_id=r.race_id JOIN horses h ON h.horse_id=r.horse_id
           WHERE h.sire=? AND ra.surface=? AND ra.distance BETWEEN ? AND ? {extra}"""
    n, t = conn.execute(q.format(extra=""), (sire, s, lo, hi)).fetchone()
    nc, tc = conn.execute(q.format(extra="AND ra.course=?"), (sire, s, lo, hi, card.get("course"))).fetchone()
    base = conn.execute("SELECT AVG(r.finish<=3) FROM results r JOIN races ra ON ra.race_id=r.race_id WHERE ra.surface=?", (s,)).fetchone()[0] or 0.22
    return {"n": n or 0, "rate": (t or 0) / n if n else None, "nc": nc or 0, "rate_c": (tc or 0) / nc if nc else None,
            "base": base, "band": BAND_JA[band]}


def _own_record(conn, horse_id, card):
    if conn is None or not horse_id:
        return []
    rows = conn.execute("""SELECT ra.date, ra.name, ra.grade, r.finish, ra.course, ra.surface, ra.distance
        FROM results r JOIN races ra ON ra.race_id=r.race_id WHERE r.horse_id=? ORDER BY ra.date DESC""", (horse_id,)).fetchall()
    out = []
    for r in rows:
        if r["course"] == card.get("course") and r["surface"] == card.get("surface") and \
                abs((r["distance"] or 0) - (card.get("distance") or 0)) <= 200 and r["finish"] and r["finish"] <= 3:
            out.append(f"{r['date'][:4]}年{r['name']}{'(' + r['grade'] + ')' if r['grade'] in OPEN[2:] else ''}{r['finish']}着")
    return out[:3]


def write(conn, card: dict, entry: dict, h) -> str:
    """望田潤氏の血統評価のような短い考察文."""
    sires = K.sires()
    S = []
    dam, ped = entry.get("dam") or h.__dict__.get("dam"), entry.get("pedigree") or {}
    dd = ped.get("DD")
    rel = _relatives(conn, dam, dd, entry.get("horse_id"))
    if rel["sib"]:
        S.append(f"母{dam}の産駒に{'、'.join(rel['sib'])}。")
    tf = TF.load().get(dd or "") or []
    fam, _b = K.detect_family(ped, dam)
    if rel["fam"] or fam:
        txt = f"2代母{dd}の一族" + (f"に{'、'.join(rel['fam'])}" if rel["fam"] else "")
        if fam:
            txt += f"（{fam}系: {K.families()[fam].get('trait', '')}）"
        S.append(txt + "。")
    elif tf and tf[0]:
        S.append(f"牝系は2代母{dd}、3代母{tf[0]}へと遡る。")
    si = sires.get(h.sire or "", {})
    line = f"父{h.sire}は{h.sire_line}"
    if si.get("note"):
        line += f"で、{si['note']}"
    elif si.get("examples"):
        line += f"で、代表産駒に{'・'.join(si['examples'][:3])}"
    S.append(line + ("" if line.endswith("。") else "。"))
    sc = _sire_cond(conn, h.sire, card)
    if sc and sc["n"] >= 30:
        rel_rate = sc["rate"] / sc["base"] if sc["base"] else 1
        word = "得意" if rel_rate >= 1.15 else "苦手" if rel_rate <= 0.85 else "平均的"
        S.append(f"父の{card.get('surface')}{sc['band']}は複勝率{sc['rate']:.0%}（{sc['n']}走・平均比{rel_rate:.2f}）で{word}"
                 + (f"、{card.get('course')}では{sc['rate_c']:.0%}（{sc['nc']}走）" if sc["nc"] >= 15 else "") + "。")
    ds = sires.get(h.damsire or "", {})
    if h.damsire:
        txt = f"母父{h.damsire}（{h.damsire_line}）"
        if ds.get("as_damsire"):
            txt += f"は{ds['as_damsire']}"
        elif ds.get("note"):
            txt += f"は{ds['note']}"
        S.append(txt + ("" if txt.endswith("。") else "。"))
    xs = [x for x in (h.crosses or [])][:3]
    if xs:
        S.append("クロスは" + "、".join(f"{n} {g}" for n, g in xs) + "。")
    own = _own_record(conn, entry.get("horse_id"), card)
    if own:
        S.append(f"同コース・同距離帯で{'、'.join(own)}の実績。")
    if (entry.get("age") or 0) >= 7:
        S.append(f"{entry['age']}歳。")
    return "".join(S)


def grades(evals, card, conn=None) -> dict:
    """出走馬の中での相対評価: {馬番: {'距離','スピード','底力','コース': ◎○△, '評価': 1.0〜5.0}}."""
    def comp(h, ks):
        return sum(h.components.get(k, 0.0) for k in ks)
    axes = {
        "距離": lambda h: comp(h, ("distance", "dist_data")) + 0.5 * comp(h, ("blood",)),
        "スピード": lambda h: comp(h, ("time_index", "agari", "closing")),
        "底力": lambda h: comp(h, ("form", "margin", "class", "sire_data", "family_fit", "dam_data")),
        "コース": lambda h: comp(h, ("course_type", "sire_course_type", "direction", "course_exp", "repeat_blood",
                                    "course_bias", "draw")),
    }
    n = len(evals)
    out = {h.number: {} for h in evals}
    own = {}
    if conn is not None:   # 同コース・同距離帯で3着内の実績は「コース」に加点
        ids = {e["number"]: e.get("horse_id") for e in card.get("entries", [])}
        own = {h.number: len(_own_record(conn, ids.get(h.number), card)) for h in evals}
    base_course = axes["コース"]
    axes["コース"] = lambda h: base_course(h) + 0.4 * own.get(h.number, 0)
    for ax, f in axes.items():
        for i, h in enumerate(sorted(evals, key=f, reverse=True)):
            out[h.number][ax] = "◎" if i < max(1, round(n * 0.2)) else "○" if i < round(n * 0.6) else "△"
    # 総合評価: 血統要素（50%）と予測勝率（50%）の順位を合成し、0.5刻みの★（5.0〜1.5）
    rb = {h.number: i for i, h in enumerate(sorted(evals, key=lambda h: -h.blood_upside))}
    rp = {h.number: i for i, h in enumerate(sorted(evals, key=lambda h: -h.p_win))}
    for h in evals:
        r = (rb[h.number] + rp[h.number]) / 2 / max(n - 1, 1)
        out[h.number]["評価"] = round(5.0 - r * 3.5, 1) // 0.5 * 0.5
    return out
