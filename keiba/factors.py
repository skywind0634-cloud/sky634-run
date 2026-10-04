"""血統・距離・展開以外の多角的な要因.

| 要因 | 中身 |
|---|---|
| ローテーション | 前走からの間隔（連闘/中1週/…/休み明け/長期休養明け）、叩き2戦目 |
| 斤量 | 出走馬平均との差、前走からの増減 |
| 馬体重 | 前走比の増減（当日発表後に反映）|
| クラス | 昇級/降級/同クラス、重賞初挑戦 |
| 騎手 | 継続騎乗か乗り替わりか、乗り替わり先の騎手の格 |
| 季節×性別・年齢 | 夏の牝馬、秋の3歳、冬の高齢馬など |
| コース実績 | 同コース(場×芝ダ)の経験・勝利、左右回りの得手不得手 |
| タイム指数 | 走破タイムを場・芝ダ・距離・馬場の基準タイムで標準化した指数（直近と最高）と、勝ち馬とのタイム差 |
| インブリード | 5代内クロスの有無・祖先別の実績 |
| 新馬 | 父・調教師の新馬戦成績 |
| 頭数 | 少頭数/多頭数 × 脚質 |
| 妙味 | 種牡馬・騎手の単勝回収率（過剰人気/過小評価の傾向）|

実績データが十分(出走数しきい値以上)ならデータ、足りない間は PRIOR の小さな事前効果を使う。
"""
from __future__ import annotations

import datetime as dt
import statistics

from .config import going_group

GRADE_LEVEL = {"G1": 6, "JG1": 6, "G2": 5, "JG2": 5, "G3": 4, "JG3": 4, "L": 3, "OP": 3,
               "3勝": 2, "2勝": 1, "1勝": 0, "未勝利": -1, "新馬": -1}

# 事前効果（log-ratio 相当・控えめ）。データが貯まると実測で置換
PRIOR = {
    "interval": {"連闘": -0.05, "中1週": 0.0, "中2-4週": 0.05, "中5-8週": 0.0,
                 "休み明け": -0.1, "長期休養明け": -0.25, "初出走": 0.0},
    "class": {"昇級": -0.12, "同クラス": 0.0, "降級": 0.12, "初": 0.0},
    "jockey": {"継続": 0.03, "乗替": -0.03, "初": 0.0},
    "carried": {"斤量増": -0.05, "同斤量": 0.0, "斤量減": 0.05, "初": 0.0},
    "body": {"大幅減": -0.12, "減": 0.0, "増減なし": 0.02, "増": 0.02, "大幅増": -0.08},
    "course_exp": {"初コース": -0.03, "経験あり": 0.0, "好走あり": 0.06, "勝利あり": 0.1},
}
LABEL = {"interval": "ローテーション", "class": "クラス", "jockey": "騎手", "carried": "斤量",
         "body": "馬体重", "course_exp": "コース実績"}


def interval_bucket(days: int | None) -> str:
    if days is None:
        return "初出走"
    if days <= 8:
        return "連闘"
    if days <= 17:
        return "中1週"
    if days <= 35:
        return "中2-4週"
    if days <= 63:
        return "中5-8週"
    if days <= 180:
        return "休み明け"
    return "長期休養明け"


def body_bucket(diff: int | None) -> str | None:
    if diff is None:
        return None
    if diff <= -10:
        return "大幅減"
    if diff <= -4:
        return "減"
    if diff <= 3:
        return "増減なし"
    if diff <= 9:
        return "増"
    return "大幅増"


def carried_bucket(prev: float | None, cur: float | None) -> str:
    if prev is None or cur is None:
        return "初"
    d = cur - prev
    return "斤量増" if d >= 1.5 else ("斤量減" if d <= -1.5 else "同斤量")


def class_bucket(prev_grade: str | None, cur_grade: str | None) -> str:
    if not prev_grade or not cur_grade or prev_grade not in GRADE_LEVEL or cur_grade not in GRADE_LEVEL:
        return "初"
    d = GRADE_LEVEL[cur_grade] - GRADE_LEVEL[prev_grade]
    return "昇級" if d > 0 else ("降級" if d < 0 else "同クラス")


def jockey_bucket(prev_j: str | None, cur_j: str | None) -> str:
    if not prev_j or not cur_j:
        return "初"
    return "継続" if prev_j == cur_j else "乗替"


def season_of(date: str | None) -> str | None:
    if not date:
        return None
    m = int(date[5:7])
    return {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏"}.get(m, "秋")


def age_group(age: int | None) -> str | None:
    if not age:
        return None
    return str(age) if age <= 5 else "6+"


def field_size_bucket(n: int | None) -> str | None:
    if not n:
        return None
    return "少頭数(〜10)" if n <= 10 else ("中頭数(11-14)" if n <= 14 else "多頭数(15〜)")


def course_exp_bucket(prev_runs: list[dict], course: str | None, surface: str | None) -> str:
    runs = [h for h in prev_runs if h.get("course") == course and h.get("surface") == surface]
    if not runs:
        return "初コース"
    if any(h.get("finish") == 1 for h in runs):
        return "勝利あり"
    if any((h.get("finish") or 99) <= 3 for h in runs):
        return "好走あり"
    return "経験あり"


def days_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days
    except ValueError:
        return None


def time_index(st, h: dict) -> float | None:
    """走破タイムの標準化指数: (基準平均 - タイム) / 標準偏差 × 10 + 50. 高いほど速い."""
    if st is None or not getattr(st, "standards", None) or not h.get("time_sec"):
        return None
    key = (h.get("course"), h.get("surface"), h.get("distance"), going_group(h.get("going")))
    sd = st.standards.get(key)
    if not sd:
        return None
    mean, std = sd
    return 50 + 10 * (mean - h["time_sec"]) / std if std > 0 else None


# ---------------------------------------------------------------- 1頭分の生特徴量

def extract(entry: dict, hist: list[dict], card: dict, st=None) -> dict:
    last = hist[0] if hist else {}
    fx = {
        "interval_days": days_between(last.get("date"), card.get("date")),
        "prev_weight_carried": last.get("weight_carried"),
        "weight_carried": entry.get("weight") or entry.get("weight_carried"),
        "prev_grade": last.get("grade"),
        "prev_jockey": last.get("jockey"),
        "body_weight_diff": entry.get("body_weight_diff"),
        "sex": entry.get("sex"),
        "age": entry.get("age"),
        "n_runs": len(hist),
    }
    fx["interval"] = interval_bucket(fx["interval_days"])
    # 叩き2戦目: 前走が休み明けで今回は間隔が詰まっている
    if len(hist) >= 2 and fx["interval"] in ("中1週", "中2-4週", "中5-8週"):
        pd = days_between(hist[1].get("date"), last.get("date"))
        fx["second_after_rest"] = pd is not None and pd > 63
    else:
        fx["second_after_rest"] = False
    fx["class"] = class_bucket(fx["prev_grade"], card.get("grade"))
    fx["jockey"] = jockey_bucket(fx["prev_jockey"], entry.get("jockey"))
    fx["carried"] = carried_bucket(fx["prev_weight_carried"], fx["weight_carried"])
    fx["body"] = body_bucket(fx["body_weight_diff"])
    fx["course_exp"] = course_exp_bucket(hist, card.get("course"), card.get("surface"))
    fx["season"] = season_of(card.get("date"))
    # 左右回り: 今回と同じ回りでの成績 vs 逆回り
    from . import knowledge as K
    direction = K.courses()["courses"].get(card.get("course") or "", {}).get("direction")
    fx["direction"] = direction
    same, other = [], []
    for h in hist:
        d = K.courses()["courses"].get(h.get("course") or "", {}).get("direction")
        f, n = h.get("finish"), h.get("n_runners") or 16
        if f is None or not d:
            continue
        (same if d == direction else other).append(1 - (f - 1) / max(n - 1, 1))
    fx["dir_same"], fx["dir_other"] = same, other
    # タイム指数（同芝ダの直近5走）
    tis = [time_index(st, h) for h in hist[:5] if h.get("surface") == card.get("surface")]
    tis = [t for t in tis if t is not None]
    fx["ti_best"] = max(tis) if tis else None
    fx["ti_last"] = tis[0] if tis else None
    fx["ti_n"] = len(tis)
    # 勝ち馬とのタイム差（直近3走平均）
    behind = [h["behind"] for h in hist[:3] if h.get("behind") is not None]
    fx["behind_avg"] = sum(behind) / len(behind) if behind else None

    # ---- コース形態適性（直線の長さ・坂・大回り/小回り）: 同じ形態のコースでの成績 vs それ以外
    today = K.course_attrs(card.get("course"), card.get("surface"), card.get("distance"))
    fx["course_attrs"] = today
    ct = {}
    for attr in ("straight_cat", "slope", "turn"):
        same, other = [], []
        for h in hist:
            pf = _perf(h)
            if pf is None or not h.get("course"):
                continue
            a = K.course_attrs(h.get("course"), h.get("surface"), h.get("distance"))
            (same if a[attr] == today[attr] else other).append(pf)
        ct[attr] = (same, other)
    fx["course_type"] = ct
    # ---- 頭数適性: 今回と同じ頭数帯での成績 vs それ以外
    nb = field_size_bucket(card.get("n_runners") or len(card.get("entries") or []) or None)
    same, other = [], []
    for h in hist:
        pf = _perf(h)
        if pf is None:
            continue
        (same if field_size_bucket(h.get("n_runners")) == nb else other).append(pf)
    fx["field_bucket"], fx["field_same"], fx["field_other"] = nb, same, other
    # ---- 休み明け適性: その馬自身の、間隔が9週以上空いた時の成績
    rest_runs, normal_runs = [], []
    for i, h in enumerate(hist[:-1]):
        pf = _perf(h)
        gap = days_between(hist[i + 1].get("date"), h.get("date"))
        if pf is None or gap is None:
            continue
        (rest_runs if gap > 63 else normal_runs).append(pf)
    fx["rest_runs"], fx["normal_runs"] = rest_runs, normal_runs
    # ---- 通過順位からの追い上げ（4角位置 → 着順）と上がり3Fの切れ
    gains, agari = [], []
    for h in hist[:6]:
        pos = [int(x) for x in str(h.get("passing") or "").split("-") if x.isdigit()]
        n = h.get("n_runners") or 16
        if pos and h.get("finish"):
            gains.append((pos[-1] - h["finish"]) / max(n - 1, 1))
        if h.get("last3f_rank"):
            agari.append(1 - (h["last3f_rank"] - 1) / max(n - 1, 1))
    fx["gain_avg"] = sum(gains) / len(gains) if gains else None
    fx["agari_avg"] = sum(agari) / len(agari) if agari else None
    return fx


def _perf(h: dict) -> float | None:
    f, n = h.get("finish"), h.get("n_runners") or 16
    if f is None:
        return None
    return 1 - (f - 1) / max(n - 1, 1)


def _diff(same: list, other: list, min_each: int = 2) -> float | None:
    if len(same) < min_each or len(other) < min_each:
        return None
    return sum(same) / len(same) - sum(other) / len(other)


def field_context(fxs: list[dict]) -> dict:
    tis = [f["ti_best"] for f in fxs if f.get("ti_best") is not None]
    ws = [f["weight_carried"] for f in fxs if f.get("weight_carried")]
    return {
        "ti_mean": statistics.mean(tis) if len(tis) >= 3 else None,
        "ti_sd": (statistics.pstdev(tis) or 1.0) if len(tis) >= 3 else None,
        "w_mean": statistics.mean(ws) if ws else None,
        "n": len(fxs),
    }


# ---------------------------------------------------------------- スコア化

def score(fx: dict, ctx: dict, card: dict, entry: dict, st, P: dict,
          sire: str | None, trainer: str | None, jockey: str | None, style: str | None,
          crosses: list | None) -> tuple[dict, list[str]]:
    comp: dict[str, float] = {}
    ev: list[str] = []
    s = card.get("surface")
    has = st is not None and st.n_races > 0

    def data_or_prior(kind: str, key: tuple, bucket: str, k: float = 100.0, min_n: int = 80) -> float:
        prior = PRIOR[kind].get(bucket, 0.0)
        if has:
            v, n = st.log_ratio([key], k)
            if n >= min_n:
                return v
        return prior

    # ローテーション
    b = fx["interval"]
    if b != "初出走":
        v = data_or_prior("interval", ("interval", s, b), b)
        if trainer and b in ("休み明け", "長期休養明け") and has:
            tv, tn = st.log_ratio([("interval", s, b), ("trainer_rest", trainer, "休み明け")], k=30)
            if tn >= 10:
                v = tv
                c = st.get("trainer_rest", trainer, "休み明け")
                ev.append(f"{trainer}厩舎の休み明け 複勝率{c.top3_rate:.1%}（{c.n}走）")
        if fx["second_after_rest"]:
            add = 0.05
            if has:
                vv, n = st.log_ratio([("second_after_rest", s)], k=100)
                if n >= 80:
                    add = vv
            v += add
        comp["rotation"] = P["w_rotation"] * v
        ev.append(f"ローテ: 前走から{fx['interval_days']}日（{b}{'・叩き2戦目' if fx['second_after_rest'] else ''}） {v:+.2f}")

    # クラス
    if fx["class"] != "初":
        v = data_or_prior("class", ("class_chg", s, fx["class"]), fx["class"])
        comp["class"] = P["w_class"] * v
        if fx["class"] != "同クラス":
            ev.append(f"クラス: {fx['prev_grade']}→{card.get('grade')}（{fx['class']}） {v:+.2f}")

    # 騎手の継続/乗り替わり
    if fx["jockey"] != "初":
        v = data_or_prior("jockey", ("jockey_chg", fx["jockey"]), fx["jockey"])
        if fx["jockey"] == "乗替" and has and jockey and fx["prev_jockey"]:
            # 乗り替わり先と前任の騎手の格差（騎手全体の複勝率の比）
            a, _ = st.log_ratio([("jockey", jockey)], k=50)
            b_, _ = st.log_ratio([("jockey", fx["prev_jockey"])], k=50)
            v += 0.5 * (a - b_)
            ev.append(f"乗り替わり: {fx['prev_jockey']}→{jockey}（騎手力差 {a - b_:+.2f}）")
        comp["jockey_chg"] = P["w_jockey_chg"] * v

    # 斤量（出走馬平均との差 + 前走比）
    w = fx["weight_carried"]
    if w and ctx.get("w_mean"):
        rel = w - ctx["w_mean"]
        dist_factor = min((card.get("distance") or 1600) / 2000, 1.5)   # 距離が長いほど斤量が効く
        v = -0.04 * rel * dist_factor
        v += data_or_prior("carried", ("carried_chg", s, fx["carried"]), fx["carried"])
        comp["weight"] = P["w_weight"] * v
        if abs(rel) >= 1.5 or fx["carried"] != "同斤量":
            ev.append(f"斤量: {w}kg（出走馬平均比{rel:+.1f}kg・前走比{fx['carried']}） {v:+.2f}")

    # 馬体重（当日発表時のみ）
    if fx["body"]:
        v = data_or_prior("body", ("body_chg", fx["body"]), fx["body"])
        comp["body_weight"] = P["w_body"] * v
        ev.append(f"馬体重: 前走比{fx['body_weight_diff']:+d}kg（{fx['body']}） {v:+.2f}")

    # コース実績
    v = data_or_prior("course_exp", ("course_exp", card.get("course"), s, fx["course_exp"]), fx["course_exp"], min_n=50)
    if fx["n_runs"]:
        comp["course_exp"] = P["w_course_exp"] * v
        ev.append(f"コース実績: {card.get('course')}{s}は{fx['course_exp']} {v:+.2f}")

    # 左右回り（馬自身）
    if len(fx["dir_same"]) >= 2 and len(fx["dir_other"]) >= 2:
        a = sum(fx["dir_same"]) / len(fx["dir_same"])
        b_ = sum(fx["dir_other"]) / len(fx["dir_other"])
        v = (a - b_) * 0.6
        comp["direction"] = P["w_direction"] * v
        if abs(a - b_) >= 0.15:
            ev.append(f"{fx['direction']}回り: 同回り平均着順率{a:.2f} vs 逆回り{b_:.2f}（{'得意' if a > b_ else '不得手'}）")

    # コース形態適性（馬自身）
    ca = fx.get("course_attrs") or {}
    parts, tot, cnt = [], 0.0, 0
    lab = {"straight_cat": ("直線", "{}い直線"), "slope": ("坂", "{}"), "turn": ("コーナー", "{}")}
    for attr, (same, other) in (fx.get("course_type") or {}).items():
        d = _diff(same, other)
        if d is None:
            continue
        tot += d
        cnt += 1
        if abs(d) >= 0.12:
            name = {"straight_cat": f"直線{ca.get('straight_cat')}", "slope": ca.get("slope"), "turn": ca.get("turn")}[attr]
            parts.append(f"{name}コースで{'得意' if d > 0 else '不得手'}（{d:+.2f}）")
    if cnt:
        comp["course_type"] = P["w_course_type"] * (tot / cnt) * 0.8
        if parts:
            ev.append("コース形態適性: " + "、".join(parts))
    # コース形態適性（種牡馬の実績）
    if has and sire and ca:
        keys = [("sire_straight", sire, s, ca.get("straight_cat")), ("sire_slope", sire, s, ca.get("slope")),
                ("sire_turn", sire, s, ca.get("turn"))]
        vals = []
        for kk in keys:
            v, n = st.log_ratio([("sire_s", sire, s), kk], k=60)
            base_v, _ = st.log_ratio([("sire_s", sire, s)], k=60)
            if n >= 30:
                vals.append(v - base_v)
                c = st.get(*kk)
                if abs(v - base_v) >= 0.15:
                    ev.append(f"{sire}産駒の{kk[3]}コース（{s}） 複勝率{c.top3_rate:.1%}（{c.n}走）")
        if vals:
            comp["sire_course_type"] = P["w_sire_course_type"] * sum(vals) / len(vals)
    # 頭数適性（馬自身＋種牡馬）
    d = _diff(fx.get("field_same", []), fx.get("field_other", []))
    if d is not None:
        comp["field_fit"] = P["w_field_fit"] * d
        if abs(d) >= 0.12:
            ev.append(f"頭数: {fx['field_bucket']}で{'好成績' if d > 0 else '苦戦'}（{d:+.2f}）")
    if has and sire and fx.get("field_bucket"):
        v, n = st.log_ratio([("sire_s", sire, s), ("sire_field", sire, fx["field_bucket"])], k=60)
        bv, _ = st.log_ratio([("sire_s", sire, s)], k=60)
        if n >= 30:
            comp["sire_field"] = P["w_sire_field"] * (v - bv)
    # 休み明け適性（馬自身＋種牡馬）
    if fx["interval"] in ("休み明け", "長期休養明け"):
        d = _diff(fx.get("rest_runs", []), fx.get("normal_runs", []), min_each=1)
        if d is not None:
            comp["rest_fit"] = P["w_rest_fit"] * d
            ev.append(f"休み明け: この馬の過去の休み明け{len(fx['rest_runs'])}走 平均着順率{sum(fx['rest_runs'])/len(fx['rest_runs']):.2f}（通常時比{d:+.2f}）")
        if has and sire:
            v, n = st.log_ratio([("sire_s", sire, s), ("sire_rest", sire, True)], k=60)
            bv, _ = st.log_ratio([("sire_s", sire, s)], k=60)
            if n >= 30:
                comp["sire_rest"] = P["w_sire_rest"] * (v - bv)
    # 追い上げ（4角→着順）と上がりの切れ
    if fx.get("gain_avg") is not None:
        comp["closing"] = P["w_closing"] * fx["gain_avg"]
        if abs(fx["gain_avg"]) >= 0.1:
            ev.append(f"4角からの追い上げ: 平均{fx['gain_avg']:+.2f}（+は直線で順位を上げる）")
    if fx.get("agari_avg") is not None:
        comp["agari"] = P["w_agari"] * (fx["agari_avg"] - 0.5)

    # 季節×性別・年齢
    if has and fx["season"]:
        keys = []
        if fx["sex"]:
            keys.append(("sex_season", fx["sex"], fx["season"], s))
        if fx["age"]:
            keys.append(("age_season", age_group(fx["age"]), fx["season"], s))
        tot = 0.0
        for kk in keys:
            vv, n = st.log_ratio([kk], k=200)
            if n >= 200:
                tot += vv
        if sire:
            vv, n = st.log_ratio([("sire_season", sire, fx["season"], s)], k=60)
            if n >= 30:
                tot += vv
                c = st.get("sire_season", sire, fx["season"], s)
                if abs(vv) >= 0.1:
                    ev.append(f"季節: {sire}産駒の{fx['season']}の{s} 複勝率{c.top3_rate:.1%}（{c.n}走）")
        if tot:
            comp["season"] = P["w_season"] * tot

    # タイム指数（出走馬の中での相対）
    if fx["ti_best"] is not None and ctx.get("ti_mean") is not None:
        z = (0.6 * fx["ti_best"] + 0.4 * (fx["ti_last"] or fx["ti_best"]) - ctx["ti_mean"]) / ctx["ti_sd"]
        comp["time_index"] = P["w_time"] * max(-2.5, min(2.5, z)) * min(fx["ti_n"], 3) / 3
        ev.append(f"タイム指数: 最高{fx['ti_best']:.1f}・直近{fx['ti_last']:.1f}（出走馬平均{ctx['ti_mean']:.1f}、相対{z:+.2f}σ）")
    if fx["behind_avg"] is not None:
        v = max(-0.4, min(0.3, 0.3 - fx["behind_avg"] * 0.4))
        comp["margin"] = P["w_margin"] * v
        ev.append(f"近3走の勝ち馬とのタイム差 平均{fx['behind_avg']:.1f}秒")

    # インブリード
    if has and crosses is not None:
        v, n = st.log_ratio([("has_cross", s, bool(crosses))], k=200)
        tot = v if n >= 200 else 0.0
        for name in crosses[:3]:
            vv, nn = st.log_ratio([("cross", name, s)], k=80)
            if nn >= 50:
                tot += 0.5 * vv
                c = st.get("cross", name, s)
                ev.append(f"クロス実績: {name}のクロス持ち {s}複勝率{c.top3_rate:.1%}（{c.n}走）")
        if tot:
            comp["inbreed"] = P["w_inbreed"] * tot

    # 新馬（初出走）: 父・調教師の新馬成績
    if fx["n_runs"] == 0 and has:
        keys = [k for k in [("debut", s), ("sire_debut", sire, s), ("trainer_debut", trainer)] if None not in k]
        v, n = st.log_ratio(keys, k=30)
        comp["debut"] = P["w_debut"] * v
        c = st.get("sire_debut", sire, s)
        if c.n >= 10:
            ev.append(f"初出走: {sire}産駒の{s}デビュー戦 勝率{c.win_rate:.1%} 複勝率{c.top3_rate:.1%}（{c.n}頭）")
        c = st.get("trainer_debut", trainer)
        if c.n >= 10:
            ev.append(f"初出走: {trainer}厩舎のデビュー戦 複勝率{c.top3_rate:.1%}（{c.n}頭）")

    # 頭数 × 脚質
    fb = field_size_bucket(ctx.get("n"))
    if has and fb and style:
        v, n = st.log_ratio([("style_field", style, fb)], k=200)
        if n >= 200:
            comp["field_size"] = P["w_field"] * v

    # 妙味（回収率）: 評価には入れず、根拠に表示
    if has and sire:
        c = st.get("sire", sire, s, _band(card))
        if c.n >= 50 and c.roi >= 1.1:
            ev.append(f"妙味: {sire}産駒のこの距離帯は単勝回収率{c.roi:.0%}（人気以上に走る傾向）")
        elif c.n >= 50 and c.roi <= 0.55:
            ev.append(f"注意: {sire}産駒のこの距離帯は単勝回収率{c.roi:.0%}（過剰人気傾向）")
    if has and jockey:
        c = st.get("jockey", jockey)
        if c.n >= 200 and c.roi >= 1.0:
            ev.append(f"妙味: 騎手{jockey}の単勝回収率{c.roi:.0%}")
    return comp, ev


def _band(card):
    from .config import distance_band
    return distance_band(card.get("distance") or 1600)
