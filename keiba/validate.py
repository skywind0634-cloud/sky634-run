"""予想モデルの検証（バックテスト）・要素の貢献度・重みの自動調整.

- 検証期間より前のデータだけで集計・学習し（未来の情報を使わない）、検証期間の各レースを予想して答え合わせ
- 指標: 対数損失、勝率予測のキャリブレーション、◎の勝率/複勝率/単勝回収率、推奨馬券の的中率・回収率（実際の払戻）
- 要素ごとに重みを0にした時の悪化幅（貢献度）
- 座標降下法で各要素の重みと温度・市場ブレンド比を最適化 → data/model_params.json
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

from . import analysis, deep
from . import knowledge as K
from .betting import build_plan
from .config import DATA_DIR, ROOT, is_target_race
from .model import PARAMS, evaluate_race

PARAMS_PATH = DATA_DIR / "model_params.json"

from .model import COMP_W  # noqa: E402  要素名→重み名（model と共通）
GROUP_JA = {"blood": "血統適性(事前+学習)", "nick": "ニックス(事前)", "family": "牝系", "sire_data": "種牡馬実績",
            "going": "道悪実績", "damsire_data": "母父実績", "nick_data": "実測ニックス", "dam_data": "兄弟実績",
            "jockey": "騎手", "trainer": "調教師", "jt": "騎手×調教師", "draw": "枠", "pace": "系統×ペース",
            "form": "近走フォーム", "style": "展開・脚質", "pace_fit": "自身のペース適性", "distance": "距離適性",
            "dist_data": "距離実績(父・延長短縮)", "rotation": "ローテ", "class": "昇級降級", "jockey_chg": "乗り替わり",
            "weight": "斤量", "body_weight": "馬体重", "course_exp": "コース実績", "direction": "左右回り",
            "season": "季節", "time_index": "タイム指数", "margin": "着差", "inbreed": "インブリード",
            "debut": "新馬", "field_size": "頭数×脚質", "course_type": "コース形態適性(馬)",
            "sire_course_type": "コース形態適性(種牡馬)", "field_fit": "頭数適性(馬)", "sire_field": "頭数適性(種牡馬)",
            "rest_fit": "休み明け適性(馬)", "sire_rest": "休み明け(種牡馬)", "closing": "4角からの追い上げ",
            "agari": "上がり3Fの切れ", "repeat_blood": "同名レースの連続好走血統", "momentum": "血統の勢い(直近1年)",
            "family_fit": "牝系(兄弟・2代母の一族)の条件適性", "country_fit": "国別タイプ(日本型/米国型/欧州型)×条件", "meet_bias": "今の開催の馬場傾向", "course_bias": "コースバイアス(開催週・馬場状態×枠・脚質)"}


def race_cards(conn, start: str, end: str) -> list[tuple[dict, dict, dict]]:
    """検証対象レース → (カード, {馬番: 着順}, 払戻)."""
    out = []
    for race in conn.execute("SELECT * FROM races WHERE date BETWEEN ? AND ? AND surface IN ('芝','ダ') "
                             "ORDER BY date, race_id", (start, end)).fetchall():
        race = dict(race)
        if not is_target_race(race["race_no"], race["grade"], race["surface"], race["name"]):
            continue
        rows = conn.execute("SELECT r.*, h.name FROM results r LEFT JOIN horses h ON h.horse_id=r.horse_id "
                            "WHERE r.race_id=? ORDER BY r.number", (race["race_id"],)).fetchall()
        if len(rows) < 5:
            continue
        card = {**race, "entries": [{
            "horse_id": r["horse_id"], "name": r["name"] or r["horse_id"], "number": r["number"], "gate": r["gate"],
            "age": r["age"], "sex": r["sex"], "jockey": r["jockey"], "trainer": r["trainer"],
            "weight": r["weight_carried"], "popularity": r["popularity"],
            "body_weight_diff": r["body_weight_diff"]} for r in rows]}
        card.pop("pace_type", None)   # レース後に分かる情報は使わない
        fin = {r["number"]: r["finish"] for r in rows}
        out.append((card, fin, json.loads(race["payouts"] or "{}")))
    return out


def _learn_before(conn, start: str):
    """検証開始日より前のデータだけで適性を学習し、予想モデルに差し込む（未来情報の遮断）."""
    rows = [r for r in deep.load_rows(conn) if r["date"] < start]
    lv = {"sires": deep.learn_sire_aptitudes(rows, "sire"),
          "damsires": deep.learn_sire_aptitudes(rows, "damsire", min_n=80)}
    K.learned.cache_clear()
    K._learned_override = lv


def collect(conn, start: str, end: str) -> list[dict]:
    """各レースの各馬について、重み1あたりの生の要素値を計算してキャッシュ."""
    from . import model as M
    M.USE_CLOGIT = False   # 生の要素値を集めるので、学習済み重みは使わない
    st = analysis.build_stats(conn, before=start)
    _learn_before(conn, start)
    base = {k: v for k, v in PARAMS.items()}
    data = []
    for card, fin, pay in race_cards(conn, start, end):
        ev = evaluate_race(card, st, conn, base, n_sims=0)
        horses = []
        for h in ev:
            raw = {c: (v / base[COMP_W[c]] if base.get(COMP_W.get(c, ""), 0) else 0.0)
                   for c, v in h.components.items() if c in COMP_W}
            pop = next((e.get("popularity") for e in card["entries"] if e["number"] == h.number), None)
            horses.append({"num": h.number, "raw": raw, "pop": pop, "fin": fin.get(h.number)})
        data.append({"race_id": card["race_id"], "date": card["date"], "grade": card.get("grade"),
                     "horses": horses, "pay": pay, "card": card})
    K._learned_override = None
    K.learned.cache_clear()
    M.USE_CLOGIT = True
    return data


# 人気順 → 市場の勝率（JRA平地の一般的な水準。実績があれば置き換える）
POP_WIN = [0.32, 0.19, 0.13, 0.095, 0.07, 0.055, 0.042, 0.033, 0.026, 0.02, 0.016, 0.013, 0.011, 0.009,
           0.008, 0.007, 0.006, 0.005]


def pop_table(data) -> list[float]:
    cnt = defaultdict(lambda: [0, 0])
    for r in data:
        for h in r["horses"]:
            if h["pop"]:
                cnt[h["pop"]][0] += 1
                cnt[h["pop"]][1] += h["fin"] == 1
    out = []
    for i in range(1, 19):
        n, w = cnt[i]
        out.append((w + 20 * POP_WIN[i - 1]) / (n + 20))
    return out


def probs(race: dict, P: dict, ptab: list[float]) -> list[float]:
    s = [sum(P.get(COMP_W[c], 0) * v for c, v in h["raw"].items()) for h in race["horses"]]
    T = P["T"]
    mx = max(s)
    ex = [math.exp((x - mx) / T) for x in s]
    z = sum(ex)
    pm = [x / z for x in ex]
    mw = P["market_w"]
    if mw and all(h["pop"] for h in race["horses"]):
        pk = [ptab[min(h["pop"], 18) - 1] for h in race["horses"]]
        zk = sum(pk)
        lg = [(1 - mw) * math.log(a) + mw * math.log(b / zk) for a, b in zip(pm, pk)]
        m2 = max(lg)
        ex = [math.exp(v - m2) for v in lg]
        z = sum(ex)
        return [x / z for x in ex]
    return pm


def logloss(data, P, ptab) -> float:
    tot = n = 0
    for r in data:
        p = probs(r, P, ptab)
        for h, q in zip(r["horses"], p):
            if h["fin"] == 1:
                tot += -math.log(max(q, 1e-6))
                n += 1
    return tot / max(n, 1)


MIN_RACES_TO_SAVE = 600     # これ未満の検証レース数では調整結果を保存しない（過学習防止）
MIN_RACES_TO_ZERO = 2000    # これ未満では要素の重みを 0 にしない（0.5〜2倍の範囲でのみ調整）


def tune(data, P: dict, ptab, rounds: int = 2) -> tuple[dict, float]:
    """座標降下法で重み・温度・市場比を最適化（対数損失の最小化）."""
    P = dict(P)
    best = logloss(data, P, ptab)
    keys = sorted(set(COMP_W.values())) + ["T", "market_w"]
    mults = (0, 0.5, 0.75, 1.25, 1.5, 2.0) if len(data) >= MIN_RACES_TO_ZERO else (0.5, 0.75, 1.25, 1.5, 2.0)
    for _ in range(rounds):
        for k in keys:
            cur = P[k]
            base_w = PARAMS.get(k, cur) or cur
            cands = ([min(max(cur * m, base_w * 0.25), base_w * 4) for m in mults] if k not in ("market_w",)
                     else [0.2, 0.35, 0.5, 0.65])
            if k == "T":
                cands = [cur * m for m in (0.6, 0.8, 1.25, 1.5)]
            for v in cands:
                P[k] = v
                ll = logloss(data, P, ptab)
                if ll < best - 1e-5:
                    best, cur = ll, v
            P[k] = cur
    return P, best


PAY_KEY = {"単勝": ["単勝"], "馬連": ["馬連"], "ワイド": ["ワイド"], "三連複": ["3連複", "三連複"]}


def ticket_return(t, pay) -> int:
    combo = "-".join(str(x) for x in sorted(t.horses))
    for key in PAY_KEY[t.kind]:
        for c, yen in pay.get(key, []):
            nums = sorted(int(x) for x in str(c).replace("→", "-").split("-") if x.strip().isdigit())
            if "-".join(map(str, nums)) == combo:
                return yen or 0
    return 0


def evaluate(data, P, ptab) -> dict:
    """指標の計算（キャリブレーション・◎成績・推奨馬券の回収率）."""
    from .model import HorseEval
    bins = [(0, .05), (.05, .1), (.1, .2), (.2, .3), (.3, .5), (.5, 1.01)]
    cal = {b: [0, 0.0, 0] for b in bins}
    top = {"n": 0, "win": 0, "top3": 0, "ret": 0.0}
    bets_all = {"n": 0, "cost": 0, "ret": 0, "hit": 0}
    weekly = defaultdict(list)
    for r in data:
        p = probs(r, P, ptab)
        for h, q in zip(r["horses"], p):
            for b in bins:
                if b[0] <= q < b[1]:
                    cal[b][0] += 1
                    cal[b][1] += q
                    cal[b][2] += h["fin"] == 1
        order = sorted(range(len(p)), key=lambda i: -p[i])
        h0 = r["horses"][order[0]]
        top["n"] += 1
        top["win"] += h0["fin"] == 1
        top["top3"] += (h0["fin"] or 99) <= 3
        if h0["fin"] == 1:
            top["ret"] += next((y for c, y in r["pay"].get("単勝", []) if str(c) == str(h0["num"])), 0) / 100
        evs = [HorseEval(r["horses"][i]["num"], "", None, None, "", "", None, None, p_win=p[i], p_model=p[i])
               for i in order]
        plan = build_plan(evs, n_sims=2000)
        cost = 100 * len(plan.tickets)
        ret = sum(ticket_return(t, r["pay"]) for t in plan.tickets)
        bets_all["n"] += 1
        bets_all["cost"] += cost
        bets_all["ret"] += ret
        bets_all["hit"] += ret > 0
        conf = 0.5 * plan.p_any_hit + 0.4 * p[order[0]] + {"G1": .06, "G2": .04, "G3": .03}.get(r["grade"] or "", 0)
        weekly[r["date"][:4] + "-W" + str(_iso_week(r["date"]))].append((conf, cost, ret))
    sel = {"n": 0, "cost": 0, "ret": 0, "hit": 0}
    for wk, lst in weekly.items():
        for conf, cost, ret in sorted(lst, reverse=True)[:5]:
            sel["n"] += 1
            sel["cost"] += cost
            sel["ret"] += ret
            sel["hit"] += ret > 0
    return {"cal": cal, "top": top, "bets_all": bets_all, "bets_selected": sel, "logloss": logloss(data, P, ptab)}


def _iso_week(date: str) -> int:
    import datetime as dt
    return dt.date.fromisoformat(date).isocalendar()[1]


def ablation(data, P, ptab) -> list[tuple[str, float]]:
    base = logloss(data, P, ptab)
    out = []
    for comp, w in COMP_W.items():
        if not P.get(w):
            continue
        Q = dict(P)
        Q[w] = 0.0
        out.append((comp, logloss(data, Q, ptab) - base))
    out.sort(key=lambda x: -x[1])
    return out


def run(conn, start: str, end: str, save: bool = True) -> str:
    data = collect(conn, start, end)
    if not data:
        return "検証対象レースがありません。"
    ptab = pop_table(data)
    P0 = {**PARAMS, **(json.loads(PARAMS_PATH.read_text()) if PARAMS_PATH.exists() else {})}
    ll0 = logloss(data, P0, ptab)
    # 前半で調整し、後半で検証（過学習チェック）
    half = len(data) // 2
    Pt, llt = tune(data[:half], P0, ptab)
    ll_valid_before = logloss(data[half:], P0, ptab)
    ll_valid_after = logloss(data[half:], Pt, ptab)
    use = Pt if ll_valid_after <= ll_valid_before else P0
    m = evaluate(data[half:], use, ptab)
    abl = ablation(data, use, ptab)
    uniform = sum(math.log(len(r["horses"])) for r in data) / len(data)
    mkt = logloss(data, {**use, **{w: 0.0 for w in COMP_W.values()}, "market_w": 1.0}, ptab)
    L = ["# 予想モデルの検証（バックテスト, 自動生成）", "",
         f"- 検証期間: {start} 〜 {end}（{len(data)}レース）。その期間より前のデータだけで集計・学習して予想し、答え合わせ。",
         "- 前半で重みを調整し、後半（未使用データ）で成績を測定。",
         f"- 対数損失（小さいほど良い）: ランダム {uniform:.3f} / 人気のみ {mkt:.3f} / 調整前 {ll0:.3f} / "
         f"後半: 調整前 {ll_valid_before:.3f} → 調整後 {ll_valid_after:.3f}"
         f"（{'採用' if use is Pt else '改善しないため不採用'}）", ""]
    t = m["top"]
    L += ["## ◎（予測勝率1位）の成績（後半）", "",
          f"- {t['n']}レース: 勝率 {t['win'] / t['n']:.1%} / 複勝率 {t['top3'] / t['n']:.1%} / 単勝回収率 {t['ret'] / t['n']:.0%}", ""]
    for lab, b in (("全レース", m["bets_all"]), ("毎週の推奨上位5レース（本番と同じ選び方）", m["bets_selected"])):
        if b["n"]:
            L.append(f"- 推奨馬券・{lab}: {b['n']}レース、的中 {b['hit'] / b['n']:.1%}、投資 {b['cost']:,}円 → 払戻 {b['ret']:,}円（回収率 {b['ret'] / max(b['cost'], 1):.0%}）")
    L += ["", "## キャリブレーション（予測勝率と実際の勝率）", "", "| 予測勝率の帯 | 頭数 | 予測の平均 | 実際の勝率 |",
          "|---|--:|--:|--:|"]
    for (a, b), (n, s, w) in m["cal"].items():
        if n:
            L.append(f"| {a:.0%}〜{min(b, 1):.0%} | {n} | {s / n:.1%} | {w / n:.1%} |")
    L += ["", "## 要素ごとの貢献度（重みを0にした時の対数損失の悪化幅。大きいほど効いている）", "",
          "| 要素 | 悪化幅 |", "|---|--:|"]
    for comp, d in abl:
        L.append(f"| {GROUP_JA.get(comp, comp)} | {d:+.4f} |")
    L += ["", "## 採用した重み", "", "```json", json.dumps({k: round(v, 4) for k, v in use.items()}, indent=1), "```", ""]
    text = "\n".join(L)
    (ROOT / "docs" / "analysis").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "analysis" / "backtest.md").write_text(text, encoding="utf-8")
    if save and use is Pt and len(data) >= MIN_RACES_TO_SAVE:
        PARAMS_PATH.write_text(json.dumps({k: round(v, 5) for k, v in Pt.items()}, indent=1))
    elif len(data) < MIN_RACES_TO_SAVE:
        text += f"\n> 検証レースが {len(data)} 件と少ないため、調整した重みは保存していません（{MIN_RACES_TO_SAVE}件以上で保存）。\n"
        (ROOT / "docs" / "analysis" / "backtest.md").write_text(text, encoding="utf-8")
    return text


# ================================================================ 条件付きロジット（重みの学習）
CLOGIT_PATH = DATA_DIR / "model_clogit.json"


def _design(data, comps, ptab):
    import numpy as np
    X, y, groups, meta = [], [], [], []
    for r in data:
        hs = r["horses"]
        if not all(h["pop"] for h in hs) or not any(h["fin"] == 1 for h in hs):
            continue
        pk = [ptab[min(h["pop"], 18) - 1] for h in hs]
        z = sum(pk)
        start = len(X)
        for h, m in zip(hs, pk):
            X.append([h["raw"].get(c, 0.0) for c in comps] + [math.log(m / z)])
            y.append(1 if h["fin"] == 1 else 0)
            meta.append((r, h))
        groups.append((start, len(X)))
    return np.array(X, dtype=float), np.array(y), groups, meta


def _clogit_ll(Z, y, groups, w):
    import numpy as np
    s = Z @ w
    tot = 0.0
    for a, b in groups:
        e = np.exp(s[a:b] - s[a:b].max())
        p = e / e.sum()
        tot += -np.log(p[y[a:b] == 1]).sum()
    return tot / max(len(groups), 1)


def _clogit_fit(Z, y, groups, l2=1.0, iters=400, lr=0.5):
    import numpy as np
    w = np.zeros(Z.shape[1])
    w[-1] = 1.0
    mask = np.r_[np.ones(Z.shape[1] - 1), 0.0]
    for _ in range(iters):
        s = Z @ w
        grad = np.zeros_like(w)
        for a, b in groups:
            e = np.exp(s[a:b] - s[a:b].max())
            p = e / e.sum()
            grad += Z[a:b].T @ (y[a:b] - p)
        grad -= l2 * w * mask
        w += lr * grad / len(groups)
    return w


def learn(conn, train_from: str, train_to: str, test_from: str, test_to: str, save: bool = True) -> str:
    """市場（人気）を土台に、各要素の重みを条件付きロジットで学習し、未使用期間で検証する."""
    import numpy as np
    tr = collect(conn, train_from, train_to)
    te = collect(conn, test_from, test_to)
    comps = sorted(COMP_W)
    ptab = pop_table(tr)
    Xtr, ytr, gtr, _ = _design(tr, comps, ptab)
    Xte, yte, gte, mte = _design(te, comps, ptab)
    if len(gtr) < 300 or len(gte) < 100:
        return f"学習データ不足（学習 {len(gtr)} / 検証 {len(gte)} レース）"
    mu = Xtr[:, :-1].mean(0)
    sd = Xtr[:, :-1].std(0) + 1e-9

    def norm(X):
        Z = X.copy()
        Z[:, :-1] = (X[:, :-1] - mu) / sd
        return Z
    Ztr, Zte = norm(Xtr), norm(Xte)
    w = _clogit_fit(Ztr, ytr, gtr)
    w0 = np.zeros_like(w)
    w0[-1] = 1.0
    ll_mkt, ll_model = _clogit_ll(Zte, yte, gte, w0), _clogit_ll(Zte, yte, gte, w)
    better = ll_model < ll_mkt
    # 期待値（モデル確率 / 市場確率）で単勝・複勝を選んだ場合の回収率
    s = Zte @ w
    rows = []
    for a, b in gte:
        e = np.exp(s[a:b] - s[a:b].max())
        p = e / e.sum()
        m = np.exp(Xte[a:b, -1])
        for k, i in enumerate(range(a, b)):
            r, h = mte[i]
            wp = next((yy for c, yy in r["pay"].get("単勝", []) if str(c) == str(h["num"])), 0)
            pp = next((yy for c, yy in r["pay"].get("複勝", []) if str(c) == str(h["num"])), 0)
            rows.append((p[k], m[k], h["pop"], h["fin"], wp, pp))
    L = ["# 重みの学習（条件付きロジット, 自動生成）", "",
         f"- 学習: {train_from}〜{train_to}（{len(gtr)}レース） / 検証: {test_from}〜{test_to}（{len(gte)}レース, 学習に未使用）",
         f"- 検証の対数損失: 人気のみ {ll_mkt:.4f} → 学習モデル {ll_model:.4f}（{'改善: 採用' if better else '改善せず: 不採用'}）",
         f"- 市場（人気）の係数: {w[-1]:.3f}", "", "## 要素の重み（標準化後。+ は市場評価より上に見るべき要素）", "",
         "| 要素 | 重み |", "|---|--:|"]
    for i in np.argsort(-np.abs(w[:-1])):
        L.append(f"| {GROUP_JA.get(comps[i], comps[i])} | {w[i]:+.3f} |")
    L += ["", "## 期待値で選んだ場合の検証期間の回収率", "",
          "| 条件（モデル確率/市場確率, 最低確率） | 頭数 | 勝率 | 単勝回収 | 複勝回収 | 平均人気 |", "|---|--:|--:|--:|--:|--:|"]
    for thr in (1.1, 1.2, 1.3, 1.5):
        for minp in (0.05, 0.1, 0.15):
            sel = [x for x in rows if x[0] / x[1] >= thr and x[0] >= minp]
            if len(sel) < 30:
                continue
            L.append(f"| ≥{thr}, p≥{minp} | {len(sel)} | {sum(x[3] == 1 for x in sel) / len(sel):.1%} | "
                     f"{sum(x[4] for x in sel) / 100 / len(sel):.0%} | {sum(x[5] for x in sel) / 100 / len(sel):.0%} | "
                     f"{sum(x[2] for x in sel) / len(sel):.1f} |")
    text = "\n".join(L) + "\n"
    (ROOT / "docs" / "analysis").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "analysis" / "learned_weights.md").write_text(text, encoding="utf-8")
    if save and better:
        CLOGIT_PATH.write_text(json.dumps({
            "comps": comps, "mu": mu.tolist(), "sd": sd.tolist(), "w": w[:-1].tolist(), "w_market": float(w[-1]),
            "train": [train_from, train_to], "test": [test_from, test_to],
            "ll_market": ll_mkt, "ll_model": ll_model}, ensure_ascii=False, indent=1))
    return text
