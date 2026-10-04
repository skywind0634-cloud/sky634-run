"""チャット・予想ページ向けの「レースごとの注目馬一覧」.

本線（妙味馬の単複）だけでなく、DBが拾った材料を持つ馬を全部並べる（買うかは読む人が選ぶ）:
- 本線: 4〜9番人気で予測勝率が市場の1.3倍以上、かつ人気帯の中で走る条件がプラス（単複の本線。検証 docs/analysis/strategy.md）
- ★: 8番人気以下で血統要素の合計が高い馬
- 専門家: 望田潤・亀谷敬正・白井寿昭などの見解のうち、種牡馬・配合を名指しした具体的なもの
- 走る条件: 人気帯の平均より走る条件が重なる馬（cond_score ≥ 0.4）
- 妙味条件: 過去の複数期間で回収率100%超の条件に当てはまる馬
- 牝系: 母・2代母の一族がこの条件で人気以上に走る（初めての条件なら特に）
- 危険: 1〜6番人気で人気帯の平均より来ない条件が重なる馬
"""
from __future__ import annotations

import re

from .betting import longshot_picks
from .model import BLOOD_COMPS, HorseEval

VALUE_RATIO, VALUE_POP = 1.3, (4, 9)
GENERIC = ("考え方の要約",)   # 系統の型（日本型/米国型など）の一般論。該当馬が多いのでまとめて1行に


def value_picks(evals: list[HorseEval], n: int = 2) -> list[HorseEval]:
    from .betting import value_horses
    return value_horses(evals)[:n]


def _expert(h) -> tuple[list[str], list[str]]:
    spec, gen = [], []
    for e in h.evidence:
        if not e.startswith("専門家見解"):
            continue
        m = re.match(r"専門家見解\[([^（\]]+)（([^）]*)）\]: (.*?)（(プラス|マイナス)／実績検証: ([^・）]*)", e)
        if not m:
            continue
        who, src, text, sign, ver = m.groups()
        line = f"{who}「{text}」（{sign}・{ver}）"
        (gen if any(g in src for g in GENERIC) else spec).append(line)
    return spec, gen


def _pick(h, key):
    return next((e for e in h.evidence if key in e), None)


def _short(s: str | None, n: int = 150) -> str:
    return "" if not s else (s if len(s) <= n else s[:n] + "…")


def horse_line(h: HorseEval) -> str:
    ratio = f"・人気比{h.p_win / h.p_market:.2f}" if h.p_market else ""
    odds = f"{h.odds}倍" if h.odds else "オッズ前"
    pop = f"{h.pop_rank}人気" if h.pop_rank and not h.pop_estimated else (f"想定{h.pop_rank}番手" if h.pop_rank else "")
    return f"{h.number} {h.name}（{pop}・{odds}・父{h.sire or '?'}×母父{h.damsire or '?'}・{h.jockey or ''}{ratio}）"


def reasons(h: HorseEval) -> list[str]:
    out = []
    for key in ("検証済みの傾向", "兄弟姉妹", "牝系: 母", "牝系: 2代母", "牝系: 3代母", "走る条件", "妙味条件", "妙味: ", "回収率の傾向",
                "傾向の波", "騎手×調教師", "近走"):
        e = _pick(h, key)
        if e and e not in out:
            out.append(_short(e))
    spec, _ = _expert(h)
    out += spec
    bad = _pick(h, "来ない条件")
    if bad:
        out.append("注意: " + _short(bad))
    return out[:7]


def race_digest(evals: list[HorseEval]) -> dict:
    """カテゴリ → [(馬, 一言)]."""
    vp = value_picks(evals)
    stars = longshot_picks(evals)
    seen = {h.number for h in vp}
    out = {"本線": [(h, "") for h in vp], "★": [], "専門家": [], "検証済み": [], "走る条件": [], "妙味条件": [], "牝系": [],
           "危険": [], "型の見解": []}
    for h in stars:
        out["★"].append((h, f"血統要素 {h.blood_upside:+.2f}"))
    for h in evals:
        spec, gen = _expert(h)
        if spec:
            out["専門家"].append((h, " / ".join(spec)))
        if gen:
            out["型の見解"].append((h, ""))
        ang = [e.replace("検証済みの傾向: ", "") for e in h.evidence if e.startswith("検証済みの傾向")]
        if ang:
            out["検証済み"].append((h, " / ".join(ang)))
        if h.number not in seen and h.cond_score >= 0.4 and (h.pop_rank or 99) >= 4:
            out["走る条件"].append((h, _short(_pick(h, "走る条件"), 160)))
        if h.number not in seen and (h.value_segments or (h.value_edge or 0) > 0.15):
            out["妙味条件"].append((h, _short(_pick(h, "妙味条件") or _pick(h, "回収率の傾向") or _pick(h, "妙味: "), 160)))
        fam = next((e for e in h.evidence if e.startswith("牝系: ") and "で走る" in e), None)
        if fam and h.number not in seen:
            out["牝系"].append((h, _short(fam, 160)))
        if (h.pop_rank or 99) <= 6 and h.cond_score <= -0.3:
            out["危険"].append((h, _short(_pick(h, "来ない条件"), 160)))
    return out


def sub_picks(evals: list[HorseEval], n: int = 2) -> list[HorseEval]:
    """準本線: 4〜9番人気で人気帯の中で走る条件が強い（0.4以上）馬（本線以外, 危険な人気馬を除く, 人気比の高い順）.
    検証（過去1年）: 単勝回収率 100%前後（前半100%・後半102%）。本線に足すと回収率は117%→105%前後、当たりの幅が広がる."""
    from .betting import is_danger, value_horses
    vs = {h.number for h in value_horses(evals)[:1]}
    c = [h for h in evals if 4 <= (h.pop_rank or 0) <= 9 and not h.pop_estimated and h.cond_score >= 0.4
         and not is_danger(h) and h.number not in vs]
    return sorted(c, key=lambda h: -(h.p_win / h.p_market if h.p_market else 0))[:n]


def ticket_card(card: dict, evals: list[HorseEval]) -> list[str]:
    """そのまま買える買い目カード（本線・準本線・遊び）."""
    from .betting import value_horses, value_plan
    nm = {h.number: h.name for h in evals}
    L = []
    vp = value_plan(evals, len(card.get("entries") or evals))
    if vp:
        L.append("  - 本線（資金の中心）: " + " / ".join(
            f"{t.kind} {'-'.join(map(str, t.horses))}" + (f"（想定{t.est_pay:,.0f}円）" if t.kind == "馬連" else "")
            for t in vp.tickets) + f"（{nm[vp.tickets[0].horses[0]]}）")
    sp = sub_picks(evals)
    if sp:
        L.append("  - 準本線（少額・単勝）: " + "、".join(f"単勝 {h.number}（{h.name}・{h.pop_rank}人気）" for h in sp))
    axis = [h.number for h in value_horses(evals)[:1]] or [h.number for h in sp[:1]]
    d = race_digest(evals)
    pool = []
    for k in ("★", "走る条件", "専門家", "検証済み", "妙味条件"):
        for h, _ in d[k]:
            if h.number not in axis and h.number not in pool and (h.pop_rank or 0) >= 4:
                pool.append(h.number)
    if axis and pool:
        L.append("  - 遊び（ごく少額・検証では負け越し）: ワイド " + "、".join(f"{axis[0]}-{x}" for x in pool[:3])
                 + f"／馬連 " + "、".join(f"{axis[0]}-{x}" for x in pool[:3]))
    return (["**買い目カード**"] + L) if L else []


def text(card: dict, evals: list[HorseEval], title: str) -> str:
    d = race_digest(evals)
    L = [f"### {title}"]
    L += ticket_card(card, evals)
    if d["本線"]:
        from .betting import value_plan
        vp = value_plan(evals, len(card.get("entries") or evals))
        if vp:
            nm = {h.number: h.name for h in evals}
            L.append("**本線の買い目**: " + " / ".join(
                f"{t.kind} {'-'.join(map(str, t.horses))}"
                + (f"（{'・'.join(nm.get(x, '?') for x in t.horses)}・想定{t.est_pay:,.0f}円）" if t.kind == "馬連" else "")
                for t in vp.tickets))
        for h, _ in d["本線"]:
            L.append(f"**本線（単複） {horse_line(h)}**")
            L += [f"  - {r}" for r in reasons(h)]
    else:
        L.append("本線: なし（妙味馬の条件に届く馬がいない）")
    labels = {"★": "★ 血統の穴", "専門家": "専門家の見解に該当", "検証済み": "検証済みの傾向（3期間で回収率100%超）に該当", "走る条件": "人気帯の中で走る条件が重なる",
              "妙味条件": "回収率の高い条件に該当", "牝系": "牝系がこの条件で走る", "危険": "危険な人気馬"}
    for k, lab in labels.items():
        if not d[k]:
            continue
        L.append(f"- {lab}:")
        for h, why in d[k]:
            L.append(f"  - {horse_line(h)}{'：' + why if why else ''}")
    if d["型の見解"]:
        L.append("- 系統の型（日本型/米国型など）の一般的な見解に該当: "
                 + "、".join(f"{h.number}{h.name}" for h, _ in d["型の見解"]))
    return "\n".join(L)
