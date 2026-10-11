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
        # 4〜6番人気は検証で3着内率が同じ人気の他の馬と変わらない（tools/strategy_danger_partners.py）ので1〜3番人気だけ
        if (h.pop_rank or 99) <= 3 and h.cond_score <= -0.3:
            out["危険"].append((h, _short(_pick(h, "来ない条件"), 160)))
    return out


SUB_COND = 0.999  # 走る条件の指標は最大1.00


def sub_picks(evals: list[HorseEval], n: int = 2) -> list[HorseEval]:
    """準本線: 7〜9番人気で人気帯の中で走る条件が満点（1.00）の馬（本線以外, 危険な人気馬を除く, 人気比の高い順）.
    検証（過去1年・実払戻, 前半/後半）: 単勝 101%/172%・複勝 94%/123%・3着内20%（1日約4頭）。
    旧基準（4〜9番人気・0.4以上）は単勝100%/103%・複勝85%/94%で1日22頭と多すぎたため 2026-10-11 に絞った（tools/strategy_sub_picks.py）."""
    from .betting import is_danger, value_horses
    vs = {h.number for h in value_horses(evals)[:1]}
    c = [h for h in evals if 7 <= (h.pop_rank or 0) <= 9 and not h.pop_estimated and h.cond_score >= SUB_COND
         and not is_danger(h) and h.number not in vs]
    return sorted(c, key=lambda h: -(h.p_win / h.p_market if h.p_market else 0))[:n]


def strict_axis(evals: list[HorseEval]) -> list[HorseEval]:
    """妙味条件（厳格: 2024年までの2期間で単勝回収率120%以上が続いた条件）に該当する4番人気以下の馬."""
    return [h for h in evals if h.value_segments and (h.pop_rank or 0) >= 4 and not h.pop_estimated]


def strict_package(evals: list[HorseEval]) -> list[tuple[str, tuple]]:
    """妙味条件(厳格)の馬を軸に: 単勝 ＋ ワイド（1〜5番人気へ）＋ 馬連（1〜3番人気へ）＋ 3連複（軸−1〜2番人気−モデル上位5頭）.
    検証（過去1年・実払戻, docs/analysis/strategy.md）: 1レース約19点、回収率 前半146%・後半140%、的中率26%、的中時の払戻中央値6,580円."""
    fav = {h.pop_rank: h.number for h in evals if h.pop_rank and not h.pop_estimated}
    out = []
    for a in strict_axis(evals):
        out.append(("単勝", (a.number,)))
        out += [("ワイド", tuple(sorted((a.number, fav[p])))) for p in range(1, 6) if p in fav and fav[p] != a.number]
        out += [("馬連", tuple(sorted((a.number, fav[p])))) for p in range(1, 4) if p in fav and fav[p] != a.number]
        # 3連複: 軸 − 1〜2番人気 − モデル上位5頭（軸以外）。前半で選び後半で確認（146%/140%, docs/analysis/strategy.md）
        top5 = [h.number for h in sorted((h for h in evals if h.number != a.number), key=lambda h: -h.p_win)[:5]]
        for b in [fav[p] for p in (1, 2) if p in fav and fav[p] != a.number]:
            out += [("3連複", tuple(sorted((a.number, b, c)))) for c in top5 if c not in (a.number, b)]
    return list(dict.fromkeys(out))


def ticket_card(card: dict, evals: list[HorseEval]) -> list[str]:
    """そのまま買える買い目カード（本線・準本線・遊び）."""
    from .betting import value_horses, value_plan
    nm = {h.number: h.name for h in evals}
    L = []
    sp_pkg = strict_package(evals)
    if sp_pkg:
        L.append("  - ◎妙味条件(厳格)の軸（検証で回収率146%/140%・的中26%・払戻中央6,580円）: "
                 + "、".join(f"{h.number} {h.name}（{h.pop_rank}人気）" for h in strict_axis(evals)) + " → "
                 + " / ".join(f"{k} {'-'.join(map(str, t))}" for k, t in sp_pkg))
    vp = value_plan(evals, len(card.get("entries") or evals))
    if vp:
        L.append("  - 本線（資金の中心）: " + " / ".join(
            f"{t.kind} {'-'.join(map(str, t.horses))}" + (f"（想定{t.est_pay:,.0f}円）" if t.kind == "馬連" else "")
            for t in vp.tickets) + f"（{nm[vp.tickets[0].horses[0]]}）")
    sp = sub_picks(evals)
    if sp:
        L.append("  - 準本線（7〜9番人気・走る条件が満点。検証では単勝101%/172%・複勝94%/123%、少額の単複）: " + "、".join(f"単複 {h.number}（{h.name}・{h.pop_rank}人気）" for h in sp))
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


GRADE_ORDER = {"1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}


def chokketsu_horses(card: dict, evals: list[HorseEval], min_pop: int = 7) -> list[tuple[int, str]]:
    """直結コースで好走歴あり／直結のコース替わり（7番人気以下）. data/knowledge/chokketsu_validated.json
    検証（docs/analysis/chokketsu_list.md）: 3着内率で選び2024年以降も確認した組。人気薄の3着内率が約1.5倍."""
    import json
    from .config import KNOWLEDGE_DIR
    try:
        kb = json.loads((KNOWLEDGE_DIR / "chokketsu_validated.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    T = f"{card.get('course')}{card.get('surface')}{card.get('distance')}"
    ck, cc = set(kb.get("chokketsu", {}).get(T, [])), set(kb.get("course_change", {}).get(T, []))
    if not ck and not cc:
        return []
    pop = {h.number: h.pop_rank for h in evals}
    out = []
    for e in card.get("entries") or []:
        if (pop.get(e.get("number")) or 0) < min_pop:
            continue
        why = []
        rec = e.get("recent") or []
        for r in rec:
            k = f"{r.get('course')}{r.get('surface')}{r.get('distance')}"
            good = (r.get("finish") or 99) <= 3 or (r.get("behind") is not None and r["behind"] <= 0.3)
            if k in ck and good:
                why.append(f"直結コース{k}で好走（{r.get('date')} {r.get('race_name') or ''} {r.get('finish')}着）")
                break
        if rec and f"{rec[0].get('course')}{rec[0].get('surface')}{rec[0].get('distance')}" in cc:
            why.append(f"直結のコース替わり（前走{rec[0].get('course')}{rec[0].get('surface')}{rec[0].get('distance')}→今回{T}）")
        if why:
            out.append((e.get("number"), "、".join(why)))
    return out


def stage_blood_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """開催の進み具合（開幕週〜4週目以降）× 血統で、2021-23年と2024-26年の両方で人気以上/以下だった組（data/knowledge/meet_stage_blood.json,
    tools/meet_stage_blood.py）. 単独の回収率は100%前後なので材料扱い."""
    import json
    from .config import KNOWLEDGE_DIR
    from .knowledge import country_type
    from .trend import meet_stage
    try:
        kb = json.loads((KNOWLEDGE_DIR / "meet_stage_blood.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    stg = meet_stage(card.get("race_id"))
    ent = kb.get(f"{card.get('course')}{card.get('surface')}|{stg}") or []
    if not ent:
        return []
    out = []
    for h in evals:
        vals = {"父系統": h.sire_line, "父タイプ": country_type(h.sire_line), "母父タイプ": country_type(h.damsire_line)}
        why = [f"{e['kind']}={e['value']} {'○' if e['ae'][0] >= 1 else '▼'}（A/E {e['ae'][0]:.2f}/{e['ae'][1]:.2f}・複勝回収{e['fuku'][0]}/{e['fuku'][1]}%）"
               for e in ent if vals.get(e["kind"]) and vals[e["kind"]] == e["value"]]
        if why:
            out.append((h.number, f"{stg}: " + "、".join(why)))
    return out


def close_losers(card: dict) -> list[tuple[int, str]]:
    """前走 4着以下で勝ち馬から0.6秒差以内、今回が同じ芝ダ・同距離で同クラスかクラス落ちの馬."""
    out = []
    g_now = GRADE_ORDER.get(card.get("grade") or "", 0)
    for e in card.get("entries") or []:
        rec = (e.get("recent") or [None])[0]
        if not rec or not rec.get("finish") or rec["finish"] < 4 or rec.get("behind") is None:
            continue
        if rec["behind"] > 0.6 or rec.get("surface") != card.get("surface") or rec.get("distance") != card.get("distance"):
            continue
        g_prev = GRADE_ORDER.get(rec.get("grade") or "", 0)
        if g_prev and g_now and g_now > g_prev:
            continue
        drop = "クラス落ち" if g_prev and g_now and g_now < g_prev else "同クラス"
        out.append((e.get("number"), f"前走 {rec.get('date')} {rec.get('course')}{rec.get('race_name') or ''} {rec['finish']}着・{rec['behind']:.1f}秒差（{drop}）"))
    return out


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
    labels = {"★": "★ 血統の穴", "専門家": "専門家の見解に該当", "検証済み": "検証済みの傾向（3期間で回収率100%超）に該当", "走る条件": "人気帯の中で走る条件が重なる（検証: 7〜9番人気の満点は単勝101%/172%。10番人気以下は複勝60〜70%台で単独では買わない。ヒモ候補）",
              "妙味条件": "回収率の高い条件に該当", "牝系": "牝系がこの条件で走る", "危険": "危険な人気馬（1〜3番人気。検証では3着内率45%前後で同じ人気の他の馬51%より低く、単勝回収66〜75%。消しではなく、軸にしない・頭で買わない）"}
    for k, lab in labels.items():
        if not d[k]:
            continue
        L.append(f"- {lab}:")
        for h, why in d[k]:
            L.append(f"  - {horse_line(h)}{'：' + why if why else ''}")
    ckh = chokketsu_horses(card, evals)
    if ckh:
        L.append("- 直結コース（3着内率で選び2024年以降も確認。7番人気以下の3着内率が約1.5倍。ヒモ候補）:")
        nm = {h.number: h for h in evals}
        for num, txt in ckh:
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    sb = stage_blood_horses(card, evals)
    if sb:
        L.append("- 開催の進み具合×血統（この開催週に2021-23年・2024-26年とも人気以上○/以下▼の血統。単独の回収率は100%前後なので材料）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(sb, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    close = close_losers(card)
    if close:
        L.append("- 前走が勝ち馬から0.6秒差以内の4着以下（今回 同じ芝ダ・同距離で同クラスかクラス落ち。検証: 3着内率25%・クラス落ちは37%と高いが人気に織り込み済みで単独の回収率は70%台。材料として）:")
        nm = {h.number: h for h in evals}
        for num, txt in close:
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    if d["型の見解"]:
        L.append("- 系統の型（日本型/米国型など）の一般的な見解に該当: "
                 + "、".join(f"{h.number}{h.name}" for h, _ in d["型の見解"]))
    return "\n".join(L)
