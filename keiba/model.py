"""血統×実績×人的要因による勝率モデル.

スコア = 血統事前適性(A) + ニックス/牝系(B) + 実績データ集計(C) + 近走フォーム(D)
勝率   = softmax(スコア / T)。単勝オッズがあれば市場確率と対数線形でブレンド。
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field

from . import factors as F
from . import knowledge as K
from . import racing as R
from .analysis import Stats, draw_group, horse_history
from .config import distance_band, going_group

GRADE_LEVEL = {"G1": 6, "JG1": 6, "G2": 5, "JG2": 5, "G3": 4, "JG3": 4, "L": 3, "OP": 3,
               "3勝": 2, "2勝": 1, "1勝": 0, "未勝利": -1, "新馬": -1}

PARAMS = {
    "T": 1.0,             # softmax 温度 (calibrate で調整)
    "market_w": 0.45,     # 市場(オッズ)の重み
    "w_blood": 0.35,
    "w_nick": 0.12,
    "w_family": 0.08,
    "w_sire": 0.8, "w_going": 0.4, "w_damsire": 0.4, "w_nick_data": 0.3, "w_dam": 0.3,
    "w_jockey": 0.6, "w_trainer": 0.3, "w_jt": 0.3, "w_draw": 0.3, "w_pace": 0.3,
    "w_form": 2.4,
    "w_style": 0.8,       # 展開利(ペース×脚質×コース脚質バイアス)
    "w_dist": 0.6,        # その馬自身の距離適性(同距離帯の成績)
    "w_dist_data": 0.4,   # 父の距離別(ピンポイント距離)・距離延長/短縮の実績
    "w_pace_fit": 0.5,    # その馬自身の想定ペース型での成績
    # ---- その他の要因 (factors.py)
    "w_rotation": 0.6, "w_class": 0.6, "w_jockey_chg": 0.5, "w_weight": 0.8, "w_body": 0.6,
    "w_course_exp": 0.5, "w_direction": 0.4, "w_season": 0.4, "w_time": 0.35, "w_margin": 0.8,
    "w_inbreed": 0.3, "w_debut": 0.6, "w_field": 0.4,
    # コース形態・頭数・休み明け・追い上げ・上がり
    "w_course_type": 0.6, "w_sire_course_type": 0.4, "w_field_fit": 0.4, "w_sire_field": 0.3,
    "w_rest_fit": 0.4, "w_sire_rest": 0.3, "w_closing": 0.8, "w_agari": 0.6,
    "w_expert": 0.15,     # 専門家見解（実績で裏付けのあるもののみ）
    "w_repeat": 0.3, "w_momentum": 0.5, "w_meet": 0.6,   # 傾向の波
    "w_value": 1.0,
    "w_cond": 0.25,
    "w_course_bias": 0.6,
    "w_family_fit": 0.5,
    "w_country": 0.5,       # 国別タイプ × 条件の人気比    # 牝系（兄弟・2代母の一族）の条件適性   # 開催の進み具合・馬場状態による枠/脚質のバイアス   # 人気帯内の相対指標（テスト期間でのロジット係数 0.24 に合わせる）   # 妙味条件（人気帯×条件の回収率の突出）の補正の強さ
}

AXIS_JA = {"turf": "芝", "dirt": "ダート", "sprint": "短距離", "mile": "マイル", "middle": "中距離",
           "long": "長距離", "heavy": "道悪", "kire": "瞬発力", "jizoku": "持続力", "power": "パワー",
           "early": "早熟性", "growth": "成長力"}


@dataclass
class HorseEval:
    number: int | None
    name: str
    sire: str | None
    damsire: str | None
    sire_line: str
    damsire_line: str
    jockey: str | None
    odds: float | None
    components: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    score: float = 0.0
    p_win: float = 0.0
    p_top3: float = 0.0
    p_model: float = 0.0
    p_market: float | None = None
    crosses: list = field(default_factory=list)
    family: str | None = None
    style: str | None = None
    esi: float | None = None
    dist_change: str = "初"
    best_distance: float | None = None
    value_segments: list = field(default_factory=list)
    value_edge: float = 0.0     # 妙味条件（回収率の傾向）による補正（対数）
    cond_score: float = 0.0     # 人気帯内の相対指標（条件が合わない人気馬＝マイナス）
    pop_band: str | None = None  # 人気帯（単勝オッズ順、無ければ出馬表の人気）
    pop_rank: int | None = None
    pop_estimated: bool = False   # 前売り前でモデルの評価順を人気の代わりにしている
    blood_upside: float = 0.0    # 血統要素だけの合計（大穴★の選定用）


OPPOSITE_BAND = {"sprint": {"long": -0.5, "middle": -0.2}, "mile": {"long": -0.3},
                 "middle": {"sprint": -0.3}, "long": {"sprint": -0.5, "mile": -0.2}}


def race_demand(card: dict) -> dict:
    s = card.get("surface") or "芝"
    band = distance_band(card.get("distance") or 1600)
    d = {("turf" if s == "芝" else "dirt"): 1.2, band: 1.0}
    # 反対側の適性が強すぎる血統への減点（芝血統のダート替わり、長距離血統の短距離戦など）
    d["dirt" if s == "芝" else "turf"] = -0.3 if s == "芝" else -0.5
    d.update(OPPOSITE_BAND[band])
    if going_group(card.get("going")) == "soft":
        d["heavy"] = 0.8
    course = K.courses()["courses"].get(card.get("course") or "", {})
    cd = course.get("turf" if s == "芝" else "dirt", {}).get("demand", {})
    for a, w in cd.items():
        d[a] = d.get(a, 0) + 0.6 * w
    return d


def _apt_str(apt: dict, demand: dict) -> str:
    keys = sorted(demand, key=lambda a: -abs(demand[a]))[:4]
    return " / ".join(f"{AXIS_JA[a]}{apt[a]:+.1f}" for a in keys)


def form_score(history: list[dict], card: dict) -> tuple[float, str | None]:
    if not history:
        return 0.0, None
    target = GRADE_LEVEL.get(card.get("grade") or "", 2)
    s = card.get("surface")
    num = den = 0.0
    for i, h in enumerate(history[:5]):
        f, n = h.get("finish"), h.get("n_runners") or 16
        if f is None:
            continue
        perf = 1 - (f - 1) / max(n - 1, 1)
        perf += 0.08 * (GRADE_LEVEL.get(h.get("grade") or "", target) - target)
        w = 0.8 ** i * (1.0 if h.get("surface") == s else 0.5)
        num += w * perf
        den += w
    if not den:
        return 0.0, None
    avg = num / den
    fins = "-".join(str(h.get("finish") or "×") for h in history[:5])
    return avg - 0.5, f"近走 {fins}（フォーム指数 {avg:.2f}）"


def evaluate_race(card: dict, st: Stats | None = None, conn=None, params: dict | None = None,
                  n_sims: int = 20000, seed: int = 0) -> list[HorseEval]:
    P = {**PARAMS, **(params or {})}
    s = card.get("surface") or "芝"
    band = distance_band(card.get("distance") or 1600)
    soft = going_group(card.get("going")) == "soft"
    course = card.get("course")
    demand = race_demand(card)
    dsum = sum(abs(v) for v in demand.values()) or 1
    has_data = st is not None and st.n_races > 0
    evals: list[HorseEval] = []

    # 1) 血統・履歴・脚質プロファイルを先に揃える（展開予想に全馬の脚質が必要）
    prepared = []
    for e in card["entries"]:
        ped = e.get("pedigree") or {}
        sire, dam, damsire = e.get("sire"), e.get("dam"), e.get("damsire")
        if conn is not None and e.get("horse_id"):
            row = conn.execute("SELECT * FROM horses WHERE horse_id=?", (e["horse_id"],)).fetchone()
            if row:
                sire, dam, damsire = sire or row["sire"], dam or row["dam"], damsire or row["damsire"]
                if not ped and row["pedigree"]:
                    ped = json.loads(row["pedigree"])
        sire = sire or ped.get("S")
        dam = dam or ped.get("D")
        damsire = damsire or ped.get("DS")
        sl = K.resolve_line(sire, ped, "S")
        dsl = K.resolve_line(damsire, ped, "DS")
        hist = list(e.get("recent") or [])
        if conn is not None and e.get("horse_id"):
            # 出馬表の近走(全レース)と DB の履歴(第7R以降のみ・ラップ型/上がり順位つき)を日付で統合。
            # 同じ日のレースは DB 側(情報が多い)を優先する
            dbh = horse_history(conn, e["horse_id"], before_date=card.get("date"))
            by_date = {h.get("date"): h for h in hist if h.get("date")}
            for h in dbh:
                by_date[h.get("date")] = {**by_date.get(h.get("date"), {}), **{k: v for k, v in h.items() if v is not None}}
            if by_date:
                hist = sorted(by_date.values(), key=lambda h: h.get("date") or "", reverse=True)
        prof = R.build_profile(hist, card, e, sire, sl, st.sire_style.get(sire) if has_data else None)
        fx = F.extract(e, hist, card, st if has_data else None)
        prepared.append((e, ped, sire, dam, damsire, sl, dsl, hist, prof, fx))
    ctx = F.field_context([p[9] for p in prepared])

    # 2) 展開予想
    fc = R.forecast_pace([(p[0], p[8]) for p in prepared], card, st if has_data else None)
    card["_forecast"] = fc          # レポートの展開予想欄で使う
    if not card.get("expected_pace"):
        card = {**card, "expected_pace": fc.pace_type}

    # 傾向の波（同名レースの連続好走血統・今の開催の馬場傾向）: レース単位で一度だけ計算
    from . import trend as TR
    rh = TR.race_history(conn, card) if conn is not None else None
    mb = TR.meet_bias(conn, card.get("course"), card.get("surface"), card.get("date")) if conn is not None else None
    if rh:
        card["_race_history"] = rh
    if mb:
        card["_meet_bias"] = mb

    prepared_ctx = {}
    for e, ped, sire, dam, damsire, sl, dsl, hist, prof, fx in prepared:
        prepared_ctx[e.get("number")] = (e, sire, sl, damsire, dsl, hist, fx)
        he = HorseEval(e.get("number"), e["name"], sire, damsire, sl, dsl, e.get("jockey"), e.get("odds"))
        comp, ev = {}, []

        # A. 血統事前適性
        apt_s = K.sire_apt(sire, sl)
        apt_d = K.sire_apt(damsire, dsl, role="damsires")
        apt = {a: 0.65 * apt_s[a] + 0.35 * apt_d[a] for a in K.AXES}
        age = e.get("age")
        dem = dict(demand)
        if age == 2:
            dem["early"] = dem.get("early", 0) + 0.6
        elif age == 3:
            dem["early"] = dem.get("early", 0) + 0.3
        elif age and age >= 5:
            dem["growth"] = dem.get("growth", 0) + 0.4
        fit = sum(apt[a] * w for a, w in dem.items()) / (sum(abs(v) for v in dem.values()) or dsum)
        comp["blood"] = P["w_blood"] * fit
        ev.append(f"父{sire or '不明'}（{sl}）× 母父{damsire or '不明'}（{dsl}）: 条件適性 {fit:+.2f}［{_apt_str(apt, dem)}］")
        sinfo = K.sires().get(sire or "", {})
        if sinfo.get("note"):
            ev.append(f"父の特徴: {sinfo['note']}")
        dinfo = K.sires().get(damsire or "", {})
        if dinfo.get("as_damsire"):
            ev.append(f"母父の特徴: {dinfo['as_damsire']}")

        # B. ニックス・牝系・クロス
        nr, nnote = K.nick_prior(sire, sl, damsire, dsl)
        if nr:
            # ニックスは『条件に合う血統』の時だけ効かせる（適性が低い条件では割り引く）
            comp["nick"] = P["w_nick"] * nr * max(0.0, min(1.0, (fit + 0.3) / 1.2))
            ev.append(f"ニックス評価 {nr:+.1f}: {nnote[0] if nnote else ''}")
        fam, fb = K.detect_family(ped, dam)
        he.family = fam
        if fam:
            comp["family"] = P["w_family"] * fb
            ev.append(f"牝系: {fam}系（{K.families()[fam]['trait']}）")
        from . import tailfemale as TF
        xs = TF.crosses(e.get("horse_id"))
        he.crosses = (xs if xs is not None else K.detect_crosses(ped))[:3]
        if he.crosses:
            ev.append("クロス: " + "、".join(f"{n} {g}" for n, g in he.crosses))

        # C. 実績データ
        if has_data:
            def lr(keys, k=20.0):
                return st.log_ratio([kk for kk in keys if None not in kk], k)
            v, n = lr([("line_s", sl, s), ("line", sl, s, band), ("sire", sire, s, band),
                       ("sire_cs", sire, course, s, band)])
            comp["sire_data"] = P["w_sire"] * v
            c = st.get("sire", sire, s, band)
            if c.n:
                ev.append(f"実績: {sire}産駒 {s}{band_ja(band)} 勝率{c.win_rate:.1%} 複勝率{c.top3_rate:.1%}（{c.n}走）")
            cc = st.get("sire_cs", sire, course, s, band)
            if cc.n >= 5:
                ev.append(f"実績: {sire}産駒 {course}{s}{band_ja(band)} 複勝率{cc.top3_rate:.1%}（{cc.n}走）")
            if soft:
                v, _ = lr([("line_going", sl, s, "soft"), ("sire_going", sire, s, "soft")])
                comp["going"] = P["w_going"] * v
                cg = st.get("sire_going", sire, s, "soft")
                if cg.n:
                    ev.append(f"道悪実績: {sire}産駒 {s}道悪 複勝率{cg.top3_rate:.1%}（{cg.n}走）")
            v, _ = lr([("dsline", dsl, s, band), ("damsire", damsire, s, band)])
            comp["damsire_data"] = P["w_damsire"] * v
            v, n = lr([("nickline", sl, dsl), ("nick", sire, dsl)])
            comp["nick_data"] = P["w_nick_data"] * v
            cn = st.get("nick", sire, dsl)
            if cn.n >= 10:
                ev.append(f"実測ニックス: {sire}×母父{dsl} 複勝率{cn.top3_rate:.1%}（{cn.n}走）")
            if dam:
                v, n = lr([("dam", dam)], k=10)
                comp["dam_data"] = P["w_dam"] * v
                cd = st.get("dam", dam)
                if cd.n >= 3:
                    ev.append(f"兄弟姉妹(母{dam}産駒) 複勝率{cd.top3_rate:.1%}（{cd.n}走）")
            j, t = e.get("jockey"), e.get("trainer")
            if j:
                v, _ = lr([("jockey", j), ("jockey_cs", j, course, s)], k=50)
                comp["jockey"] = P["w_jockey"] * v
                cj = st.get("jockey_cs", j, course, s)
                if cj.n >= 10:
                    ev.append(f"騎手 {j} {course}{s} 複勝率{cj.top3_rate:.1%}（{cj.n}騎乗）")
            if t:
                v, _ = lr([("trainer", t)], k=50)
                comp["trainer"] = P["w_trainer"] * v
            if j and t:
                v, _ = lr([("jockey", j), ("jt", j, t)], k=20)
                comp["jt"] = P["w_jt"] * v
                cjt = st.get("jt", j, t)
                if cjt.n >= 5:
                    ev.append(f"騎手×調教師 {j}×{t} 複勝率{cjt.top3_rate:.1%}（{cjt.n}回）")
            if e.get("gate") and card.get("distance"):
                v, _ = lr([("draw_all", course, s, card["distance"]),
                           ("draw", course, s, card["distance"], draw_group(e["gate"]))], k=50)
                comp["draw"] = P["w_draw"] * v
            pace = card.get("expected_pace")
            if pace:
                v, _ = lr([("line_pace", sl, pace), ("sire_pace", sire, pace)])
                comp["pace"] = P["w_pace"] * v

        # D. 近走フォーム
        fs, fnote = form_score(hist, card)
        comp["form"] = P["w_form"] * fs
        if fnote:
            ev.append(fnote)

        # E. 展開・脚質
        he.style, he.esi = prof.style, prof.esi
        src = {"history": "近走の通過順", "card": "出馬表情報", "sire": "父産駒の傾向から推定"}[prof.esi_source or "sire"]
        sd = "・".join(f"{k}{v}" for k, v in prof.style_dist.most_common()) if prof.style_dist else ""
        sa, snote = R.style_advantage(prof, fc, card, st if has_data else None)
        comp["style"] = P["w_style"] * sa
        ev.append(f"脚質: {prof.style}（テン指数{prof.esi:.2f}・{src}{'／' + sd if sd else ''}）→ 展開利 {sa:+.2f}［{snote}］")
        pf, pnote = R.pace_fit(prof, card["expected_pace"])
        if pnote:
            comp["pace_fit"] = P["w_pace_fit"] * pf
            ev.append(f"ペース適性: {pnote}")

        # F. 距離
        he.dist_change, he.best_distance = prof.dist_change, prof.best_distance
        if prof.dist_note:
            comp["distance"] = P["w_dist"] * prof.dist_fit
            ev.append(f"距離適性: {prof.dist_note}（評価{prof.dist_fit:+.2f}）")
        if has_data and card.get("distance"):
            keys = [k for k in [("sire", sire, s, band), ("sire_dist", sire, s, card["distance"])] if None not in k]
            v1, n1 = st.log_ratio(keys) if keys else (0.0, 0)
            keys2 = [k for k in [("dchg", s, band, prof.dist_change), ("line_dchg", sl, s, prof.dist_change),
                                 ("sire_dchg", sire, s, prof.dist_change)] if None not in k]
            v2, _ = st.log_ratio(keys2) if keys2 else (0.0, 0)
            comp["dist_data"] = P["w_dist_data"] * (0.6 * v1 + 0.4 * v2)
            cdd = st.get("sire_dist", sire, s, card["distance"])
            if cdd.n >= 5:
                ev.append(f"実績: {sire}産駒 {s}{card['distance']}m ピンポイント複勝率{cdd.top3_rate:.1%}（{cdd.n}走）")
            if prof.dist_change in ("延長", "短縮"):
                cdc = st.get("line_dchg", sl, s, prof.dist_change)
                if cdc.n >= 20:
                    ev.append(f"距離{prof.dist_change}: {sl}の{s}距離{prof.dist_change}時 複勝率{cdc.top3_rate:.1%}（{cdc.n}走）")
        elif prof.dist_change in ("延長", "短縮"):
            ev.append(f"距離{prof.dist_change}（前走{hist[0].get('distance')}m→今回{card.get('distance')}m）")

        # G. その他の多角的要因（ローテ・斤量・馬体重・クラス・乗替・季節・コース実績・回り・タイム指数・クロス・新馬・頭数・妙味）
        xc, xev = F.score(fx, ctx, card, e, st if has_data else None, P, sire, e.get("trainer"), e.get("jockey"),
                          prof.style, [n for n, g in (TF.crosses(e.get("horse_id")) or K.detect_crosses(ped)) if sum(int(x) for x in g.split("×")) <= 9]
                          if ped else None)
        comp.update(xc)
        ev.extend(xev)

        # I. 傾向の波
        if rh:
            v, notes = 0.0, []
            for attr, val, wgt, lab in (("sire", sire, 0.5, "父"), ("sire_line", sl, 0.3, "父系統"),
                                        ("damsire_line", dsl, 0.3, "母父系統"), ("style", prof.style, 0.2, "脚質"),
                                        ("gate", TR.gate_group(e.get("gate")), 0.15, "枠")):
                n, tot = rh["streaks"].get((attr, val), (0, 0))
                if n >= 2 or (attr in ("sire", "sire_line", "damsire_line") and tot >= 3):
                    v += wgt * min(max(n, tot / 2), 4)
                    notes.append(f"{lab}{val}（直近{n}年連続・過去{len(rh['years'])}回中{tot}回3着内）")
            if v:
                comp["repeat_blood"] = P["w_repeat"] * v
                ev.append(f"{rh['key']}の傾向の波: " + "、".join(notes))
        if conn is not None:
            mvals = []
            for who, name, wgt in (("sire", sire, 1.0), ("sire_line", sl, 0.5)):
                m = TR.momentum(conn, who, name, card.get("course"), card.get("surface"), card.get("date"))
                if m and m[1] >= 10 and m[3] >= 30:
                    p1s = (m[0] * m[1] + 30 * m[2]) / (m[1] + 30)
                    mv = math.log(max(p1s, 1e-3) / max(m[2], 1e-3))
                    mvals.append(wgt * mv)
                    if who == "sire" and abs(mv) >= 0.2:
                        ev.append(f"勢い: {name}産駒の{card.get('course')}{card.get('surface')} 直近1年 複勝率{m[0]:.1%}（{m[1]}走）"
                                  f" vs それ以前 {m[2]:.1%} → {'上昇中' if mv > 0 else '下降中'}")
            if mvals:
                comp["momentum"] = P["w_momentum"] * sum(mvals)
        if mb:
            sv = "前" if (prof.esi or 0) >= 0.62 else "後"
            parts, v = [], 0.0
            for key, lab in ((("style", sv), f"{'前に行く馬' if sv == '前' else '差し・追込'}"),
                             (("gate", TR.gate_group(e.get("gate"))), f"{TR.gate_group(e.get('gate'))}枠")):
                if key in mb["rates"]:
                    rt, n = mb["rates"][key]
                    rs = (rt * n + 40 * mb["base"]) / (n + 40)
                    lv = math.log(max(rs, 1e-3) / mb["base"])
                    v += lv
                    if abs(lv) >= 0.15:
                        parts.append(f"{lab}の複勝率{rt:.0%}（全体{mb['base']:.0%}）")
            comp["meet_bias"] = P["w_meet"] * v
            if parts:
                ev.append(f"今の開催の馬場傾向（直近2週・{card.get('course')}{card.get('surface')}）: " + "、".join(parts))

        # 牝系の条件適性: 兄弟・2代母の一族が同じ条件（芝ダ・距離帯・馬場）で人気以上に走るか。初めての条件ほど重視
        if conn is not None:
            from . import family as FAM
            fv, fn = FAM.family_fit(conn, card, e.get("horse_id"), dam)
            if fv:
                comp["family_fit"] = P["w_family_fit"] * fv
            if fn:
                ev.append("牝系: " + "、".join(fn[:3]))

        # 国別タイプ（日本型・米国型・欧州型）× 条件の人気比
        if conn is not None:
            from . import country as CT
            cv, clab, cn = CT.country_fit(conn, card, sl, dsl,
                                          R.dist_change(hist[0].get("distance") if hist else None, card.get("distance")))
            if cv:
                comp["country_fit"] = P["w_country"] * cv
            ev.append(f"国別タイプ: {clab}" + (f"（{'、'.join(cn)}）" if cn else ""))

        # コースバイアス: 開催の進み具合（開幕週〜最終週）・馬場状態で、この枠/脚質が普段より有利か
        if conn is not None:
            cbv, cbn = TR.course_bias(conn, card, e.get("gate"), (prof.esi or 0) >= 0.62 if prof.esi is not None else None)
            if cbv:
                comp["course_bias"] = P["w_course_bias"] * cbv
            if cbn:
                ev.append("コースバイアス: " + "、".join(cbn))

        # H. 専門家見解（expert_notes.json）: 見解（出典の信頼度）と実績を、該当走の数に応じて合成して小さく反映
        from . import experts as X
        for note, chk in X.applicable(card, e, sire, sl, damsire, dsl, hist):
            sign = 1 if note.get("direction", "+") == "+" else -1
            verdict = chk.get("verdict", "未検証")
            # 重み = 見解の事前の重み（出典の信頼度×向き）と、実績（強さ×時期の安定度）の合成（experts.verify）。
            # データが少ない条件は見解寄り、データがはっきり逆なら実績の向き。未検証の新しい見解は見解の向きで
            w_ = chk.get("weight") if chk else None
            if w_ is None and not note.get("condition", {}).get("qualitative"):
                w_ = sign * X.credibility(note) * 0.5
            if w_:
                comp["expert"] = comp.get("expert", 0.0) + P["w_expert"] * w_
            ev.append(f"専門家見解[{note.get('author', '')}]: {note.get('summary', '')}（{'プラス' if sign > 0 else 'マイナス'}／"
                      f"実績検証: {verdict}{'・z%+.1f' % chk['z'] if 'z' in chk else ''}"
                      f"{'・直近1年z%+.1f' % chk['recent_z'] if chk.get('recent_z') is not None else ''}"
                      f"{'・安定度%.2f' % chk['stability'] if 'stability' in chk else ''}"
                      f"{' → 実績の向き（見解と逆）で反映' if verdict.startswith('逆の傾向') else ''}"
                      f"{'・反映%+.2f' % w_ if w_ else ''}）")

        he.components = comp
        he.blood_upside = sum(comp.get(k, 0.0) for k in BLOOD_COMPS)
        he.evidence = ev
        he.score = sum(comp.values())
        evals.append(he)

    # 学習済みの条件付きロジット重みがあれば、それでスコアを付け直す（validate.learn が生成）
    cl = _load_clogit()
    if cl is not None:
        idx = {c: i for i, c in enumerate(cl["comps"])}
        for h in evals:
            raw = {c: (v / P[_COMP_W[c]] if P.get(_COMP_W.get(c, ""), 0) else 0.0)
                   for c, v in h.components.items() if c in _COMP_W}
            h.score = sum(cl["w"][i] * ((raw.get(c, 0.0) - cl["mu"][i]) / cl["sd"][i]) for c, i in idx.items())
            h.score += h.components.get("expert", 0.0)   # 専門家見解は学習外の小さな補正として加える

    # 妙味条件（人気帯×条件の回収率）: 人気は単勝オッズ順（無ければ出馬表の人気）。
    # 厳格基準の条件は☆の候補、それ以外の確認済み条件も含め、実績の突出度に応じた相対的な補正としてスコアに加える
    _mark_value_segments(card, evals, prepared_ctx)
    for h in evals:
        h.score += P["w_value"] * h.value_edge + P["w_cond"] * h.cond_score

    # 確率化
    T = 1.0 if cl is not None else P["T"]
    mx = max(h.score for h in evals)
    ex = [math.exp((h.score - mx) / T) for h in evals]
    z = sum(ex)
    for h, x in zip(evals, ex):
        h.p_model = x / z
    odds = [h.odds for h in evals]
    if all(o and o > 1 for o in odds):
        inv = [1 / o for o in odds]
        zi = sum(inv)
        for h, v in zip(evals, inv):
            h.p_market = v / zi
        if cl is not None:
            # 学習モデル: スコア + 市場係数 × log(市場確率)
            lg = [h.score + cl["w_market"] * math.log(h.p_market) for h in evals]
        else:
            mw = P["market_w"]
            lg = [(1 - mw) * math.log(h.p_model) + mw * math.log(h.p_market) for h in evals]
        m2 = max(lg)
        ex = [math.exp(v - m2) for v in lg]
        z = sum(ex)
        for h, x in zip(evals, ex):
            h.p_win = x / z
    else:
        for h in evals:
            h.p_win = h.p_model

    if n_sims:
        top3 = simulate_top3([h.p_win for h in evals], n_sims, seed)
        for h, p in zip(evals, top3["top3"]):
            h.p_top3 = p
    evals.sort(key=lambda h: -h.p_win)
    return evals


_COMP_W = {"blood": "w_blood", "nick": "w_nick", "family": "w_family", "sire_data": "w_sire", "going": "w_going",
           "damsire_data": "w_damsire", "nick_data": "w_nick_data", "dam_data": "w_dam", "jockey": "w_jockey",
           "trainer": "w_trainer", "jt": "w_jt", "draw": "w_draw", "pace": "w_pace", "form": "w_form",
           "style": "w_style", "pace_fit": "w_pace_fit", "distance": "w_dist", "dist_data": "w_dist_data",
           "rotation": "w_rotation", "class": "w_class", "jockey_chg": "w_jockey_chg", "weight": "w_weight",
           "body_weight": "w_body", "course_exp": "w_course_exp", "direction": "w_direction", "season": "w_season",
           "time_index": "w_time", "margin": "w_margin", "inbreed": "w_inbreed", "debut": "w_debut",
           "field_size": "w_field", "course_type": "w_course_type", "sire_course_type": "w_sire_course_type",
           "field_fit": "w_field_fit", "sire_field": "w_sire_field", "rest_fit": "w_rest_fit",
           "sire_rest": "w_sire_rest", "closing": "w_closing", "agari": "w_agari",
           "repeat_blood": "w_repeat", "momentum": "w_momentum", "meet_bias": "w_meet",
           "course_bias": "w_course_bias",
           "family_fit": "w_family_fit", "country_fit": "w_country"}
COMP_W = _COMP_W
# 血統の要素（大穴★の選定に使う。8番人気以下でこの合計が最大の馬は、人気薄全体より3着内率が18〜28%高い: 2024・2025〜とも）
BLOOD_COMPS = ("blood", "sire_data", "damsire_data", "nick_data", "nick", "dam_data", "family", "family_fit", "dist_data",
               "going", "sire_course_type", "sire_field", "sire_rest", "repeat_blood", "expert", "country_fit", "inbreed",
               "momentum")
USE_CLOGIT = True


def _load_clogit():
    from .config import DATA_DIR
    p = DATA_DIR / "model_clogit.json"
    if not USE_CLOGIT or not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _mark_value_segments(card, evals, prepared_ctx):
    from . import value as V
    from .config import going_group as _gg
    odds_rank = {}
    with_odds = [h for h in evals if h.odds]
    for i, h in enumerate(sorted(with_odds, key=lambda h: h.odds), 1):
        odds_rank[h.number] = i
    # オッズも人気も無い（前売り前）ときは、モデルの評価順を人気の代わりに使う（★の選定・人気帯の指標用）
    est_rank = {}
    if not with_odds and not any(e.get("popularity") for e, *_ in prepared_ctx.values()):
        for i, h in enumerate(sorted(evals, key=lambda h: -h.score), 1):
            est_rank[h.number] = i
    a = K.course_attrs(card.get("course"), card.get("surface"), card.get("distance"))
    for h in evals:
        e, sire, sl, damsire, dsl, hist, fx = prepared_ctx.get(h.number, ({}, None, None, None, None, [], {}))
        pop = odds_rank.get(h.number) or e.get("popularity")   # 人気帯の指標は実際の人気（オッズ順）だけで
        h.pop_estimated = pop is None and h.number in est_rank
        h_pop_for_star = pop or est_rank.get(h.number)          # ★の選定だけはモデルの評価順で代用可
        prev_style = None
        if hist:
            prev_style, _ = R.style_from_passing(hist[0].get("passing"), hist[0].get("n_runners"))
        ctx = {"sire": sire, "sire_line": sl, "damsire": damsire, "damsire_line": dsl, "jockey": e.get("jockey"),
               "trainer": e.get("trainer"), "course": card.get("course"), "surface": card.get("surface"),
               "distance": card.get("distance"), "gate": e.get("gate"), "prev_style": prev_style,
               "gg": _gg(card.get("going")), "dchg": R.dist_change(hist[0].get("distance") if hist else None,
                                                                   card.get("distance")),
               "interval": fx.get("interval"), "n_runners": len(card.get("entries") or []), "season": fx.get("season"),
               "grade": card.get("grade"), "age": e.get("age"), "sex": e.get("sex"),
               "straight_cat": a["straight_cat"], "slope": a["slope"], "pop_b": V.pop_bucket(pop)}
        segs = V.matching(ctx)
        h.value_segments = segs
        allsegs = segs + V.matching(ctx, "win") + V.matching(ctx, "place") + V.matching(ctx, "fade")
        h.value_edge, used = V.edge(allsegs)
        # 人気帯内の相対指標（条件が合わない人気馬は割引、条件が合う人気薄は加点）
        h.pop_band = ctx["pop_b"]
        h.pop_rank = h_pop_for_star
        h.cond_score, parts = V.cond_score(ctx)
        # 検証済みの傾向（3期間で回収率100%超の角度×人気帯）: 材料として根拠欄に出す（スコアには足さない）
        try:
            from . import angles as AN
            arow = {**ctx, "going": card.get("going"), "prev_fin": hist[0].get("finish") if hist else None,
                    "prev_pop": hist[0].get("popularity") if hist else None}
            h.evidence += AN.match(arow, pop)
        except Exception:   # noqa: BLE001
            pass
        neg = [p for p in parts if p[0] <= -0.1][:3]
        pos = [p for p in parts[::-1] if p[0] >= 0.1][:3]
        fmt = lambda p: f"{p[1]}＝{' / '.join(map(str, p[2]))}（複勝率{p[3][2]:.0%}・{p[3][1]}走, 平均{p[3][3]:.0%}）"
        if h.cond_score <= -0.2 and neg:
            h.evidence.append(f"{ctx['pop_b']}としては来ない条件（指標{h.cond_score:+.2f}）: " + "、".join(map(fmt, neg)))
        elif h.cond_score >= 0.2 and pos:
            h.evidence.append(f"{ctx['pop_b']}としては走る条件（指標{h.cond_score:+.2f}）: " + "、".join(map(fmt, pos)))
        strict_ids = {id(x) for x in segs}
        for e_, sg, n, roi in used:
            if id(sg) not in strict_ids and abs(e_) < 0.08:
                continue
            kind = sg.get("kind", "win")
            if kind == "fade":
                d_, c_, t_ = sg["discover"], sg["confirm"], sg["test"]
                h.evidence.append(f"来ない条件: {sg['dim']}＝{' / '.join(map(str, sg['key']))}（{sg['pop']}）"
                                  f" 複勝率 発見{d_['t3']:.0%}(平均{d_['base_t3']:.0%})→確認{c_['t3']:.0%}(平均{c_['base_t3']:.0%})"
                                  f"→直近{t_['t3']:.0%}（{t_['n']}走）→ 評価{e_:+.2f}")
                continue
            h.evidence.append(f"{'妙味条件(厳格)' if id(sg) in strict_ids else '回収率の傾向'}: "
                              f"{sg['dim']}＝{' / '.join(map(str, sg['key']))}（{sg['pop']}）"
                              f" {'単勝' if kind == 'win' else '複勝'}回収率 発見{sg['discover'][kind + '_roi']:.0%}"
                              f"→確認{sg['confirm'][kind + '_roi']:.0%}→直近{sg['test'][kind + '_roi']:.0%}"
                              f"（計{n}走・{roi:.0%}）→ 評価{'+' if e_ >= 0 else ''}{e_:.2f}")


def band_ja(band: str) -> str:
    return AXIS_JA[band]


def simulate_top3(p: list[float], n_sims: int = 20000, seed: int = 0) -> dict:
    """Harville モデルに基づくモンテカルロ. 各馬の3着内率と、着順サンプルを返す."""
    rng = random.Random(seed)
    n = len(p)
    cnt = [0] * n
    samples = []
    for _ in range(n_sims):
        rem = list(range(n))
        w = list(p)
        order = []
        for _k in range(min(3, n)):
            tot = sum(w[i] for i in rem)
            r = rng.random() * tot
            acc = 0.0
            for idx, i in enumerate(rem):
                acc += w[i]
                if acc >= r:
                    order.append(i)
                    rem.pop(idx)
                    break
            else:
                order.append(rem.pop())
        for i in order:
            cnt[i] += 1
        samples.append(tuple(order))
    return {"top3": [c / n_sims for c in cnt], "samples": samples}
