"""距離・ペース(ラップ)・脚質の分析.

- 脚質判定: 通過順(1角→4角)と頭数から 逃げ/先行/差し/追込 を判定し、テン指数(ESI: 0=最後方, 1=先頭)を出す
- 馬ごとのプロファイル: 脚質分布、テン指数、上がり3F順位、距離別成績(ベスト距離・今回距離の適性・延長/短縮)、ペース別成績
- 展開予想: 出走馬のテン指数から逃げ候補・先行勢の数を数え、コースのペース傾向と合わせてペースを予想し、
  ペース × 脚質 × コースの脚質バイアスから各馬の展開利を計算する
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import knowledge as K

STYLES = ["逃げ", "先行", "差し", "追込"]
# 想定ペース(ハイ/ミドル/スロー) → ラップ分類
PACE_TO_TYPE = {"ハイ": "消耗", "ミドル": "持続", "スロー": "瞬発"}
# ペース × 脚質 の事前相性（log-ratio 相当）。データが貯まると style_pace 実績で上書き
PACE_STYLE_PRIOR = {
    "消耗": {"逃げ": -0.35, "先行": -0.15, "差し": 0.15, "追込": 0.2},
    "持続": {"逃げ": 0.05, "先行": 0.1, "差し": 0.0, "追込": -0.15},
    "瞬発": {"逃げ": 0.3, "先行": 0.2, "差し": -0.05, "追込": -0.3},
    "平均": {"逃げ": 0.1, "先行": 0.1, "差し": 0.0, "追込": -0.15},
}


def parse_passing(passing: str | None) -> list[int]:
    if not passing:
        return []
    return [int(x) for x in re.findall(r"\d+", str(passing))]


def style_from_passing(passing: str | None, n_runners: int | None) -> tuple[str | None, float | None]:
    """通過順 → (脚質, テン指数ESI). ESI は最初の2コーナーの位置から 1=先頭, 0=最後方."""
    pos = parse_passing(passing)
    if not pos:
        return None, None
    n = max(n_runners or 16, 2)
    early = pos[:2]
    esi = 1 - (sum(early) / len(early) - 1) / (n - 1)
    esi = max(0.0, min(1.0, esi))
    if pos[0] == 1 or (len(pos) > 1 and pos[0] <= 2 and pos[1] == 1):
        return "逃げ", esi
    ratio = (pos[0] - 1) / (n - 1)
    if pos[0] <= 4 or ratio <= 0.3:
        return "先行", esi
    if ratio <= 0.65:
        return "差し", esi
    return "追込", esi


def style_from_esi(esi: float) -> str:
    if esi >= 0.88:
        return "逃げ"
    if esi >= 0.62:
        return "先行"
    if esi >= 0.33:
        return "差し"
    return "追込"


def dist_change(prev: int | None, cur: int | None) -> str:
    if not prev or not cur:
        return "初"
    d = cur - prev
    return "延長" if d >= 100 else ("短縮" if d <= -100 else "同")


def perf_of(run: dict) -> float | None:
    f, n = run.get("finish"), run.get("n_runners") or 16
    if f is None:
        return None
    return 1 - (f - 1) / max(n - 1, 1)


@dataclass
class HorseProfile:
    n_runs: int = 0
    style: str | None = None           # 主脚質
    style_dist: Counter = field(default_factory=Counter)
    esi: float | None = None           # 平均テン指数
    esi_source: str = ""               # 'history' / 'card' / 'sire'
    agari_top3_rate: float | None = None   # 上がり3F 3位以内率
    agari_rank_avg: float | None = None
    best_distance: float | None = None     # 好走距離の加重平均
    dist_fit: float = 0.0                  # 今回距離の適性 (-1〜+1)
    dist_note: str | None = None
    dist_change: str = "初"
    pace_perf: dict = field(default_factory=dict)   # {瞬発: (平均perf, 走数)}
    surface_perf: dict = field(default_factory=dict)


def build_profile(history: list[dict], card: dict, entry: dict | None = None,
                  sire: str | None = None, sire_line: str | None = None,
                  sire_style: dict | None = None) -> HorseProfile:
    """近走履歴(新しい順)から馬の脚質・距離・ペース適性プロファイルを作る."""
    hp = HorseProfile()
    s, dist = card.get("surface"), card.get("distance")
    runs = [h for h in history[:10] if h.get("finish") is not None]
    hp.n_runs = len(runs)
    esis = []
    for i, h in enumerate(runs):
        st, esi = style_from_passing(h.get("passing"), h.get("n_runners"))
        if st:
            hp.style_dist[st] += 1
            esis.append((0.85 ** i, esi))
        pf = perf_of(h)
        pt = h.get("pace_type")
        if pt and pf is not None:
            a, n = hp.pace_perf.get(pt, (0.0, 0))
            hp.pace_perf[pt] = ((a * n + pf) / (n + 1), n + 1)
    if esis:
        hp.esi = sum(w * e for w, e in esis) / sum(w for w, _ in esis)
        hp.esi_source = "history"
    elif entry and entry.get("style") in STYLES:
        hp.esi = {"逃げ": 0.95, "先行": 0.75, "差し": 0.45, "追込": 0.2}[entry["style"]]
        hp.esi_source = "card"
    else:
        # 新馬・データなし: 父の産駒の脚質傾向 → 系統の事前値
        if sire_style and sum(sire_style.values()) >= 20:
            tot = sum(sire_style.values())
            m = {"逃げ": 0.95, "先行": 0.75, "差し": 0.45, "追込": 0.2}
            hp.esi = sum(m[k] * v for k, v in sire_style.items()) / tot
            hp.esi_source = "sire"
        else:
            hp.esi = K.line_esi(sire_line)
            hp.esi_source = "sire"
    hp.style = hp.style_dist.most_common(1)[0][0] if hp.style_dist else style_from_esi(hp.esi)

    ranks = [h.get("last3f_rank") for h in runs if h.get("last3f_rank")]
    if ranks:
        hp.agari_top3_rate = sum(1 for r in ranks if r <= 3) / len(ranks)
        hp.agari_rank_avg = sum(ranks) / len(ranks)

    # 距離適性
    same_surface = [h for h in runs if h.get("surface") == s and h.get("distance")]
    good = [(h["distance"], perf_of(h)) for h in same_surface if (perf_of(h) or 0) >= 0.6]
    if good:
        hp.best_distance = sum(d * p for d, p in good) / sum(p for _, p in good)
    if dist and same_surface:
        near = [perf_of(h) for h in same_surface if abs(h["distance"] - dist) <= 200]
        far = [perf_of(h) for h in same_surface if abs(h["distance"] - dist) > 200]
        base = sum(perf_of(h) for h in same_surface) / len(same_surface)
        fit = 0.0
        if near:
            fit += (sum(near) / len(near) - base) * min(len(near), 4) / 4
            fit += (sum(near) / len(near) - 0.5) * 0.5
        elif hp.best_distance:
            # 未経験距離: ベスト距離からの乖離で減点（400m で -0.2 程度）
            fit -= min(abs(dist - hp.best_distance) / 2000, 0.3)
        hp.dist_fit = max(-1.0, min(1.0, fit * 2))
        parts = []
        if hp.best_distance:
            parts.append(f"好走距離の中心 {hp.best_distance:.0f}m")
        if near:
            parts.append(f"今回±200m {len(near)}走 平均着順率{sum(near)/len(near):.2f}")
        else:
            parts.append("今回距離帯は未経験")
        if far:
            parts.append(f"他距離 {len(far)}走 平均{sum(far)/len(far):.2f}")
        hp.dist_note = " / ".join(parts)
    prev = history[0].get("distance") if history else None
    hp.dist_change = dist_change(prev, dist)
    return hp


@dataclass
class PaceForecast:
    pace: str                  # ハイ / ミドル / スロー
    pace_type: str             # 消耗 / 持続 / 瞬発
    nige: list                 # 逃げ候補 (馬番, 馬名)
    senko: list                # 先行勢
    front_ratio: float
    course_tendency: str | None
    note: str


def forecast_pace(profiles: list[tuple[dict, HorseProfile]], card: dict, st=None) -> PaceForecast:
    """出走馬のテン指数から展開(ペース)を予想する."""
    n = len(profiles) or 1
    ranked = sorted(profiles, key=lambda x: -(x[1].esi or 0))
    nige = [(e.get("number"), e["name"]) for e, p in ranked if (p.esi or 0) >= 0.85 or p.style == "逃げ"]
    senko = [(e.get("number"), e["name"]) for e, p in ranked
             if 0.62 <= (p.esi or 0) < 0.85 and (e.get("number"), e["name"]) not in nige]
    front_ratio = (len(nige) + len(senko)) / n
    # コースのペース傾向（実績）
    tendency = None
    if st is not None and getattr(st, "pace_freq", None):
        pf = st.pace_freq.get((card.get("course"), card.get("surface"), card.get("distance")))
        if pf and sum(pf.values()) >= 10:
            tendency = pf.most_common(1)[0][0]
    top_esi = [p.esi or 0 for _, p in ranked[:3]]
    speed_pressure = sum(top_esi) / max(len(top_esi), 1)
    if len(nige) >= 3 or (len(nige) >= 2 and front_ratio >= 0.4) or front_ratio >= 0.5:
        pace = "ハイ"
    elif len(nige) == 0 or (len(nige) == 1 and front_ratio <= 0.25) or speed_pressure < 0.75:
        pace = "スロー"
    else:
        pace = "ミドル"
    pace_type = PACE_TO_TYPE[pace]
    # 1000m直線や短距離は基本的に前傾
    if (card.get("distance") or 9999) <= 1200 and pace == "スロー":
        pace, pace_type = "ミドル", "持続"
    if tendency and pace == "ミドル":
        pace_type = tendency
    note_parts = [f"逃げ候補{len(nige)}頭・先行{len(senko)}頭（前に行く馬の比率 {front_ratio:.0%}）"]
    if len(nige) == 1:
        note_parts.append(f"{nige[0][0]}番{nige[0][1]}の単騎逃げが濃厚")
    elif len(nige) >= 2:
        note_parts.append("ハナ争いで前半が速くなりやすい")
    if tendency:
        note_parts.append(f"このコース距離の過去傾向は『{tendency}戦』が最多")
    return PaceForecast(pace, pace_type, nige, senko, front_ratio, tendency, "。".join(note_parts))


def style_advantage(hp: HorseProfile, fc: PaceForecast, card: dict, st=None) -> tuple[float, str]:
    """展開利: ペース×脚質 + コースの脚質バイアス + 単騎逃げ + 上がり性能."""
    style = hp.style or style_from_esi(hp.esi or 0.5)
    v = 0.0
    notes = []
    # ペース×脚質（実績があれば実績、無ければ事前）
    ps = PACE_STYLE_PRIOR.get(fc.pace_type, {}).get(style, 0.0)
    if st is not None and st.n_races:
        dv, n = st.log_ratio([("style_pace", style, fc.pace_type)], k=100)
        if n >= 50:
            ps = dv
    v += ps
    # コースの脚質バイアス
    cs = card.get("course"), card.get("surface"), card.get("distance")
    cb = K.course_style_prior(card.get("course"), card.get("surface")).get(style, 0.0)
    if st is not None and st.n_races:
        dv, n = st.log_ratio([("style_bias_all", *cs), ("style_bias", *cs, style)], k=60)
        if n >= 30:
            cb = dv
    v += cb
    notes.append(f"脚質{style}：{fc.pace}ペース想定で{ps:+.2f}、コース脚質傾向{cb:+.2f}")
    if style == "逃げ" and len(fc.nige) == 1:
        v += 0.2
        notes.append("単騎逃げ濃厚 +0.20")
    if fc.pace_type == "瞬発" and hp.agari_top3_rate is not None:
        a = (hp.agari_top3_rate - 0.3) * 0.6
        v += a
        notes.append(f"上がり3F上位率{hp.agari_top3_rate:.0%}（瞬発戦で{a:+.2f}）")
    if fc.pace_type == "消耗" and hp.pace_perf.get("消耗"):
        pf, n = hp.pace_perf["消耗"]
        v += (pf - 0.5) * 0.4 * min(n, 3) / 3
    return v, "、".join(notes)


def pace_fit(hp: HorseProfile, pace_type: str) -> tuple[float, str | None]:
    """その馬自身の、想定ペース型のレースでの成績."""
    if pace_type not in hp.pace_perf:
        return 0.0, None
    pf, n = hp.pace_perf[pace_type]
    allp = [v for v, _ in hp.pace_perf.values()]
    base = sum(allp) / len(allp)
    v = (pf - base) * min(n, 4) / 4 + (pf - 0.5) * 0.3
    return v, f"{pace_type}戦 {n}走 平均着順率{pf:.2f}"
