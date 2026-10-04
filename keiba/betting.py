"""推奨馬券の組み立て（1レース最大10点）と的中率推定."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .config import MAX_TICKETS_PER_RACE
from .model import HorseEval, simulate_top3

MARKS = ["◎", "○", "▲", "△", "△", "△"]


@dataclass
class Ticket:
    kind: str          # 単勝 / 馬連 / ワイド / 三連複
    horses: tuple      # 馬番
    p_hit: float = 0.0

    def label(self) -> str:
        return f"{self.kind} {'-'.join(str(h) for h in self.horses)}"


@dataclass
class BetPlan:
    strategy: str
    tickets: list
    p_any_hit: float
    marks: dict        # 馬番 → 印


def _hit(kind: str, horses: tuple, order: tuple) -> bool:
    if kind == "単勝":
        return order[0] == horses[0]
    if kind == "複勝":
        return horses[0] in order[:3]
    if kind == "馬連":
        return set(horses) == set(order[:2])
    if kind == "ワイド":
        return set(horses) <= set(order[:3])
    if kind == "三連複":
        return set(horses) == set(order[:3])
    raise ValueError(kind)


LONGSHOT_MIN_POP = 8


def longshot_picks(evals: list[HorseEval], max_n: int = 3) -> list[HorseEval]:
    """★ 血統の穴（複数可）: 8番人気以下で血統要素の合計が最大の馬と、それに近い馬（0.3以上かつ最大の6割以上）.
    検証（2024 / 2025〜）: 最大の馬は3着内率 8.5% / 9.5%、この基準の馬全体で 8.1% / 8.9%（人気薄全体 7.2% / 7.4%）."""
    ls = sorted((h for h in evals if (h.pop_rank or 0) >= LONGSHOT_MIN_POP and h.blood_upside > 0),
                key=lambda h: -h.blood_upside)
    if not ls:
        return []
    best = ls[0].blood_upside
    return [ls[0]] + [h for h in ls[1:max_n] if h.blood_upside >= max(0.3, 0.6 * best)]


def longshot_pick(evals: list[HorseEval]) -> HorseEval | None:
    ls = longshot_picks(evals)
    return ls[0] if ls else None


def assign_marks(evals: list[HorseEval]) -> dict:
    marks = {h.number: MARKS[i] for i, h in enumerate(evals[:len(MARKS)])}
    for ls in longshot_picks(evals):
        if ls.number not in list(marks)[:4]:
            marks[ls.number] = "★"
    # ☆ = 妙味条件（過去2期間で単勝回収率120%超・直近でも検証済み）に当てはまる中穴
    vals = [h for h in evals if getattr(h, "value_segments", None) and h.number not in list(marks)[:3]
            and marks.get(h.number) != "★"]
    if vals:
        marks[max(vals, key=lambda h: h.p_win).number] = "☆"
        return marks
    # ☆ = 市場評価より血統モデルの評価が大きく上回る人気薄
    cands = [h for h in evals[3:] if h.p_market and h.p_model > h.p_market * 1.5 and h.odds and h.odds >= 10
             and marks.get(h.number) != "★"]
    if cands:
        star = max(cands, key=lambda h: h.p_model / h.p_market)
        marks[star.number] = "☆"
    return marks


def build_plan(evals: list[HorseEval], max_tickets: int = MAX_TICKETS_PER_RACE,
               n_sims: int = 30000) -> BetPlan:
    nums = [h.number for h in evals]
    sims = simulate_top3([h.p_win for h in evals], n_sims, seed=1)["samples"]
    orders = [tuple(nums[i] for i in o) for o in sims]
    marks = assign_marks(evals)
    p = [h.p_win for h in evals]
    top = nums
    star = [n for n, m in marks.items() if m == "☆" and n not in top[:4]]
    ana = [n for n, m in marks.items() if m == "★"][:1]   # 血統の穴（最上位）は必ず相手に1枠入れる
    ana_all = [h.number for h in longshot_picks(evals) if marks.get(h.number) == "★"]
    partners5 = list(dict.fromkeys(top[1:5] + star))[:5]

    if p[0] >= 0.30 and p[0] - p[1] >= 0.10:
        strategy = "◎1頭軸（本命信頼型）: 馬連流し4点＋三連複1頭軸流し6点"
        partners = list(dict.fromkeys(top[1:4] + ana + top[4:5]))[:4]
        tickets = [Ticket("馬連", tuple(sorted((top[0], x)))) for x in partners]
        tickets += [Ticket("三連複", tuple(sorted((top[0], a, b)))) for a, b in combinations(partners, 2)]
    elif p[0] + p[1] >= 0.42:
        strategy = "◎○2頭軸（2強型）: 単勝1点＋馬連BOX3点＋三連複2頭軸流し6点"
        tickets = [Ticket("単勝", (top[0],))]
        tickets += [Ticket("馬連", tuple(sorted(c))) for c in combinations(top[:3], 2)]
        others = list(dict.fromkeys(top[2:6] + ana + star + top[6:7]))[:6]
        tickets += [Ticket("三連複", tuple(sorted((top[0], top[1], x)))) for x in others]
    else:
        strategy = "5頭BOX（混戦型）: 三連複BOX10点"
        box = list(dict.fromkeys(top[:4] + ana + partners5))[:5]
        tickets = [Ticket("三連複", tuple(sorted(c))) for c in combinations(box, 3)]

    # ★ 血統の穴は複勝でも押さえる（最大2点、点数上限内。複勝回収は人気薄全体より上だが100%未満）
    fuku = [Ticket("複勝", (n,)) for n in ana_all[:2]]
    # 妙味条件の☆がいれば単勝を1点。★複勝と☆単勝の枠を先に確保し、本線を削る（点数上限内）
    star_v = [n for n, m in marks.items() if m == "☆"]
    tan = [Ticket("単勝", (star_v[0],))] if star_v and not any(
        t.kind == "単勝" and t.horses == (star_v[0],) for t in tickets) else []
    extras = fuku + tan
    if extras:
        main = tickets[:max(0, max_tickets - len(extras))]
        if len(main) < len(tickets):
            strategy += f"（買い目の上位{len(main)}点）"
        tickets = main + extras
    if fuku:
        strategy += f"＋★複勝{len(fuku)}点"
    if tan:
        strategy += "＋妙味☆の単勝1点"
    tickets = tickets[:max_tickets]
    any_hit = 0
    for t in tickets:
        t.p_hit = sum(_hit(t.kind, t.horses, o) for o in orders) / len(orders)
    for o in orders:
        if any(_hit(t.kind, t.horses, o) for t in tickets):
            any_hit += 1
    return BetPlan(strategy, tickets, any_hit / len(orders), marks)


# ================================================================ 本線: 妙味馬の単複＋馬連（検証: docs/analysis/strategy.md）
VALUE_RATIO = 1.3          # 予測勝率 ÷ 市場の勝率
VALUE_POP = (4, 9)         # 対象の人気帯
UMAREN_EV = 1.2            # 馬連: モデルの的中確率 ÷ 市場の想定確率
UMAREN_PAY_MIN = 2000      # 馬連: 市場から見た想定配当（円）
UMAREN_MAX = 5             # 馬連: 最大点数
UMAREN_MAX_RUNNERS = 14    # 馬連は14頭以下のレースだけ（多頭数は妙味馬が効きにくい）
UMAREN_TOP_K = 7           # 馬連の候補: モデル上位7頭（危険な人気馬を除く）


def is_danger(h: HorseEval) -> bool:
    return (h.pop_rank or 99) <= 6 and h.cond_score <= -0.3


def value_horses(evals: list[HorseEval]) -> list[HorseEval]:
    """妙味馬: 4〜9番人気・予測勝率が市場の1.3倍以上・人気帯の中で走る条件がプラス（予測/市場の高い順）."""
    c = [h for h in evals if h.p_market and not h.pop_estimated and VALUE_POP[0] <= (h.pop_rank or 0) <= VALUE_POP[1]
         and h.p_win / h.p_market >= VALUE_RATIO and h.cond_score > 0 and not is_danger(h)]
    return sorted(c, key=lambda h: -h.p_win / h.p_market)


def _harville(p: dict, order) -> float:
    rem, out = 1.0, 1.0
    for k in order:
        if rem <= 0:
            return 0.0
        out *= p[k] / rem
        rem -= p[k]
    return out


def umaren_prob(p: dict, a, b) -> float:
    return _harville(p, (a, b)) + _harville(p, (b, a))


def value_plan(evals: list[HorseEval], n_runners: int | None = None) -> BetPlan | None:
    """本線の買い目: 妙味馬の単勝・複勝（各1点）＋ 妙味馬を含む馬連（期待値の比1.2以上・想定2000円以上, 14頭以下で最大5点）."""
    vals = value_horses(evals)
    if not vals:
        return None
    v = vals[0]
    tickets = [Ticket("単勝", (v.number,)), Ticket("複勝", (v.number,))]
    n = n_runners or len(evals)
    marks = {h.number: "妙" for h in vals}
    if n <= UMAREN_MAX_RUNNERS and all(h.p_market for h in evals):
        pm = {h.number: h.p_market for h in evals}
        pp = {h.number: h.p_win for h in evals}
        top = [h for h in sorted(evals, key=lambda h: -h.p_win) if not is_danger(h)][:UMAREN_TOP_K]
        vset = {h.number for h in vals}
        cand = []
        for a, b in combinations([h.number for h in top], 2):
            if not ({a, b} & vset):
                continue
            q, qm = umaren_prob(pp, a, b), umaren_prob(pm, a, b)
            if qm <= 0:
                continue
            est = 100 * 0.775 / qm
            if q >= UMAREN_EV * qm and est >= UMAREN_PAY_MIN:
                cand.append((q / qm, tuple(sorted((a, b))), q, est))
        cand.sort(reverse=True)
        for r, c, q, est in cand[:UMAREN_MAX]:
            t = Ticket("馬連", c, p_hit=q)
            t.est_pay = est
            t.ev_ratio = r
            tickets.append(t)
    # 的中率（単勝・複勝はモデル確率から）
    from .model import simulate_top3
    sims = simulate_top3([h.p_win for h in evals], 4000, seed=1)["samples"]
    nums = [h.number for h in evals]
    orders = [tuple(nums[i] for i in o) for o in sims]
    for t in tickets:
        t.p_hit = sum(_hit(t.kind, t.horses, o) for o in orders) / len(orders)
    any_hit = sum(any(_hit(t.kind, t.horses, o) for t in tickets) for o in orders) / len(orders)
    n_um = sum(t.kind == "馬連" for t in tickets)
    strat = f"妙味馬 {v.number} の単勝・複勝" + (f"＋妙味馬を含む馬連{n_um}点" if n_um else
                                              ("（15頭以上のため馬連なし）" if n > UMAREN_MAX_RUNNERS else "（条件を満たす馬連なし）"))
    return BetPlan(strat, tickets, any_hit, marks)
