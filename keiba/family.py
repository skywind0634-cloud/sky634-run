"""牝系（ファミリーライン）の条件適性.

同じ母（兄弟）・同じ2代母（一族）の馬が、今回と同じ条件（芝ダ／芝ダ×距離帯／芝ダ×馬場）で
人気から期待される以上に走っているか（実際の3着内数 / 人気からの期待数, 縮約つき対数比）。
その馬自身がその条件を初めて走るとき（初ダート・初距離など）に特に効く（docs/analysis/family.md の検証）。
予想日の前月末までのデータだけを使う（月単位でキャッシュ）。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

from .config import distance_band, going_group

K = 10.0
MIN_N = 3
_CACHE: dict = {}


def lineage(dam: str | None, dd: str | None, tf: dict) -> list[tuple[str, str]]:
    """(段階, 牝祖名): 母（兄弟）・2代母（一族）・3代母・4代母（data/tail_female.json があれば）."""
    out = [("母", dam), ("2代母", dd)]
    deep = tf.get(dd) if dd else None
    if deep:
        out += [("3代母", deep[0]), ("4代母", deep[1])]
    return [(lv, k) for lv, k in out if k]


def cond_keys(surface, distance, going) -> dict:
    if surface not in ("芝", "ダ"):
        return {}
    return {"surface": (surface,), "band": (surface, distance_band(distance or 0)),
            "going": (surface, going_group(going))}


def _pop_expect(conn) -> dict:
    if "pe" not in _CACHE:
        pr = defaultdict(lambda: [0, 0])
        for p, f in conn.execute("SELECT popularity, finish FROM results WHERE popularity > 0 AND finish > 0"):
            x = pr[min(p, 16)]
            x[0] += 1
            x[1] += f <= 3
        _CACHE["pe"] = {k: t / n for k, (n, t) in pr.items()}
    return _CACHE["pe"]


def table(conn, before: str) -> dict:
    """月単位でキャッシュ: {'fam': {(level, 牝系キー, 条件種別, 条件値): [3着内, 期待, 走]}, 'own': {(horse_id, 条件種別, 条件値): [...]}, 'dd': {horse_id: 2代母}}."""
    cut = before[:7] + "-01"
    key = (id(conn), cut)
    if key in _CACHE:
        return _CACHE[key]
    pe = _pop_expect(conn)
    dd = {}
    for hid, ped in conn.execute("SELECT horse_id, pedigree FROM horses"):
        try:
            dd[hid] = json.loads(ped or "{}").get("DD")
        except ValueError:
            dd[hid] = None
    from . import tailfemale
    tf = tailfemale.load()
    fam, own = defaultdict(lambda: [0, 0.0, 0]), defaultdict(lambda: [0, 0.0, 0])
    for r in conn.execute("""
            SELECT r.horse_id, r.finish, r.popularity, ra.surface, ra.distance, ra.going, h.dam
            FROM results r JOIN races ra ON ra.race_id = r.race_id LEFT JOIN horses h ON h.horse_id = r.horse_id
            WHERE ra.date < ? AND r.finish > 0 AND r.popularity > 0""", (cut,)):
        hid, fin, pop, s, d, g, dam = r
        e, top = pe[min(pop, 16)], 1 if fin <= 3 else 0
        for kind, val in cond_keys(s, d, g).items():
            o = own[(hid, kind, val)]
            o[0] += top
            o[1] += e
            o[2] += 1
            for level, fk in lineage(dam, dd.get(hid), tf):
                if fk:
                    a = fam[(level, fk, kind, val)]
                    a[0] += top
                    a[1] += e
                    a[2] += 1
    for k in [k for k in _CACHE if isinstance(k, tuple) and k[0] == id(conn)]:
        del _CACHE[k]   # 前の月のキャッシュは捨てる（メモリ節約）
    _CACHE[key] = {"fam": fam, "own": own, "dd": dd, "tf": tf}
    return _CACHE[key]


KIND_JA = {"surface": "", "band": "", "going": ""}
BAND_JA = {"sprint": "短距離", "mile": "マイル", "middle": "中距離", "long": "長距離"}


def _label(kind, val):
    if kind == "surface":
        return "芝" if val[0] == "芝" else "ダート"
    if kind == "band":
        return f"{'芝' if val[0] == '芝' else 'ダート'}{BAND_JA.get(val[1], val[1])}"
    return f"{'芝' if val[0] == '芝' else 'ダート'}の{'道悪' if val[1] == 'soft' else '良馬場'}"


def family_fit(conn, card: dict, horse_id: str | None, dam: str | None, dd: str | None = None) -> tuple[float, list]:
    """(値, 根拠)。値 = Σ_条件 重み(初めての条件=1.0, 経験あり=0.3) × 平均(母・2代母 の縮約つき対数比)."""
    if conn is None or not card.get("date") or not horse_id:
        return 0.0, []
    t = table(conn, card["date"])
    dd = dd or t["dd"].get(horse_id)
    total, notes = 0.0, []
    for kind, val in cond_keys(card.get("surface"), card.get("distance"), card.get("going")).items():
        o = t["own"].get((horse_id, kind, val), [0, 0.0, 0])
        first = o[2] == 0
        vals = []
        for level, fk in lineage(dam, dd, t["tf"]):
            a = t["fam"].get((level, fk, kind, val))
            if not a:
                continue
            tp, ex, n = a[0] - o[0], a[1] - o[1], a[2] - o[2]
            if n < MIN_N:
                continue
            lv = math.log((tp + K * 0.25) / (ex + K * 0.25))
            vals.append(lv)
            if abs(lv) >= 0.2 and (first or abs(lv) >= 0.35):
                who = f"母{fk}の兄弟" if level == "母" else f"{level}{fk}の一族"
                notes.append(f"{who}は{_label(kind, val)}で{'走る' if lv > 0 else '走らない'}"
                             f"（3着内{tp}/{n}走・人気からの期待{ex:.1f}）{'→ 今回初めての条件' if first else ''}")
        if vals:
            total += (1.0 if first else 0.3) * sum(vals) / len(vals)
    return total, notes


# ---------------------------------------------------------------- レポート（検証つき）

def report(conn, test_from: str = "2023-01-01") -> str:
    """牝系の条件適性が、初めての条件で人気以上に効くかの検証と、有力牝系の一覧 → docs/analysis/family.md."""
    from itertools import groupby
    from . import tailfemale
    tf = tailfemale.load()
    pe = _pop_expect(conn)
    dd = {hid: (json.loads(p or "{}").get("DD") if p else None) for hid, p in conn.execute("SELECT horse_id, pedigree FROM horses")}
    LV = {"母": "母（兄弟）", "2代母": "2代母（一族）", "3代母": "3代母（一族）", "4代母": "4代母（一族）"}
    rows = conn.execute("""
        SELECT r.horse_id, r.finish, r.popularity, ra.date, ra.surface, ra.distance, ra.going, ra.grade, h.dam, h.name
        FROM results r JOIN races ra ON ra.race_id = r.race_id LEFT JOIN horses h ON h.horse_id = r.horse_id
        WHERE r.finish > 0 AND r.popularity > 0 AND ra.surface IN ('芝','ダ') ORDER BY ra.date""").fetchall()
    fam, own = defaultdict(lambda: [0, 0.0, 0]), defaultdict(lambda: [0, 0.0, 0])
    out = defaultdict(lambda: [0, 0.0, 0])
    for date, grp in groupby(rows, key=lambda r: r["date"]):
        grp = list(grp)
        if date >= test_from:
            for r in grp:
                e, top = pe[min(r["popularity"], 16)], r["finish"] <= 3
                for kind, val in cond_keys(r["surface"], r["distance"], r["going"]).items():
                    o = own.get((r["horse_id"], kind, val), [0, 0.0, 0])
                    first = "初めて" if o[2] == 0 else "経験あり"
                    for lv0, fk in lineage(r["dam"], dd.get(r["horse_id"]), tf):
                        level = LV[lv0]
                        a = fam.get((level, fk, kind, val))
                        if not a:
                            continue
                        tp, ex, n = a[0] - o[0], a[1] - o[1], a[2] - o[2]
                        if n < MIN_N:
                            continue
                        lv = math.log((tp + K * 0.25) / (ex + K * 0.25))
                        lab = "強い(>+0.25)" if lv > 0.25 else "弱い(<−0.25)" if lv < -0.25 else "中間"
                        x = out[(kind, level, first, lab)]
                        x[0] += top
                        x[1] += e
                        x[2] += 1
        for r in grp:
            e, top = pe[min(r["popularity"], 16)], 1 if r["finish"] <= 3 else 0
            for kind, val in cond_keys(r["surface"], r["distance"], r["going"]).items():
                o = own[(r["horse_id"], kind, val)]
                o[0] += top
                o[1] += e
                o[2] += 1
                for lv0, fk in lineage(r["dam"], dd.get(r["horse_id"]), tf):
                    level = LV[lv0]
                    if fk:
                        a = fam[(level, fk, kind, val)]
                        a[0] += top
                        a[1] += e
                        a[2] += 1
    KJ = {"surface": "芝/ダート", "band": "芝ダ×距離帯", "going": "芝ダ×馬場(良/道悪)"}
    L = ["# 牝系（ファミリーライン）の分析（自動生成）", "",
         f"- 兄弟（同じ母）・一族（同じ2代母, 本馬を除く）が、今回と同じ条件で**人気から期待される以上に**3着内に来ているか（実際/期待）を、"
         f"その時点より前のデータだけで計算。{test_from[:4]}年以降の各レースで、その後の成績を集計した。",
         "- 「初めて」= 本馬がその条件（初芝・初ダート・初距離帯・初道悪など）を初めて走る場合。本馬の実績が無い分、牝系の情報が効く。",
         "- 表の **実際/期待** が1より大きいほど、人気以上に走った。",
         f"- 3代母・4代母は data/tail_female.json（5代血統表から補完, 現在 {len(tf)} 系）がある分だけ。", "",
         "| 条件 | 牝系 | 本馬 | 牝系の評価 | 出走 | 複勝率 | 人気からの期待 | 実際/期待 |", "|---|---|---|---|--:|--:|--:|--:|"]
    for kind in ("surface", "band", "going"):
        for level in LV.values():
            for first in ("初めて", "経験あり"):
                for lab in ("強い(>+0.25)", "中間", "弱い(<−0.25)"):
                    x = out.get((kind, level, first, lab))
                    if x and x[2]:
                        L.append(f"| {KJ[kind]} | {level} | {first} | {lab} | {x[2]} | {x[0] / x[2]:.1%} | "
                                 f"{x[1] / x[2]:.1%} | **{x[0] / x[1]:.2f}** |")
    # 有力牝系: 2代母ごとの OP 以上での3着内馬・人気比
    OPEN = {"OP", "L", "G3", "G2", "G1"}
    g = defaultdict(lambda: {"horses": set(), "op": set(), "g": set(), "t": 0, "e": 0.0, "n": 0, "cond": defaultdict(lambda: [0, 0.0, 0])})
    for r in rows:
        k = dd.get(r["horse_id"])
        if not k:
            continue
        x = g[k]
        x["horses"].add(r["name"] or r["horse_id"])
        top, e = r["finish"] <= 3, pe[min(r["popularity"], 16)]
        x["t"] += top
        x["e"] += e
        x["n"] += 1
        if top and r["grade"] in OPEN:
            x["op"].add(r["name"] or r["horse_id"])
        if r["finish"] == 1 and r["grade"] in ("G1", "G2", "G3"):
            x["g"].add(r["name"] or r["horse_id"])
        c = x["cond"][(r["surface"], distance_band(r["distance"] or 0))]
        c[0] += top
        c[1] += e
        c[2] += 1
    best = sorted(g.items(), key=lambda kv: (-len(kv[1]["g"]), -len(kv[1]["op"]), -(kv[1]["t"] / max(kv[1]["e"], 1e-6))))
    L += ["", "## 有力馬を出し続けている牝系（2代母別, 取り込み済み期間の第7R以降）", "",
          "| 2代母 | 頭数 | 重賞勝ち馬 | OP以上で3着内の馬 | 3着内/走 | 人気比 | 得意な条件（人気比, 走） |", "|---|--:|---|---|--:|--:|---|"]
    for k, x in best[:60]:
        if not x["op"]:
            continue
        conds = sorted(((c[0] + K * 0.25) / (c[1] + K * 0.25), cc, c[2]) for cc, c in x["cond"].items() if c[2] >= 8)
        good = "、".join(f"{'芝' if cc[0] == '芝' else 'ダ'}{BAND_JA.get(cc[1], cc[1])}({v:.2f},{n})" for v, cc, n in conds[::-1][:2] if v > 1.1)
        L.append(f"| {k} | {len(x['horses'])} | {'、'.join(sorted(x['g'])[:4]) or '-'} | {'、'.join(sorted(x['op'] - x['g'])[:5]) or '-'} | "
                 f"{x['t']}/{x['n']} | {x['t'] / max(x['e'], 1e-6):.2f} | {good or '-'} |")
    L.append("")
    return "\n".join(L)
