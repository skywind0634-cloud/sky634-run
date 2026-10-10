"""国別タイプ（日本型・米国型・欧州型, 亀谷敬正氏の分類の近似 data/knowledge/country_types.json）の分析と要素化.

父・母父の国別タイプ × 条件（芝ダ・距離帯・馬場・直線・坂・距離変化・頭数）ごとに、
人気×頭数から期待される3着内数に対する実際の比（縮約つき）を、予想日の前年末までのデータで計算して要素にする。
docs/analysis/country_types.md に、年ごとの安定性・条件別の傾向・開催の国別タイプの偏りが続くかの検証を出す。
"""
from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

from . import knowledge as K
from .config import distance_band, going_group

K_SHRINK = 300.0
_CACHE: dict = {}


def field_bucket(n) -> int:
    n = n or 0
    return 0 if n <= 10 else 1 if n <= 14 else 2


def conds(surface, distance, going, course, n_runners, dchg) -> dict:
    a = K.course_attrs(course, surface, distance)
    return {"芝ダ": (surface,), "芝ダ×距離帯": (surface, distance_band(distance or 0)),
            "芝ダ×馬場": (surface, "道悪" if going_group(going) == "soft" else "良"), "芝ダ×直線": (surface, "直線" + a["straight_cat"]),
            "芝ダ×坂": (surface, a["slope"]), "芝ダ×頭数": (surface, ("少頭数(〜10)", "中(11-14)", "多頭数(15〜)")[field_bucket(n_runners)]),
            "芝ダ×距離変化": (surface, dchg)}


def _rows(conn, before: str):
    q = """SELECT r.horse_id, r.finish, r.popularity, ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.n_runners,
                  h.sire_line, h.damsire_line
           FROM results r JOIN races ra ON ra.race_id = r.race_id JOIN horses h ON h.horse_id = r.horse_id
           WHERE ra.date < ? AND r.finish > 0 AND r.popularity > 0 AND ra.surface IN ('芝','ダ')
           ORDER BY r.horse_id, ra.date"""
    out, prev = [], {}
    for r in conn.execute(q, (before,)):
        d = dict(r)
        p = prev.get(d["horse_id"])
        d["dchg"] = ("初" if p is None else "延長" if d["distance"] - p >= 100 else "短縮" if d["distance"] - p <= -100 else "同")
        prev[d["horse_id"]] = d["distance"]
        out.append(d)
    return out


def table(conn, before: str) -> dict:
    """年単位でキャッシュ: {(誰, タイプ, 条件名, 条件値): [3着内, 期待]} と人気×頭数の期待率."""
    cut = f"{before[:4]}-01-01"
    key = (id(conn), cut)
    if key in _CACHE:
        return _CACHE[key]
    rows = _rows(conn, cut)
    pr = defaultdict(lambda: [0, 0])
    for r in rows:
        x = pr[(min(r["popularity"], 16), field_bucket(r["n_runners"]))]
        x[0] += 1
        x[1] += r["finish"] <= 3
    pe = {k: t / n for k, (n, t) in pr.items()}
    t = defaultdict(lambda: [0, 0.0])
    for r in rows:
        e = pe[(min(r["popularity"], 16), field_bucket(r["n_runners"]))]
        top = 1 if r["finish"] <= 3 else 0
        ts, td = K.country_type(r["sire_line"]), K.country_type(r["damsire_line"])
        for cn, cv in conds(r["surface"], r["distance"], r["going"], r["course"], r["n_runners"], r["dchg"]).items():
            for who, ty in (("父", ts), ("母父", td), ("父×母父", f"{ts}×{td}" if ts and td else None)):
                if ty:
                    a = t[(who, ty, cn, cv)]
                    a[0] += top
                    a[1] += e
    _CACHE[key] = {"t": t, "pe": pe}
    return _CACHE[key]


def country_fit(conn, card: dict, sire_line, damsire_line, dchg: str | None) -> tuple[float, str | None, list]:
    """(値, タイプ表記, 根拠)。値 = Σ 条件 log(縮約つき 実際/期待)。"""
    ts, td = K.country_type(sire_line), K.country_type(damsire_line)
    label = f"父{ts or '不明'}×母父{td or '不明'}"
    if conn is None or not card.get("date") or not (ts or td):
        return 0.0, label, []
    t = table(conn, card["date"])["t"]
    total, notes = 0.0, []
    for cn, cv in conds(card.get("surface"), card.get("distance"), card.get("going"), card.get("course"),
                        len(card.get("entries") or []), dchg).items():
        for who, ty in (("父", ts), ("母父", td), ("父×母父", f"{ts}×{td}" if ts and td else None)):
            if not ty:
                continue
            a = t.get((who, ty, cn, cv))
            if not a or a[1] < 20:
                continue
            lv = math.log((a[0] + K_SHRINK * 0.25) / (a[1] + K_SHRINK * 0.25))
            total += lv
            if abs(lv) >= 0.04:
                notes.append((abs(lv), f"{who}{ty}は{cn}={'/'.join(map(str, cv))}で人気比{a[0] / a[1]:.2f}"))
    notes.sort(reverse=True)
    return total, label, [n for _, n in notes[:3]]


# ---------------------------------------------------------------- レポート

def report(conn) -> str:
    rows = _rows(conn, "9999-12-31")
    pr = defaultdict(lambda: [0, 0])
    for r in rows:
        x = pr[(min(r["popularity"], 16), field_bucket(r["n_runners"]))]
        x[0] += 1
        x[1] += r["finish"] <= 3
    pe = {k: t / n for k, (n, t) in pr.items()}
    for r in rows:
        r["e"] = pe[(min(r["popularity"], 16), field_bucket(r["n_runners"]))]
        r["top"] = 1 if r["finish"] <= 3 else 0
        r["ts"], r["td"] = K.country_type(r["sire_line"]), K.country_type(r["damsire_line"])
    L = ["# 国別タイプ（日本型・米国型・欧州型）の分析（自動生成）", "",
         "- 系統→国別タイプの割り当ては `data/knowledge/country_types.json`（亀谷敬正氏の分類の近似。SS系は全て日本型、ロベルト系・キングマンボ系は欧州型 など）。",
         "- **人気比** = 実際の3着内数 / 人気×頭数から期待される3着内数（1より大きいほど人気以上に走った）。", ""]
    # 1. 年ごとの安定性
    yrs = sorted({r["date"][:4] for r in rows})
    g = defaultdict(lambda: [0, 0.0, 0])
    for r in rows:
        for who, ty in (("父", r["ts"]), ("母父", r["td"])):
            if ty:
                x = g[(who, ty, r["surface"], r["date"][:4])]
                x[0] += r["top"]
                x[1] += r["e"]
                x[2] += 1
    L += ["## 1. タイプ×芝ダの人気比（年別）", "", "| 誰 | タイプ | 芝ダ | " + " | ".join(yrs) + " |", "|---|---|---|" + "--:|" * len(yrs)]
    for who in ("父", "母父"):
        for ty in ("日本型", "米国型", "欧州型"):
            for s in ("芝", "ダ"):
                cells = []
                for y in yrs:
                    x = g.get((who, ty, s, y))
                    cells.append(f"{x[0] / x[1]:.2f}" if x and x[2] >= 300 else "-")
                L.append(f"| {who} | {ty} | {s} | " + " | ".join(cells) + " |")
    # 2. 条件別（素の複勝率と人気比、前半/後半の再現）
    agg = defaultdict(lambda: [0, 0.0, 0])
    for r in rows:
        per = "A" if r["date"] < "2024-01-01" else "B"
        for cn, cv in conds(r["surface"], r["distance"], r["going"], r["course"], r["n_runners"], r["dchg"]).items():
            for who, ty in (("父", r["ts"]), ("母父", r["td"]), ("父×母父", f"{r['ts']}×{r['td']}" if r["ts"] and r["td"] else None)):
                if ty:
                    for p in (per, "all"):
                        x = agg[(p, who, ty, cn, cv)]
                        x[0] += r["top"]
                        x[1] += r["e"]
                        x[2] += 1
    L += ["", "## 2. タイプ×条件（〜2023 と 2024〜 で同じ向きか）", "",
          "| 誰 | タイプ | 条件 | 走(全) | 複勝率 | 人気比(全) | 〜2023 | 2024〜 |", "|---|---|---|--:|--:|--:|--:|--:|"]
    items = []
    for (p, who, ty, cn, cv), x in agg.items():
        if p != "all" or x[2] < 400 or cn == "芝ダ":
            continue
        a, b = agg.get(("A", who, ty, cn, cv)), agg.get(("B", who, ty, cn, cv))
        if not a or not b or a[2] < 150 or b[2] < 100:
            continue
        ra, rb, rr = a[0] / a[1], b[0] / b[1], x[0] / x[1]
        z = (x[0] - x[1]) / math.sqrt(x[1])
        items.append((abs(z) * (1 if (ra - 1) * (rb - 1) > 0 else 0.3), who, ty, cn, cv, x, rr, ra, rb))
    for _, who, ty, cn, cv, x, rr, ra, rb in sorted(items, key=lambda i: -i[0])[:40]:
        mark = "◎" if (ra - 1) * (rb - 1) > 0 and abs(ra - 1) >= 0.04 and abs(rb - 1) >= 0.04 else ""
        L.append(f"| {who} | {ty} | {cn}={'/'.join(map(str, cv))} | {x[2]} | {x[0] / x[2]:.1%} | {rr:.2f} | {ra:.2f} | {rb:.2f}{mark} |")
    # 3. 開催のタイプ偏りの持続
    import bisect
    by = defaultdict(list)
    for r in rows:
        by[(r["course"], r["surface"])].append(r)
    out = defaultdict(lambda: [0, 0.0, 0])
    for lst in by.values():
        lst.sort(key=lambda r: r["date"])
        dates = [r["date"] for r in lst]
        for ty in ("日本型", "米国型", "欧州型"):
            pt, pex = [0], [0.0]
            for r in lst:
                pt.append(pt[-1] + (r["top"] if r["ts"] == ty else 0))
                pex.append(pex[-1] + (r["e"] if r["ts"] == ty else 0))
            for r in lst:
                if r["ts"] != ty:
                    continue
                since = (dt.date.fromisoformat(r["date"]) - dt.timedelta(days=14)).isoformat()
                i0, i1 = bisect.bisect_left(dates, since), bisect.bisect_left(dates, r["date"])
                T, E = pt[i1] - pt[i0], pex[i1] - pex[i0]
                if E < 3:
                    continue
                ratio = (T + 5 * 0.25) / (E + 5 * 0.25)
                lab = "好調(>1.2)" if ratio > 1.2 else "不調(<0.8)" if ratio < 0.8 else "普通"
                x = out[(ty, lab)]
                x[0] += r["top"]
                x[1] += r["e"]
                x[2] += 1
    L += ["", "## 3. 今の開催で走っているタイプは続くか（直近14日・同じ競馬場×芝ダ → 当日）", "",
          "| 父のタイプ | 直近14日 | 当日の出走 | 人気比 |", "|---|---|--:|--:|"]
    for k in sorted(out):
        x = out[k]
        L.append(f"| {k[0]} | {k[1]} | {x[2]} | {x[0] / x[1]:.3f} |")
    L.append("")
    return "\n".join(L)
