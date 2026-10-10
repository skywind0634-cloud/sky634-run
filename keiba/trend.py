"""傾向の「波」の分析.

1. 同名レースの連続好走血統（リピーター血統）: 過去の同じレースの3着内馬の 父/父系統/母父系統/脚質/枠 を年ごとに並べ、
   直近何年連続で3着内に絡んでいるか（連続年数）を出す。
2. 血統の勢い: 種牡馬・系統の、同じ競馬場×芝ダでの直近1年の複勝率と長期平均との差（上昇中/下降中）。
3. 今の開催の馬場傾向: 同じ競馬場×芝ダの直近14日間の、脚質別・枠別の複勝率（前残り/差し有利、内/外有利）。
いずれも予想対象レースの日付より前のデータだけで計算する（未来の情報は使わない）。
"""
from __future__ import annotations

import datetime as dt
import math
import re
from collections import defaultdict

from .racing import style_from_passing


def norm_race_name(name: str | None) -> str | None:
    if not name:
        return None
    n = re.sub(r"第\d+回", "", name)
    n = re.sub(r"[（(].*?[)）]", "", n)
    n = n.replace("ステークス", "S").replace("カップ", "C").replace("トロフィー", "T")
    return n.strip() or None


def gate_group(g):
    if not g:
        return None
    return "内" if g <= 3 else ("中" if g <= 6 else "外")


def race_history(conn, card: dict, years: int = 8) -> dict | None:
    """同名レース（同じ競馬場・芝ダ）の過去の3着内馬を年ごとに."""
    key = norm_race_name(card.get("name"))
    if not key or not is_named(card.get("name")):
        return None
    rows = conn.execute("""
        SELECT ra.race_id, ra.date, ra.name, r.finish, r.gate, r.passing, ra.n_runners, r.popularity,
               h.sire, h.sire_line, h.damsire, h.damsire_line
        FROM races ra JOIN results r ON r.race_id = ra.race_id LEFT JOIN horses h ON h.horse_id = r.horse_id
        WHERE ra.course = ? AND ra.surface = ? AND ra.date < ? AND r.finish BETWEEN 1 AND 3
        ORDER BY ra.date DESC""", (card.get("course"), card.get("surface"), card.get("date") or "9999")).fetchall()
    by_year = defaultdict(list)
    for r in rows:
        if norm_race_name(r["name"]) != key:
            continue
        st, _ = style_from_passing(r["passing"], r["n_runners"])
        by_year[int(r["date"][:4])].append({
            "finish": r["finish"], "sire": r["sire"], "sire_line": r["sire_line"], "damsire": r["damsire"],
            "damsire_line": r["damsire_line"], "style": st, "gate": gate_group(r["gate"]), "pop": r["popularity"]})
    if not by_year:
        return None
    yrs = sorted(by_year, reverse=True)[:years]
    streaks = {}
    for attr in ("sire", "sire_line", "damsire_line", "style", "gate"):
        vals = {h[attr] for y in yrs for h in by_year[y] if h[attr]}
        for v in vals:
            n = 0
            for y in yrs:   # 直近年から連続して3着内にいる年数
                if any(h[attr] == v for h in by_year[y]):
                    n += 1
                else:
                    break
            total = sum(1 for y in yrs if any(h[attr] == v for h in by_year[y]))
            streaks[(attr, v)] = (n, total)
    return {"key": key, "years": yrs, "by_year": {y: by_year[y] for y in yrs}, "streaks": streaks}


def momentum(conn, who: str, name: str | None, course: str | None, surface: str | None, date: str | None,
             recent_days: int = 365) -> tuple[float, int, float, int] | None:
    """(直近1年の複勝率, 走数, それ以前の複勝率, 走数)."""
    if not name or not date:
        return None
    col = {"sire": "h.sire", "sire_line": "h.sire_line"}[who]
    cut = (dt.date.fromisoformat(date) - dt.timedelta(days=recent_days)).isoformat()
    q = f"""SELECT SUM(ra.date >= ?) AS n1, SUM(ra.date >= ? AND r.finish <= 3) AS t1,
                   SUM(ra.date < ?) AS n0, SUM(ra.date < ? AND r.finish <= 3) AS t0
            FROM results r JOIN races ra ON ra.race_id = r.race_id JOIN horses h ON h.horse_id = r.horse_id
            WHERE {col} = ? AND ra.course = ? AND ra.surface = ? AND ra.date < ?"""
    r = conn.execute(q, (cut, cut, cut, cut, name, course, surface, date)).fetchone()
    if not r or not r[0] or not r[2]:
        return None
    return (r[1] / r[0], r[0], r[3] / r[2], r[2])


def meet_bias(conn, course: str | None, surface: str | None, date: str | None, days: int = 14) -> dict | None:
    """直近 days 日の同じ競馬場×芝ダの、脚質別・枠別の複勝率と全体の複勝率."""
    if not date:
        return None
    since = (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT r.finish, r.gate, r.passing, ra.n_runners FROM results r JOIN races ra ON ra.race_id = r.race_id
        WHERE ra.course = ? AND ra.surface = ? AND ra.date >= ? AND ra.date < ? AND r.finish IS NOT NULL""",
                        (course, surface, since, date)).fetchall()
    if len(rows) < 60:
        return None
    agg = defaultdict(lambda: [0, 0])
    tot = [0, 0]
    for r in rows:
        top = 1 if r["finish"] <= 3 else 0
        tot[0] += 1
        tot[1] += top
        st, _ = style_from_passing(r["passing"], r["n_runners"])
        for k in (("style", "前" if st in ("逃げ", "先行") else "後" if st else None), ("gate", gate_group(r["gate"]))):
            if k[1]:
                agg[k][0] += 1
                agg[k][1] += top
    base = tot[1] / tot[0]
    return {"base": base, "n": tot[0], "rates": {k: (v[1] / v[0], v[0]) for k, v in agg.items() if v[0]}}


# ---------------------------------------------------------------- レポート（検証つき）

GENERIC = ("勝クラス", "新馬", "オープン", "未勝利")


def is_named(name: str | None) -> bool:
    return bool(name) and not any(g in name for g in GENERIC)


def _cell():
    return {"n": 0, "t": 0, "w": 0, "ret": 0.0}


def _add(c, finish, odds):
    c["n"] += 1
    c["t"] += finish is not None and finish <= 3
    if finish == 1:
        c["w"] += 1
        c["ret"] += (odds or 0) * 100
    return c


def _fmt(c, extra: str = "") -> str:
    if not c["n"]:
        return "0 | - | - | -" + extra
    return f"{c['n']} | {c['w'] / c['n']:.1%} | {c['t'] / c['n']:.1%} | {c['ret'] / c['n']:.0f}%" + extra


def _streak(prior_years: list, by_year: dict, attr: str, val) -> tuple[int, int]:
    n = 0
    for y in prior_years:
        if any(h.get(attr) == val and h["finish"] <= 3 for h in by_year[y]):
            n += 1
        else:
            break
    tot = sum(1 for y in prior_years if any(h.get(attr) == val and h["finish"] <= 3 for h in by_year[y]))
    return n, tot


def report(rows: list[dict]) -> str:
    """rows = deep.load_rows(conn). 傾向の波の検証とその時点の傾向一覧 → docs/analysis/trends.md."""
    rows = [dict(r, gate_g=gate_group(r.get("gate")), front=("前" if r["style"] in ("逃げ", "先行") else
                                                                "後" if r["style"] else None))
            for r in rows if r.get("finish")]
    last = max(r["date"] for r in rows)
    L = ["# 傾向の波（連続好走血統・血統の勢い・今の開催の馬場傾向）", "",
         f"- データ: {len(rows)} 走（〜{last}）。すべて**その時点より前のデータだけ**で傾向を計算し、その後の成績で検証。",
         "- 表の列: 出走 | 勝率 | 複勝率 | 単勝回収率", ""]

    # ---- 1. 同名レースの連続好走血統
    races = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if is_named(r.get("race_name")):
            k = (norm_race_name(r["race_name"]), r["course"], r["surface"])
            races[k][int(r["date"][:4])].append(r)
    attrs = [("sire_line", "父系統"), ("damsire_line", "母父系統"), ("sire", "父"), ("gate_g", "枠(内1-3/中4-6/外7-8)")]
    val = {a: defaultdict(_cell) for a, _ in attrs}
    expv = {a: defaultdict(float) for a, _ in attrs}
    arate = {}
    for a, _ in attrs:
        g = defaultdict(lambda: [0, 0])
        for r in rows:
            if r.get(a):
                g[r[a]][0] += 1
                g[r[a]][1] += r["finish"] <= 3
        arate[a] = {v: t / n for v, (n, t) in g.items()}
    for k, by_year in races.items():
        yrs = sorted(by_year)
        for i, y in enumerate(yrs):
            prior = sorted(yrs[:i], reverse=True)[:8]
            if len(prior) < 2:
                continue
            for h in by_year[y]:
                for a, _ in attrs:
                    if not h.get(a) or h[a] == "その他":
                        continue
                    s, _t = _streak(prior, by_year, a, h[a])
                    _add(val[a][min(s, 3)], h["finish"], h.get("odds"))
                    expv[a][min(s, 3)] += arate[a][h[a]]
    L += ["## 1. 同名レースの「連続好走血統」は翌年も走るか（検証）", "",
          "同じレース名・競馬場・芝ダの過去の開催で、直近から何年連続でその属性の馬が3着内に入っていたか（連続年数）ごとに、"
          "その年の出走馬の成績を集計（過去2回以上開催されたレースのみ）。",
          "「期待複勝率」はその属性の全レースでの平均複勝率（主流系統はもともと走るので、その分を差し引いて見るため）。"
          "**実際−期待** がプラスなら、そのレース特有の傾向（波）が翌年も続いたことを意味する。", ""]
    for a, lab in attrs:
        L += [f"### {lab}", "", "| 連続年数 | 出走 | 勝率 | 複勝率 | 単回収 | 期待複勝率 | 実際−期待 |",
              "|---|--:|--:|--:|--:|--:|--:|"]
        for s_ in range(4):
            c = val[a][s_]
            e = expv[a][s_] / c["n"] if c["n"] else 0
            d = c["t"] / c["n"] - e if c["n"] else 0
            L.append(f"| {'3年以上' if s_ == 3 else f'{s_}年'} | {_fmt(c)} | {e:.1%} | {d * 100:+.1f}pt |")
        L.append("")

    # 現在の連続好走（次回の開催の参考）
    cur = []
    for (name, course, surf), by_year in races.items():
        yrs = sorted(by_year, reverse=True)[:8]
        if len(yrs) < 3:
            continue
        found = []
        runners = [h for y in yrs for h in by_year[y]]
        for a, lab in attrs[:3]:
            vs = {h[a] for h in runners if h.get(a) and h["finish"] <= 3 and h[a] != "その他"}
            for v in vs:
                s, t = _streak(yrs, by_year, a, v)
                share = sum(h.get(a) == v for h in runners) / len(runners)
                if s >= 3 and share < 0.35:   # 出走の大半を占める主流系統は「傾向」とは言えないので除く
                    found.append((s, f"{lab} {v} {s}年連続(出走シェア{share:.0%})"))
        if found:
            found.sort(reverse=True)
            cur.append((found[0][0], f"| {name} | {course}{surf} | {yrs[-1]}〜{yrs[0]} ({len(yrs)}回) | "
                                     f"{' / '.join(x for _, x in found[:5])} |"))
    cur.sort(key=lambda x: -x[0])
    L += ["### 現在「3年以上連続」で3着内に絡んでいる血統（直近の開催まで。出走シェア35%以上の主流系統は除外）", "",
          "| レース | コース | 対象年 | 連続好走 |", "|---|---|---|---|"] + [x for _, x in cur[:120]] + [""]

    # ---- 2. 血統の勢い
    import bisect
    hist = defaultdict(list)   # (sire, course, surface) → [(date, top3)]
    for r in sorted(rows, key=lambda r: r["date"]):
        if r.get("sire"):
            hist[(r["sire"], r["course"], r["surface"])].append((r["date"], 1 if r["finish"] <= 3 else 0))
    pref = {}
    for k, lst in hist.items():
        ps = [0]
        for _, t in lst:
            ps.append(ps[-1] + t)
        pref[k] = ([d for d, _ in lst], ps)

    def mom(k, date):
        ds, ps = pref[k]
        i1 = bisect.bisect_left(ds, date)
        cut = (dt.date.fromisoformat(date) - dt.timedelta(days=365)).isoformat()
        i0 = bisect.bisect_left(ds, cut)
        n1, t1, n0, t0 = i1 - i0, ps[i1] - ps[i0], i0, ps[i0]
        return n1, t1, n0, t0

    buckets = ["−5pt以下", "−5〜−2pt", "±2pt", "+2〜+5pt", "+5pt以上"]
    mb = defaultdict(lambda: [_cell(), 0.0, 0.0])
    for r in rows:
        k = (r.get("sire"), r["course"], r["surface"])
        if k not in pref:
            continue
        n1, t1, n0, t0 = mom(k, r["date"])
        if n1 < 10 or n0 < 20:
            continue
        p0 = t0 / n0
        d = (t1 + 20 * p0) / (n1 + 20) - p0
        b = 0 if d <= -0.05 else 1 if d <= -0.02 else 2 if d < 0.02 else 3 if d < 0.05 else 4
        _add(mb[b][0], r["finish"], r.get("odds"))
        mb[b][1] += p0
        mb[b][2] += t1 / n1
    L += ["## 2. 血統の勢い（種牡馬×競馬場×芝ダの直近1年の複勝率 − それ以前の複勝率）", "",
          "勢いの区分ごとに、その後の成績と「長期平均から期待される複勝率」を比較（勢いが続くなら実際>期待）。", "",
          "| 直近1年の上振れ | 出走 | 勝率 | 複勝率 | 単回収 | 以前の複勝率 | 直近1年の複勝率 |", "|---|--:|--:|--:|--:|--:|--:|"]
    for b in range(5):
        c, s, s1 = mb[b]
        L.append(f"| {buckets[b]} | {_fmt(c)} | {(s / c['n']) if c['n'] else 0:.1%} | {(s1 / c['n']) if c['n'] else 0:.1%} |")
    L.append("")
    nd = (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat()
    ups = []
    for k in pref:
        n1, t1, n0, t0 = mom(k, nd)
        if n1 >= 15 and n0 >= 20:
            p0, p1 = t0 / n0, t1 / n1
            z = (t1 - n1 * p0) / math.sqrt(max(n1 * p0 * (1 - p0), 1e-9))
            ups.append((z, k, n1, p1, n0, p0))
    ups.sort(key=lambda x: -x[0])
    hdr = ["| 種牡馬 | コース | 直近1年 出走 | 直近 複勝率 | 以前 出走 | 以前 複勝率 | z |", "|---|---|--:|--:|--:|--:|--:|"]
    row = lambda x: f"| {x[1][0]} | {x[1][1]}{x[1][2]} | {x[2]} | {x[3]:.1%} | {x[4]} | {x[5]:.1%} | {x[0]:+.1f} |"
    L += ["### 今、上昇中の種牡馬（競馬場×芝ダ別, 直近1年15走以上）", ""] + hdr + [row(x) for x in ups[:25]] + [""]
    L += ["### 今、下降中の種牡馬", ""] + hdr + [row(x) for x in ups[::-1][:15]] + [""]

    # ---- 3. 今の開催の馬場傾向
    byday = defaultdict(list)
    for r in rows:
        byday[(r["course"], r["surface"], r["date"])].append(r)
    keys_cs = defaultdict(list)
    for (c, s, d) in byday:
        keys_cs[(c, s)].append(d)
    gv = defaultdict(lambda: defaultdict(_cell))
    fv = defaultdict(lambda: defaultdict(_cell))
    current = []
    for (c, s), ds in keys_cs.items():
        ds.sort()
        for d in ds + [nd]:
            since = (dt.date.fromisoformat(d) - dt.timedelta(days=14)).isoformat()
            prev = [r for dd in ds if since <= dd < d for r in byday[(c, s, dd)]]
            if len(prev) < 60:
                continue
            base = sum(r["finish"] <= 3 for r in prev) / len(prev)
            rate = {}
            for key in ("gate_g", "front"):
                for v in {r[key] for r in prev if r[key]}:
                    sub = [r for r in prev if r[key] == v]
                    rate[(key, v)] = (sum(r["finish"] <= 3 for r in sub) / len(sub), len(sub))
            if d == nd:
                if ds[-1] >= (dt.date.fromisoformat(last) - dt.timedelta(days=14)).isoformat():
                    current.append((c, s, len(prev), base, rate))
                continue
            # 内枠有利/外枠有利 の判定 → 当日の枠別成績
            gi, go = rate.get(("gate_g", "内"), (base, 0))[0], rate.get(("gate_g", "外"), (base, 0))[0]
            gl = "内有利(前2週 内−外≥+8pt)" if gi - go >= 0.08 else "外有利(前2週 外−内≥+8pt)" if go - gi >= 0.08 else "差なし"
            fr, bk = rate.get(("front", "前"), (base, 0))[0], rate.get(("front", "後"), (base, 0))[0]
            fl = "前残り強(前2週 前−後≥+20pt)" if fr - bk >= 0.20 else "差し届く(前2週 前−後<+10pt)" if fr - bk < 0.10 else "標準"
            for r in byday[(c, s, d)]:
                if r["gate_g"]:
                    _add(gv[gl][r["gate_g"]], r["finish"], r.get("odds"))
                if r["front"]:
                    _add(fv[fl][r["front"]], r["finish"], r.get("odds"))
    L += ["## 3. 今の開催の馬場傾向は続くか（直近14日の同じ競馬場×芝ダ）", "",
          "### 枠の偏り → 当日の枠別成績", "", "| 前2週の傾向 | 枠 | 出走 | 勝率 | 複勝率 | 単回収 |", "|---|---|--:|--:|--:|--:|"]
    for gl in sorted(gv):
        for g in ("内", "中", "外"):
            L.append(f"| {gl} | {g} | {_fmt(gv[gl][g])} |")
    L += ["", "### 前残り/差し → 当日の脚質別成績（脚質はレース後の通過順なので絶対値は高めに出る。区分間の差を見る）", "",
          "| 前2週の傾向 | 脚質 | 出走 | 勝率 | 複勝率 | 単回収 |", "|---|---|--:|--:|--:|--:|"]
    for fl in sorted(fv):
        for g in ("前", "後"):
            L.append(f"| {fl} | {'逃げ・先行' if g == '前' else '差し・追込'} | {_fmt(fv[fl][g])} |")
    L += ["", f"### 直近の開催の傾向（{last} までの14日間）", "",
          "| 競馬場 | 芝ダ | 走数 | 全体複勝率 | 内枠 | 中枠 | 外枠 | 逃げ・先行 | 差し・追込 |", "|---|---|--:|--:|--:|--:|--:|--:|--:|"]
    for c, s, n, base, rate in sorted(current):
        f = lambda k: f"{rate[k][0]:.0%}" if k in rate else "-"
        L.append(f"| {c} | {s} | {n} | {base:.0%} | {f(('gate_g', '内'))} | {f(('gate_g', '中'))} | {f(('gate_g', '外'))} | "
                 f"{f(('front', '前'))} | {f(('front', '後'))} |")
    L.append("")
    L += bias_report(rows)
    L += sire_jockey_report(rows)
    return "\n".join(L)


# ---------------------------------------------------------------- コースバイアス（開催の進み具合 × 馬場状態）

def meet_stage(race_id: str | None) -> str | None:
    """race_id = YYYY CC KK DD RR の DD（開催日目）から、開催の進み具合."""
    if not race_id or len(race_id) != 12 or not race_id.isdigit():
        return None
    d = int(race_id[8:10])
    return "開幕週" if d <= 2 else "2週目" if d <= 4 else "3週目" if d <= 6 else "4週目以降"


def going3(going: str | None) -> str | None:
    if not going:
        return None
    if going.startswith("良"):
        return "良"
    return "稍重" if going.startswith("稍") else "重・不良" if going[0] in "重不" else None


_CB_CACHE: dict = {}


def _cb_rows(conn, before: str):
    return conn.execute("""
        SELECT ra.race_id, ra.course, ra.surface, ra.going, ra.n_runners, r.gate, r.passing, r.finish
        FROM results r JOIN races ra ON ra.race_id = r.race_id
        WHERE ra.surface IN ('芝','ダ') AND ra.date < ? AND r.finish IS NOT NULL""", (before,)).fetchall()


def bias_table(conn, before: str) -> dict:
    """(競馬場, 芝ダ, 段階, 属性, 値) → [出走, 3着内]。段階は ('stage', 開催週) / ('going', 馬場) / ('all',)."""
    key = (id(conn), before[:4])
    if key in _CB_CACHE:
        return _CB_CACHE[key]
    cut = f"{before[:4]}-01-01"   # 年単位でキャッシュ（その年より前のデータだけ＝未来の情報は使わない）
    t: dict = defaultdict(lambda: [0, 0])
    for r in _cb_rows(conn, cut):
        st, _ = style_from_passing(r["passing"], r["n_runners"])
        attrs = [("gate", gate_group(r["gate"])), ("front", "前" if st in ("逃げ", "先行") else "後" if st else None)]
        top = 1 if r["finish"] <= 3 else 0
        for ctx in (("all",), ("stage", meet_stage(r["race_id"])), ("going", going3(r["going"]))):
            if None in ctx:
                continue
            for a, v in attrs + [("base", "-")]:
                if v is None:
                    continue
                c = t[(r["course"], r["surface"], ctx, a, v)]
                c[0] += 1
                c[1] += top
    _CB_CACHE[key] = t
    return t


def course_bias(conn, card: dict, gate: int | None, front: bool | None, k: float = 150.0) -> tuple[float, list]:
    """開催の進み具合・馬場状態によって、この枠/脚質が普段（同じ競馬場×芝ダ全体）よりどれだけ有利/不利か（対数比の和）."""
    if conn is None or not card.get("date"):
        return 0.0, []
    t = bias_table(conn, card["date"])
    c, s = card.get("course"), card.get("surface")
    out, notes = 0.0, []
    for ctx, lab in ((("stage", meet_stage(card.get("race_id"))), None), (("going", going3(card.get("going"))), None)):
        if None in ctx:
            continue
        for a, v in (("gate", gate_group(gate)), ("front", None if front is None else ("前" if front else "後"))):
            if v is None:
                continue
            n, tp = t.get((c, s, ctx, a, v), (0, 0))
            bn, bt = t.get((c, s, ctx, "base", "-"), (0, 0))
            an, at = t.get((c, s, ("all",), a, v), (0, 0))
            abn, abt = t.get((c, s, ("all",), "base", "-"), (0, 0))
            if n < 100 or not bn or not an or not abn:
                continue
            ratio_ctx = ((tp + k * bt / bn) / (n + k)) / (bt / bn)    # この段階での、この属性の相対成績
            ratio_all = (at / an) / (abt / abn)                        # 普段の相対成績
            lv = math.log(ratio_ctx / ratio_all)
            out += lv
            if abs(lv) >= 0.08:
                what = f"{v}枠" if a == "gate" else ("逃げ・先行" if v == "前" else "差し・追込")
                notes.append(f"{c}{s}の{ctx[1]}は{what}が普段より{'有利' if lv > 0 else '不利'}"
                             f"（複勝率{tp / n:.0%}・{n}走 / 普段{at / an:.0%}）")
    return out, notes


def bias_report(rows: list[dict]) -> list[str]:
    """開催週・馬場状態別の枠・脚質の複勝率（競馬場×芝ダ）."""
    t = defaultdict(lambda: [0, 0])
    for r in rows:
        if not r.get("finish"):
            continue
        top = 1 if r["finish"] <= 3 else 0
        g = gate_group(r.get("gate"))
        f = "前" if r["style"] in ("逃げ", "先行") else "後" if r["style"] else None
        for ctx in (("all", "全体"), ("stage", meet_stage(r["race_id"])), ("going", going3(r["going"]))):
            if None in ctx:
                continue
            for a, v in (("gate", g), ("front", f), ("base", "-")):
                if v:
                    c = t[(r["course"], r["surface"], ctx, a, v)]
                    c[0] += 1
                    c[1] += top
    L = ["## 4. コースバイアス（開催の進み具合・馬場状態 × 枠・脚質）", "",
         "開催日目（race_id の日次: 1-2日目=開幕週, 3-4=2週目, 5-6=3週目, 7日目以降=4週目以降）と馬場状態ごとの、枠・脚質別の複勝率。"
         "**内−外** は内枠(1-3)と外枠(7-8)の複勝率の差、**前−後** は逃げ・先行と差し・追込の差（レース後の通過順による）。"
         "予想では、普段（同じ競馬場×芝ダ全体）との差を要素として使う。", "",
         "| 競馬場 | 芝ダ | 区分 | 走数 | 内枠 | 外枠 | 内−外 | 前 | 後 | 前−後 |", "|---|---|---|--:|--:|--:|--:|--:|--:|--:|"]
    cs = sorted({(k[0], k[1]) for k in t})
    rate = lambda k: (t[k][1] / t[k][0]) if t.get(k) and t[k][0] >= 80 else None
    for c, s in cs:
        for ctx in [("all", "全体")] + [("stage", x) for x in ("開幕週", "2週目", "3週目", "4週目以降")] + \
                   [("going", x) for x in ("良", "稍重", "重・不良")]:
            n = t.get((c, s, ctx, "base", "-"), [0])[0]
            if n < 300:
                continue
            gi, go = rate((c, s, ctx, "gate", "内")), rate((c, s, ctx, "gate", "外"))
            fr, bk = rate((c, s, ctx, "front", "前")), rate((c, s, ctx, "front", "後"))
            p = lambda x: f"{x:.1%}" if x is not None else "-"
            d1 = f"{(gi - go) * 100:+.1f}" if gi is not None and go is not None else "-"
            d2 = f"{(fr - bk) * 100:+.1f}" if fr is not None and bk is not None else "-"
            L.append(f"| {c} | {s} | {ctx[1]} | {n} | {p(gi)} | {p(go)} | {d1} | {p(fr)} | {p(bk)} | {d2} |")
    L.append("")
    return L


# ---------------------------------------------------------------- 血統×騎手の相性

def sire_jockey_report(rows: list[dict], split: str = "2025-01-01", min_n: int = 30) -> list[str]:
    """父(系統)×騎手の相性: 人気から期待される複勝率 × 父単体・騎手単体の上振れ を差し引いた、組み合わせ固有の上振れ（z）.

    split より前で相性を測り、split 以降で同じ組み合わせが期待を上回ったかを検証する（毎週自動で再検証）。
    """
    rows = [r for r in rows if r.get("finish") and r.get("popularity") and r.get("jockey")]
    pr = defaultdict(lambda: [0, 0])
    for r in rows:
        x = pr[min(r["popularity"], 16)]
        x[0] += 1
        x[1] += r["finish"] <= 3
    pe = {k: t / n for k, (n, t) in pr.items()}
    K = 30

    def ratio(a):
        return (a[0] + K * 0.25) / (a[1] + K * 0.25)

    def measure(rs, who):
        gs, gj = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
        for r in rs:
            e = pe[min(r["popularity"], 16)]
            top = r["finish"] <= 3
            if r.get(who):
                gs[r[who]][0] += top
                gs[r[who]][1] += e
            gj[r["jockey"]][0] += top
            gj[r["jockey"]][1] += e
        g = defaultdict(lambda: [0, 0.0, 0, 0.0])
        for r in rs:
            if not r.get(who):
                continue
            e = min(0.95, pe[min(r["popularity"], 16)] * ratio(gs[r[who]]) * ratio(gj[r["jockey"]]))
            a = g[(r[who], r["jockey"])]
            a[0] += r["finish"] <= 3
            a[1] += e
            a[2] += 1
            a[3] += e * (1 - e)
        return {k: ((a[0] - a[1]) / math.sqrt(a[3]), a) for k, a in g.items() if a[2] >= min_n and a[3] > 0}, gs, gj

    L = ["## 5. 血統×騎手の相性（父・父系統 × 騎手）", "",
         "人気から期待される複勝率に、父単体・騎手単体の上振れを掛けた期待値と比べて、**その組み合わせだけ**が走る／走らないか（z）。"
         f"{split[:4]}年より前で測った相性が、{split[:4]}年以降も続いたかを検証。", "",
         "| 対象 | 相性（過去） | 組み合わせ数 | その後の出走 | 実際の複勝率 | 期待複勝率 | 実際/期待 |", "|---|---|--:|--:|--:|--:|--:|"]
    tr = [r for r in rows if r["date"] < split]
    te = [r for r in rows if r["date"] >= split]
    for who, lab in (("sire", "父×騎手"), ("sire_line", "父系統×騎手")):
        sel, gs, gj = measure(tr, who)
        b = defaultdict(lambda: [0, 0.0, 0])
        for r in te:
            v = sel.get((r.get(who), r["jockey"]))
            if v is None:
                continue
            z = v[0]
            k = "良い(z≥+2)" if z >= 2 else "悪い(z≤−2)" if z <= -2 else "普通"
            e = min(0.95, pe[min(r["popularity"], 16)] * ratio(gs.get(r[who], [0, 0.0])) * ratio(gj.get(r["jockey"], [0, 0.0])))
            x = b[k]
            x[0] += r["finish"] <= 3
            x[1] += e
            x[2] += 1
        for k in ("良い(z≥+2)", "普通", "悪い(z≤−2)"):
            x = b[k]
            npair = sum(1 for v in sel.values() if (v[0] >= 2 if k.startswith("良") else v[0] <= -2 if k.startswith("悪") else -2 < v[0] < 2))
            if x[2]:
                L.append(f"| {lab} | {k} | {npair} | {x[2]} | {x[0] / x[2]:.1%} | {x[1] / x[2]:.1%} | {x[0] / x[1]:.2f} |")
    # 全期間での現在の目立つ組み合わせ
    sel, _, _ = measure(rows, "sire")
    top = sorted(sel.items(), key=lambda kv: -abs(kv[1][0]))[:30]
    L += ["", "### 全期間で目立つ 父×騎手（|z|上位, 30走以上）", "",
          "| 父 | 騎手 | 出走 | 複勝率 | 期待複勝率 | z |", "|---|---|--:|--:|--:|--:|"]
    L += [f"| {k[0]} | {k[1]} | {a[2]} | {a[0] / a[2]:.1%} | {a[1] / a[2]:.1%} | {z:+.1f} |" for k, (z, a) in top]
    L.append("")
    return L
