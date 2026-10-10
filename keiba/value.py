"""妙味（回収率）の場合分け分析.

「どの条件の、どの人気帯の馬を買えば回収率が高いか」を、多数の条件×人気帯について集計する。
大量の組み合わせを試すと偶然の高回収率が必ず出るため、期間を3つに分けて検証する:
  発見期間 → 確認期間 で両方とも回収率が基準を超えた条件だけを採用し、
  最終テスト期間（条件選びに一度も使っていない）でそれらを買った場合の回収率を測る。
採用した条件は data/knowledge/value_segments.json に保存し、予想の根拠欄と穴馬（☆）選びに使う。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

from . import factors as F
from . import knowledge as K
from .config import KNOWLEDGE_DIR, ROOT, distance_band, going_group, write_atomic

SEG_PATH = KNOWLEDGE_DIR / "value_segments.json"
STRICT = {"min_wins": 3, "roi": 1.2}

POP_BUCKETS = (("1-3番人気", 1, 3), ("4-6番人気", 4, 6), ("7-9番人気", 7, 9), ("10番人気以下", 10, 99))


def pop_bucket(p):
    if not p:
        return None
    for name, a, b in POP_BUCKETS:
        if a <= p <= b:
            return name
    return None


def gate_group(g):
    if not g:
        return None
    return "内枠(1-3)" if g <= 3 else ("中枠(4-6)" if g <= 6 else "外枠(7-8)")


# 条件の定義: 名前 → 行(dict) から値(タプル)を作る関数
def _csd(r):
    return f"{r['course']}{r['surface']}{r['distance']}"


def _cs(r):
    return f"{r['course']}{r['surface']}"


DIMENSIONS = {
    "父": lambda r: (r["sire"],),
    "父系統": lambda r: (r["sire_line"],),
    "母父": lambda r: (r["damsire"],),
    "母父系統": lambda r: (r["damsire_line"],),
    "騎手": lambda r: (r["jockey"],),
    "調教師": lambda r: (r["trainer"],),
    "コース": lambda r: (_csd(r),),
    "前走脚質×コース": lambda r: (r["prev_style"], _csd(r)),
    "枠×コース": lambda r: (gate_group(r["gate"]), _csd(r)),
    "父×競馬場": lambda r: (r["sire"], _cs(r)),
    "父×距離帯": lambda r: (r["sire"], r["surface"], distance_band(r["distance"] or 0)),
    "父×馬場": lambda r: (r["sire"], r["surface"], "道悪" if r["gg"] == "soft" else "良"),
    "父×距離変化": lambda r: (r["sire"], r["surface"], r["dchg"]),
    "父×ローテ": lambda r: (r["sire"], r["interval"]),
    "父×頭数": lambda r: (r["sire"], r["surface"], F.field_size_bucket(r["n_runners"])),
    "父×季節": lambda r: (r["sire"], r["surface"], r["season"]),
    "父×クラス": lambda r: (r["sire"], r["surface"], r["grade"]),
    "父系統×コース": lambda r: (r["sire_line"], _csd(r)),
    "父系統×直線": lambda r: (r["sire_line"], r["surface"], "直線" + r["straight_cat"]),
    "父系統×坂": lambda r: (r["sire_line"], r["surface"], r["slope"]),
    "母父系統×距離帯": lambda r: (r["damsire_line"], r["surface"], distance_band(r["distance"] or 0)),
    "騎手×競馬場": lambda r: (r["jockey"], _cs(r)),
    "調教師×ローテ": lambda r: (r["trainer"], r["interval"]),
    "前走脚質×馬場": lambda r: (r["prev_style"], r["surface"], "道悪" if r["gg"] == "soft" else "良"),
    "年齢×性別×季節": lambda r: (r["age"], r["sex"], r["season"]),
    "距離変化×前走脚質": lambda r: (r["surface"], r["dchg"], r["prev_style"]),
}

PERIODS = {"発見": ("2000-01-01", "2022-12-31"), "確認": ("2023-01-01", "2024-12-31"), "テスト": ("2025-01-01", "2099-12-31")}


def _period(date):
    for k, (a, b) in PERIODS.items():
        if a <= date <= b:
            return k
    return None


def load(conn) -> list[dict]:
    from .deep import load_rows
    rows = load_rows(conn)
    pays = {}
    for rid, pj in conn.execute("SELECT race_id, payouts FROM races").fetchall():
        try:
            p = json.loads(pj or "{}")
        except ValueError:
            p = {}
        pays[rid] = {"win": {str(c): y or 0 for c, y in p.get("単勝", [])},
                     "place": {str(c): y or 0 for c, y in p.get("複勝", [])}}
    prev = {}
    for r in rows:   # load_rows は馬ごと・日付順
        r["prev_style"] = prev.get(r["horse_id"])
        prev[r["horse_id"]] = r["style"]
        a = K.course_attrs(r["course"], r["surface"], r["distance"])
        r["straight_cat"], r["slope"] = a["straight_cat"], a["slope"]
        pr = pays.get(r["race_id"], {"win": {}, "place": {}})
        r["win_pay"] = pr["win"].get(str(r["number"]), 0)
        r["place_pay"] = pr["place"].get(str(r["number"]), 0)
        r["pop_b"] = pop_bucket(r["popularity"])
        r["period"] = _period(r["date"])
    return rows


class Acc:
    __slots__ = ("n", "win", "place", "hits", "top3")

    def __init__(self):
        self.n = self.win = self.place = self.hits = self.top3 = 0

    def add(self, r):
        self.n += 1
        self.win += r["win_pay"]
        self.place += r["place_pay"]
        self.hits += 1 if r["finish"] == 1 else 0
        self.top3 += 1 if r["finish"] and r["finish"] <= 3 else 0

    @property
    def t3(self):
        return self.top3 / self.n if self.n else 0

    @property
    def wroi(self):
        return self.win / (100 * self.n) if self.n else 0

    @property
    def proi(self):
        return self.place / (100 * self.n) if self.n else 0


def mine(rows, min_n=(60, 60), roi=1.0, kind="win"):
    """全条件×人気帯を集計し、発見・確認の両期間で回収率が基準以上の条件を返す."""
    acc = defaultdict(Acc)
    for r in rows:
        if not r["pop_b"] or not r["period"]:
            continue
        for dim, f in DIMENSIONS.items():
            try:
                key = f(r)
            except (KeyError, TypeError):
                continue
            if any(v is None for v in key):
                continue
            acc[(dim, key, r["pop_b"], r["period"])].add(r)
    segs = []
    tried = 0
    for (dim, key, pb, per), a in list(acc.items()):
        if per != "発見" or a.n < min_n[0]:
            continue
        tried += 1
        b = acc.get((dim, key, pb, "確認"))
        va = a.wroi if kind == "win" else a.proi
        if va < roi or not b or b.n < min_n[1]:
            continue
        vb = b.wroi if kind == "win" else b.proi
        if vb < roi:
            continue
        t = acc.get((dim, key, pb, "テスト"), Acc())
        segs.append({"dim": dim, "key": list(key), "pop": pb, "kind": kind,
                     "discover": {"n": a.n, "win_roi": round(a.wroi, 3), "place_roi": round(a.proi, 3)},
                     "confirm": {"n": b.n, "win_roi": round(b.wroi, 3), "place_roi": round(b.proi, 3)},
                     "test": {"n": t.n, "win_roi": round(t.wroi, 3), "place_roi": round(t.proi, 3)}})
    passed_a = sum(1 for (dim, key, pb, per), a in acc.items()
                   if per == "発見" and a.n >= min_n[0] and (a.wroi if kind == "win" else a.proi) >= roi)
    segs.sort(key=lambda s: -min(s["discover"][f"{kind}_roi"], s["confirm"][f"{kind}_roi"]))
    return segs, {"tried": tried, "passed_discover": passed_a, "passed_both": len(segs)}, acc


FADE = {"min_n": 40, "t3_ratio": 0.75, "roi": 0.65}


def mine_fade(rows, acc, base) -> tuple[list[dict], list[str]]:
    """人気（1〜9番人気）なのに来ない条件: 発見・確認の両期間で、同じ人気帯・期間の平均より
    複勝率が FADE['t3_ratio'] 倍以下、かつ単勝回収率 FADE['roi'] 以下。テスト期間で再現するかを検証."""
    fade = []
    for (dim, key, pb, per), a in acc.items():
        if per != "発見" or pb == "10番人気以下" or a.n < FADE["min_n"]:
            continue
        ba = base.get((pb, "発見"))
        if not ba or a.t3 > ba.t3 * FADE["t3_ratio"] or a.wroi > FADE["roi"]:
            continue
        b, bb = acc.get((dim, key, pb, "確認")), base.get((pb, "確認"))
        if not b or not bb or b.n < FADE["min_n"] or b.t3 > bb.t3 * FADE["t3_ratio"] or b.wroi > FADE["roi"]:
            continue
        t = acc.get((dim, key, pb, "テスト"), Acc())
        fade.append({"dim": dim, "key": list(key), "pop": pb, "kind": "fade",
                     **{nm: {"n": x.n, "wins": x.hits, "top3": x.top3, "t3": round(x.t3, 4),
                             "base_t3": round(base[(pb, per_)].t3, 4) if (pb, per_) in base else None,
                             "win_roi": round(x.wroi, 3), "place_roi": round(x.proi, 3)}
                        for nm, x, per_ in (("discover", a, "発見"), ("confirm", b, "確認"), ("test", t, "テスト"))}})
    fade.sort(key=lambda s: s["discover"]["t3"] / max(s["discover"]["base_t3"], 1e-3)
              + s["confirm"]["t3"] / max(s["confirm"]["base_t3"], 1e-3))
    # テスト期間の検証（人気帯ごと、重複は1回）
    keys = {(s["dim"], tuple(s["key"]), s["pop"]) for s in fade}
    hit, allp = defaultdict(Acc), defaultdict(Acc)
    for r in rows:
        if r["period"] != "テスト" or not r["pop_b"] or r["pop_b"] == "10番人気以下":
            continue
        allp[r["pop_b"]].add(r)
        for dim, f in DIMENSIONS.items():
            try:
                key = f(r)
            except (KeyError, TypeError):
                continue
            if (dim, key, r["pop_b"]) in keys:
                hit[r["pop_b"]].add(r)
                break
    L = ["## 人気なのに来ない条件（消し・評価下げの指標）", "",
         f"- 基準: 1〜9番人気。発見・確認の各期間で{FADE['min_n']}走以上、同じ人気帯の平均より複勝率が"
         f"{FADE['t3_ratio']:.0%}以下、かつ単勝回収率{FADE['roi']:.0%}以下。",
         f"- 抽出: **{len(fade)} 条件**。テスト期間（条件選びに未使用）で当てはまった馬の成績:", "",
         "| 人気帯 | 該当馬 | 複勝率 | 人気帯全体の複勝率 | 単回収 | 複回収 | 全体の単回収 |", "|---|--:|--:|--:|--:|--:|--:|"]
    for name, _, _ in POP_BUCKETS[:3]:
        h, a = hit.get(name, Acc()), allp.get(name, Acc())
        if a.n:
            L.append(f"| {name} | {h.n} | {h.t3:.1%} | {a.t3:.1%} | {h.wroi:.0%} | {h.proi:.0%} | {a.wroi:.0%} |")
    L += ["", "| 条件 | 人気帯 | 発見(走/複勝率/平均) | 確認(走/複勝率/平均) | テスト(走/複勝率/平均/単回収) |", "|---|---|---|---|---|"]
    for sg in fade[:80]:
        d, c, t = sg["discover"], sg["confirm"], sg["test"]
        tb = f"{t['base_t3']:.0%}" if t["base_t3"] is not None else "-"
        L.append(f"| {sg['dim']}: {' / '.join(map(str, sg['key']))} | {sg['pop']} | {d['n']}/{d['t3']:.0%}/{d['base_t3']:.0%} | "
                 f"{c['n']}/{c['t3']:.0%}/{c['base_t3']:.0%} | {t['n']}/{t['t3']:.0%}/{tb}/{t['win_roi']:.0%} |")
    L.append("")
    return fade, L


def cond_validation(rows) -> list[str]:
    """相対指標を発見+確認期間だけで作り、テスト期間で人気帯ごとに効くかを確認."""
    old = COND_PATH.read_bytes() if COND_PATH.exists() else None
    build_cond([r for r in rows if r["period"] in ("発見", "確認")])
    _COND_CACHE.clear()
    out = defaultdict(Acc)
    labels = ["−0.3以下（来ない）", "−0.3〜−0.1", "±0.1", "+0.1〜+0.3", "+0.3以上（来る）"]
    for r in rows:
        if r["period"] != "テスト" or not r["pop_b"] or not r["finish"]:
            continue
        net, _ = cond_score(r)
        b = 0 if net < -0.3 else 1 if net < -0.1 else 2 if net < 0.1 else 3 if net < 0.3 else 4
        out[(r["pop_b"], b)].add(r)
    if old is not None:
        COND_PATH.write_bytes(old)
    _COND_CACHE.clear()
    L = ["## 人気帯内の相対指標（条件が合わない人気馬＝来ない、条件が合う人気薄＝来る）", "",
         "26種類の条件（父・父系統・母父・騎手・厩舎・コース・枠・前走脚質・ローテ・距離変化・馬場・頭数・季節 など）ごとに、"
         "同じ人気帯の平均と比べた複勝率の縮約つき対数比を足し合わせた指標。**発見+確認期間だけで作り、テスト期間で評価**。", "",
         "| 人気帯 | 指標 | 出走 | 勝率 | 複勝率 | 単回収 | 複回収 |", "|---|---|--:|--:|--:|--:|--:|"]
    for name, _, _ in POP_BUCKETS:
        for b, lab in enumerate(labels):
            a = out.get((name, b))
            if a and a.n:
                L.append(f"| {name} | {lab} | {a.n} | {a.hits / a.n:.1%} | {a.t3:.1%} | {a.wroi:.0%} | {a.proi:.0%} |")
    L.append("")
    return L


def portfolio(segs, rows, kind="win"):
    """テスト期間に、採用条件のどれかに当てはまる馬を全部買った場合の成績（重複は1回）."""
    keys = {(s["dim"], tuple(s["key"]), s["pop"]) for s in segs}
    a = Acc()
    for r in rows:
        if r["period"] != "テスト" or not r["pop_b"]:
            continue
        hit = False
        for dim, f in DIMENSIONS.items():
            try:
                key = f(r)
            except (KeyError, TypeError):
                continue
            if (dim, key, r["pop_b"]) in keys:
                hit = True
                break
        if hit:
            a.add(r)
    return a


def run(conn) -> str:
    rows = load(conn)
    L = ["# 妙味（回収率）の場合分け分析（自動生成）", "",
         f"- 対象: {len(rows)}走。期間: 発見 {PERIODS['発見'][0][:4]}〜2022年 / 確認 2023〜2024年 / テスト 2025年〜（条件選びに未使用）",
         "- 採用基準: 発見・確認の両期間で、それぞれ60走以上かつ回収率100%以上。", ""]
    # 全体の人気帯別
    base = defaultdict(Acc)
    for r in rows:
        if r["pop_b"] and r["period"]:
            base[(r["pop_b"], r["period"])].add(r)
    L += ["## 全体の人気帯別回収率（基準）", "", "| 人気帯 | 期間 | 走数 | 勝率 | 単回収 | 複回収 |", "|---|---|--:|--:|--:|--:|"]
    for name, _, _ in POP_BUCKETS:
        for per in PERIODS:
            a = base.get((name, per))
            if a and a.n:
                L.append(f"| {name} | {per} | {a.n} | {a.hits / a.n:.1%} | {a.wroi:.0%} | {a.proi:.0%} |")
    L.append("")
    out = {}
    for kind, lab in (("win", "単勝"), ("place", "複勝")):
        segs, stat, _ = mine(rows, kind=kind)
        pf = portfolio(segs, rows, kind)
        out[kind] = segs
        L += [f"## {lab}: 両期間で回収率100%以上だった条件", "",
              f"- 発見期間で基準を満たした条件: {stat['passed_discover']} / {stat['tried']}（偶然でもある程度は出る）",
              f"- うち確認期間でも100%以上: **{stat['passed_both']}**",
              f"- **テスト期間（未使用）で、これら全部に当てはまる馬を買った場合: {pf.n}頭、{lab}回収率 "
              f"{(pf.wroi if kind == 'win' else pf.proi):.0%}**（単勝{pf.wroi:.0%}・複勝{pf.proi:.0%}）", "",
              f"| 条件 | 人気帯 | 発見(走/{lab}回収) | 確認(走/{lab}回収) | テスト(走/単回収/複回収) |", "|---|---|---|---|---|"]
        for sg in segs[:60]:
            k = kind + "_roi"
            L.append(f"| {sg['dim']}: {' / '.join(map(str, sg['key']))} | {sg['pop']} | "
                     f"{sg['discover']['n']} / {sg['discover'][k]:.0%} | {sg['confirm']['n']} / {sg['confirm'][k]:.0%} | "
                     f"{sg['test']['n']} / {sg['test']['win_roi']:.0%} / {sg['test']['place_roi']:.0%} |")
        L.append("")
    # ---- 本番用の厳格基準: 9番人気以内・各期間3勝以上・両期間とも単勝回収率120%以上
    _, _, acc = mine(rows, kind="win")
    strict = []
    for (dim, key, pb, per), a in acc.items():
        if per != "発見" or pb == "10番人気以下" or a.n < 60 or a.hits < STRICT["min_wins"] or a.wroi < STRICT["roi"]:
            continue
        b = acc.get((dim, key, pb, "確認"))
        if not b or b.n < 60 or b.hits < STRICT["min_wins"] or b.wroi < STRICT["roi"]:
            continue
        t = acc.get((dim, key, pb, "テスト"), Acc())
        strict.append({"dim": dim, "key": list(key), "pop": pb, "kind": "win",
                       "discover": {"n": a.n, "wins": a.hits, "win_roi": round(a.wroi, 3), "place_roi": round(a.proi, 3)},
                       "confirm": {"n": b.n, "wins": b.hits, "win_roi": round(b.wroi, 3), "place_roi": round(b.proi, 3)},
                       "test": {"n": t.n, "wins": t.hits, "win_roi": round(t.wroi, 3), "place_roi": round(t.proi, 3)}})
    pf = portfolio(strict, rows)
    L += ["## 本番で使う条件（厳格基準）", "",
          f"- 基準: 9番人気以内、発見・確認の各期間で60走以上・{STRICT['min_wins']}勝以上・単勝回収率{STRICT['roi']:.0%}以上",
          f"- **テスト期間（未使用）で全部買った場合: {pf.n}頭、単勝回収率 {pf.wroi:.0%}・複勝回収率 {pf.proi:.0%}**",
          "- 基準を厳しくするほどテスト期間の回収率が上がる（100%基準→93%、110%→102%、120%→144%）一貫した傾向あり。突出した傾向として予想の要素に使い、毎週の結果で更新する。", "",
          "| 条件 | 人気帯 | 発見(走/勝/単回収) | 確認(走/勝/単回収) | テスト(走/勝/単回収/複回収) |", "|---|---|---|---|---|"]
    for sg in strict:
        d, c, t = sg["discover"], sg["confirm"], sg["test"]
        L.append(f"| {sg['dim']}: {' / '.join(map(str, sg['key']))} | {sg['pop']} | {d['n']}/{d['wins']}/{d['win_roi']:.0%} | "
                 f"{c['n']}/{c['wins']}/{c['win_roi']:.0%} | {t['n']}/{t['wins']}/{t['win_roi']:.0%}/{t['place_roi']:.0%} |")
    L.append("")
    fade, ftxt = mine_fade(rows, acc, base)
    L += ftxt
    L += cond_validation(rows)
    build_cond(rows)
    bacc = defaultdict(Acc)
    for r in rows:
        if r["pop_b"]:
            bacc[r["pop_b"]].add(r)
    base = {pb: {"win": round(a.wroi, 3), "place": round(a.proi, 3), "top3": round(a.t3, 4)} for pb, a in bacc.items()}
    write_atomic(SEG_PATH, json.dumps({"_meta": "妙味条件（value.py が生成）。strict が本番用、win/place は確認済みの条件"
                                             "（予想では回収率の突出度に応じた相対指標として使う）。base は人気帯ごとの全体回収率",
                                    "periods": PERIODS, "base": base, "strict": strict, "fade": fade, **out}, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    text = "\n".join(L) + "\n"
    (ROOT / "docs" / "analysis" / "value_segments.md").write_text(text)
    return text


COND_PATH = KNOWLEDGE_DIR / "cond_rates.json"
COND_K, COND_MIN_N, COND_CAP = 100, 30, 1.0


def build_cond(rows) -> dict:
    """人気帯内での条件の相対成績: 各条件×人気帯の複勝率を人気帯の平均と比べた縮約つき対数比.

    人気帯の中で『この条件だと人気なのに来ない／人気薄でも来る』を表す相対指標。
    発見+確認期間だけで作った指標がテスト期間でも単調に効くことを確認済み（所見 6.7）。本番用は全期間で作る。
    """
    acc, base = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        if not r["pop_b"] or not r["finish"]:
            continue
        top = 1 if r["finish"] <= 3 else 0
        base[r["pop_b"]][0] += 1
        base[r["pop_b"]][1] += top
        for dim, f in DIMENSIONS.items():
            try:
                key = f(r)
            except (KeyError, TypeError):
                continue
            if any(v is None for v in key):
                continue
            a = acc[(dim, key, r["pop_b"])]
            a[0] += 1
            a[1] += top
    br = {k: t / n for k, (n, t) in base.items()}
    out = {}
    for (dim, key, pb), (n, t) in acc.items():
        if n < COND_MIN_N:
            continue
        b = br[pb]
        e = math.log(((t + COND_K * b) / (n + COND_K)) / b)
        if abs(e) >= 0.05:
            out["|".join([dim, *map(str, key), pb])] = [round(e, 3), n, round(t / n, 3), round(b, 3)]
    data = {"_meta": "条件×人気帯の複勝率の、人気帯平均に対する縮約つき対数比 [e, 出走, 複勝率, 人気帯平均]。value.build_cond が生成",
            "k": COND_K, "min_n": COND_MIN_N, "cond": out}
    write_atomic(COND_PATH, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return data


_COND_CACHE: dict = {}


def cond_score(ctx: dict) -> tuple[float, list]:
    """予想時: この馬の条件（＋人気帯）の相対成績の合計（±COND_CAP）と、各条件の内訳."""
    if not COND_PATH.exists() or not ctx.get("pop_b"):
        return 0.0, []
    m = COND_PATH.stat().st_mtime
    if _COND_CACHE.get("m") != m:
        _COND_CACHE.update(m=m, d=json.loads(COND_PATH.read_text(encoding="utf-8"))["cond"])
    table = _COND_CACHE["d"]
    parts = []
    for dim, f in DIMENSIONS.items():
        try:
            key = f(ctx)
        except (KeyError, TypeError):
            continue
        if any(v is None for v in key):
            continue
        v = table.get("|".join([dim, *map(str, key), ctx["pop_b"]]))
        if v:
            parts.append((v[0], dim, key, v))
    net = sum(p[0] for p in parts)
    return max(-COND_CAP, min(COND_CAP, net)), sorted(parts)


_SEG_CACHE: dict = {}


def _segs() -> dict | None:
    if not SEG_PATH.exists():
        return None
    m = SEG_PATH.stat().st_mtime
    if _SEG_CACHE.get("m") != m:
        _SEG_CACHE.update(m=m, d=json.loads(SEG_PATH.read_text(encoding="utf-8")))
    return _SEG_CACHE["d"]


def matching(entry_ctx: dict, kind: str | None = None) -> list[dict]:
    """予想時: この馬（条件＋人気）に当てはまる採用条件."""
    data = _segs()
    if not data:
        return []
    out = []
    for k in (kind,) if kind else ("strict",):
        for sg in data.get(k, []):
            f = DIMENSIONS.get(sg["dim"])
            if not f or sg["pop"] != entry_ctx.get("pop_b"):
                continue
            try:
                key = f(entry_ctx)
            except (KeyError, TypeError):
                continue
            if list(key) == sg["key"]:
                out.append(sg)
    return out


BASE_ROI = {"win": 0.78, "place": 0.80}


def edge(segs: list[dict], k: float = 200.0, cap: float = 0.5) -> tuple[float, list]:
    """当てはまる妙味条件から、市場確率に掛ける補正（対数）を出す相対指標.

    発見・確認・テストの全期間をまとめた回収率を、出走数に応じて基準回収率へ縮約（k 走ぶん基準値を混ぜる）し、
    log(縮約回収率 / 基準回収率) を足し合わせる（±cap で頭打ち）。複勝の条件は単勝への効きを半分とみなす。
    厳格基準に届かない条件も、実績の突出度と出走数に応じた強さで使う。
    """
    tot, used, seen = 0.0, [], set()
    for sg in segs:
        sid = (sg["dim"], tuple(sg["key"]), sg["pop"], sg.get("kind", "win"))
        if sid in seen:
            continue
        seen.add(sid)
        kind = sg.get("kind", "win")
        per = [sg[p] for p in ("discover", "confirm", "test") if sg.get(p)]
        n = sum(p["n"] for p in per)
        if kind == "fade":   # 複勝率の比（人気帯・期間の平均に対する）で評価を下げる
            t3 = sum(p["top3"] for p in per)
            exp_ = sum(p["n"] * (p["base_t3"] or 0.3) for p in per)
            e = math.log((t3 + k * 0.3) / (exp_ + k * 0.3)) if exp_ else 0.0
            tot += e
            used.append((e, sg, n, t3 / n if n else 0))
            continue
        ret = sum(p["n"] * p[kind + "_roi"] for p in per)
        base = ((_segs() or {}).get("base", {}).get(sg["pop"]) or BASE_ROI)[kind]
        e = math.log((ret + k * base) / (n + k) / base) * (1.0 if kind == "win" else 0.5)
        tot += e
        used.append((e, sg, n, ret / n if n else 0))
    return max(-cap, min(cap, tot)), sorted(used, key=lambda x: -x[0])
