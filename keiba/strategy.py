"""買い方（戦略）のバックテスト: 同じ予測確率から、印・買い目・レース選びの方法を変えて回収率を比べる.

- 本番と同じ evaluate_race（学習済み重み・妙味・人気帯の相対指標・★）で検証期間の各レースを予想する。
  重みの学習は検証期間より前（2025-09-29まで）、条件の相対指標（cond_rates）も検証開始より前のデータだけで作り直す。
- 単勝オッズは確定オッズ（本番は前売り）。払戻は実際の払戻。
- 期間の前半で戦略の閾値を選び、後半（未使用）で成績を測る。
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from itertools import combinations

from . import analysis
from .config import DATA_DIR, ROOT

CACHE = DATA_DIR / "cache" / "strategy_backtest.json"


# ---------------------------------------------------------------- データ収集
def _collect_range(args) -> list[dict]:
    start, end, before = args
    from .model import evaluate_race
    from .validate import POP_WIN, race_cards, _learn_before
    from . import db
    conn = db.connect()
    st = analysis.build_stats(conn, before=before)
    _learn_before(conn, before)
    out = []
    for card, fin, pay in race_cards(conn, start, end):
        # DB に単勝オッズがほぼ無いので、人気順の平均勝率から作った擬似オッズ（控除率20%）で市場評価を与える
        if not all(e.get("popularity") for e in card["entries"]):
            continue
        pk = [POP_WIN[min(e["popularity"], 18) - 1] for e in card["entries"]]
        z = sum(pk)
        for e, q in zip(card["entries"], pk):
            e["odds"] = round(0.8 * z / q, 1)
        try:
            ev = evaluate_race(card, st, conn, n_sims=0)
        except Exception:   # noqa: BLE001
            continue
        out.append({"race_id": card["race_id"], "date": card["date"], "grade": card.get("grade"),
                    "pay": pay, "horses": [{
                        "num": h.number, "p": round(h.p_win, 5), "pm": round(h.p_market or 0, 5),
                        "odds": h.odds, "pop": h.pop_rank, "up": round(h.blood_upside, 3),
                        "edge": round(h.value_edge, 3), "cond": round(h.cond_score, 3),
                        "seg": bool(h.value_segments), "fin": fin.get(h.number)} for h in ev]})
    return out


def collect(conn, start: str, end: str, workers: int = 4) -> list[dict]:
    """検証期間を2週ごとに分けて並列に予想する。集計・学習・条件の相対指標はすべて start より前のデータだけ."""
    import datetime as dt
    from multiprocessing import Pool
    from . import value as V

    # 条件の相対指標を検証開始より前のデータだけで作り直す（本番用ファイルは退避して戻す。退避済みなら上書きしない）
    bak = V.COND_PATH.with_suffix(".bak")
    if V.COND_PATH.exists() and not bak.exists():
        shutil.copy(V.COND_PATH, bak)
    try:
        V.build_cond([r for r in V.load(conn) if r["date"] < start])
        d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
        chunks, d = [], d0
        while d <= d1:
            e = min(d + dt.timedelta(days=13), d1)
            chunks.append((d.isoformat(), e.isoformat(), start))
            d = e + dt.timedelta(days=1)
        with Pool(workers) as pool:
            parts = pool.map(_collect_range, chunks, chunksize=1)
        out = sorted((r for p in parts for r in p), key=lambda r: (r["date"], r["race_id"]))
    finally:
        if bak.exists():
            shutil.move(bak, V.COND_PATH)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out, ensure_ascii=False))
    return out


# ---------------------------------------------------------------- 払戻
PAY = {"単勝": ("単勝",), "複勝": ("複勝",), "ワイド": ("ワイド",), "馬連": ("馬連",), "三連複": ("3連複", "三連複")}


def payout(kind: str, horses: tuple, pay: dict) -> int:
    combo = sorted(horses)
    for key in PAY[kind]:
        for c, yen in pay.get(key, []):
            nums = sorted(int(x) for x in str(c).replace("→", "-").split("-") if x.strip().isdigit())
            if nums == combo:
                return yen or 0
    return 0


# ---------------------------------------------------------------- 馬の分類
def ratio(h) -> float:
    return h["p"] / h["pm"] if h["pm"] else 1.0


def danger(h) -> bool:
    """危険な人気馬: 1-6番人気で人気帯の平均より来ない条件が重なる."""
    return (h["pop"] or 99) <= 6 and h["cond"] <= -0.3


def stars(hs, min_pop=8, max_n=3, rel=0.6, floor=0.3) -> list:
    """★ 血統の穴: min_pop番人気以下で血統要素の合計が最大の馬と、それに近い馬."""
    ls = sorted((h for h in hs if (h["pop"] or 0) >= min_pop and h["up"] > 0), key=lambda h: -h["up"])
    if not ls:
        return []
    best = ls[0]["up"]
    return [ls[0]] + [h for h in ls[1:max_n] if h["up"] >= max(floor, rel * best)]


# ---------------------------------------------------------------- 単体の傾向（戦略の土台）
def horse_roi(data, key, bins) -> list:
    acc = defaultdict(lambda: [0, 0, 0, 0, 0])   # 走, 勝, 3着内, 単払戻, 複払戻
    for r in data:
        for h in r["horses"]:
            v = key(h, r)
            if v is None:
                continue
            b = next((lab for lab, lo, hi in bins if lo <= v < hi), None)
            if b is None:
                continue
            a = acc[b]
            a[0] += 1
            a[1] += h["fin"] == 1
            a[2] += (h["fin"] or 99) <= 3
            a[3] += payout("単勝", (h["num"],), r["pay"])
            a[4] += payout("複勝", (h["num"],), r["pay"])
    return [(lab, *acc[lab]) for lab, _, _ in bins if acc[lab][0]]


# ---------------------------------------------------------------- 戦略
# 各戦略は (レース) → (買い目のリスト[(券種, 馬番tuple)], レース選びの点数) を返す。点数が None なら見送り。
def _current(r):
    """現行: betting.build_plan と推奨度（的中率＋◎勝率）."""
    from .betting import build_plan
    from .model import HorseEval
    evs = []
    for h in r["horses"]:
        e = HorseEval(h["num"], "", None, None, "", "", None, h["odds"], p_win=h["p"], p_model=h["p"])
        e.p_market, e.pop_rank, e.blood_upside = h["pm"], h["pop"], h["up"]
        e.value_segments = [1] if h["seg"] else []
        evs.append(e)
    plan = build_plan(evs, n_sims=1500)
    conf = 0.5 * plan.p_any_hit + 0.4 * evs[0].p_win + {"G1": .06, "G2": .04, "G3": .03}.get(r["grade"] or "", 0)
    return [(t.kind, t.horses) for t in plan.tickets], conf


def make_value(th_r=1.25, min_pop=4, star_pop=7, star_n=4, axis_max_p=1.0, wide=True, trio=True, fuku=True,
               tan=True, skip_danger_axis=True):
    """妙味型: ◎（予測勝率1位。危険な人気馬なら次点）を軸に、人気より評価の高い馬と★を相手に広めに.
    - 単勝: 人気より評価の高い馬（予測/市場 ≥ th_r, min_pop番人気以下）の最上位1点
    - ワイド: ◎ − 相手（妙味馬・★）
    - 三連複: ◎ − 相手 − 相手
    - 複勝: ★
    レース選び: 妙味馬・★の「予測/市場」の最大値（人気通りのレースは低く出る）。"""
    def f(r):
        hs = sorted(r["horses"], key=lambda h: -h["p"])
        axis = next((h for h in hs if not (skip_danger_axis and danger(h))), hs[0])
        if axis["p"] > axis_max_p:
            return [], None
        val = [h for h in hs if h is not axis and (h["pop"] or 0) >= min_pop and ratio(h) >= th_r and not danger(h)]
        val.sort(key=lambda h: -ratio(h))
        st = [h for h in stars(r["horses"], min_pop=star_pop, max_n=star_n) if h is not axis]
        partners = list({h["num"]: h for h in val[:3] + st}.values())[:5]
        if not partners:
            return [], None
        T = []
        if tan and val:
            T.append(("単勝", (val[0]["num"],)))
        if fuku:
            T += [("複勝", (h["num"],)) for h in st[:2]]
        if wide:
            T += [("ワイド", (axis["num"], h["num"])) for h in partners[:3]]
        if trio:
            for a, b in combinations(partners, 2):
                T.append(("三連複", (axis["num"], a["num"], b["num"])))
        T = list(dict.fromkeys(T))[:10]
        score = max(ratio(h) for h in partners)
        return T, score
    return f


def make_tanpuku(th_r=1.3, min_pop=4, star_pop=7, star_n=4):
    """単複だけ: 妙味馬の単勝＋★の複勝."""
    def f(r):
        hs = r["horses"]
        val = sorted((h for h in hs if (h["pop"] or 0) >= min_pop and ratio(h) >= th_r and not danger(h)),
                     key=lambda h: -ratio(h))[:3]
        st = stars(hs, min_pop=star_pop, max_n=star_n)
        T = [("単勝", (h["num"],)) for h in val] + [("複勝", (h["num"],)) for h in st]
        T = list(dict.fromkeys(T))
        return (T, max([ratio(h) for h in val + st], default=0)) if T else ([], None)
    return f


def run_strategy(data, f, per_week: int | None = 5) -> dict:
    import datetime as dt
    weekly = defaultdict(list)
    for r in data:
        T, score = f(r)
        if score is None or not T:
            continue
        ret = [payout(k, h, r["pay"]) for k, h in T]
        wk = dt.date.fromisoformat(r["date"]).isocalendar()[:2]
        weekly[wk].append((score, len(T) * 100, sum(ret), max(ret)))
    n = cost = back = hit = 0
    big = []
    for lst in weekly.values():
        lst.sort(key=lambda x: -x[0])
        for s, c, b, mx in (lst[:per_week] if per_week else lst):
            n += 1
            cost += c
            back += b
            hit += b > 0
            big.append(b)
    big.sort(reverse=True)
    return {"n": n, "cost": cost, "ret": back, "hit": hit, "roi": back / cost if cost else 0,
            "roi_ex1": (back - (big[0] if big else 0)) / cost if cost else 0}


# ---------------------------------------------------------------- 買い目ごとの期待値（モデル確率 ÷ 市場確率）
def _harville(p: dict, order) -> float:
    rem, out = 1.0, 1.0
    for k in order:
        out *= p[k] / rem
        rem -= p[k]
    return out


def ticket_prob(kind: str, horses: tuple, p: dict) -> float:
    from itertools import permutations
    if kind == "単勝":
        return p[horses[0]]
    if kind == "馬連":
        a, b = horses
        return _harville(p, (a, b)) + _harville(p, (b, a))
    if kind == "三連複":
        return sum(_harville(p, o) for o in permutations(horses))
    others = [k for k in p if k not in horses]
    if kind == "ワイド":
        return sum(ticket_prob("三連複", (*horses, c), p) for c in others)
    if kind == "複勝":
        a = horses[0]
        return sum(ticket_prob("ワイド", (a, c), p) for c in others) / 2
    raise ValueError(kind)


def ev_filter(f, th=1.0):
    """買い目のうち、モデルの的中確率が市場の想定確率の th 倍未満のものを外す（軸絡みでも外す）."""
    def g(r):
        T, score = f(r)
        if score is None:
            return T, score
        pm = {h["num"]: h["pm"] for h in r["horses"]}
        pp = {h["num"]: h["p"] for h in r["horses"]}
        keep = [(k, hs) for k, hs in T if ticket_prob(k, hs, pp) >= th * ticket_prob(k, hs, pm)]
        return (keep, score) if keep else ([], None)
    return g
