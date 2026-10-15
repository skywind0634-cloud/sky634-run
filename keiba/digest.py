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

from collections import defaultdict

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
        # 4〜6番人気は検証で3着内率が同じ人気の他の馬と変わらない（tools/strategy_danger_partners.py）ので1〜3番人気だけ
        if (h.pop_rank or 99) <= 3 and h.cond_score <= -0.3:
            out["危険"].append((h, _short(_pick(h, "来ない条件"), 160)))
        if h.out_of_form:
            continue  # 直近2〜3走すべて1.5秒以上負けの馬は注目馬に出さない
        if h.number not in seen and h.cond_score >= 0.4 and (h.pop_rank or 99) >= 4:
            out["走る条件"].append((h, _short(_pick(h, "走る条件"), 160)))
        if h.number not in seen and (h.value_segments or (h.value_edge or 0) > 0.15):
            out["妙味条件"].append((h, _short(_pick(h, "妙味条件") or _pick(h, "回収率の傾向") or _pick(h, "妙味: "), 160)))
        fam = next((e for e in h.evidence if e.startswith("牝系: ") and "で走る" in e), None)
        if fam and h.number not in seen:
            out["牝系"].append((h, _short(fam, 160)))
    return out


SUB_COND = 0.999  # 走る条件の指標は最大1.00


def sub_picks(evals: list[HorseEval], n: int = 2) -> list[HorseEval]:
    """準本線: 7〜9番人気で人気帯の中で走る条件が満点（1.00）の馬（本線以外, 危険な人気馬を除く, 人気比の高い順）.
    検証（過去1年・実払戻, 前半/後半）: 単勝 101%/172%・複勝 94%/123%・3着内20%（1日約4頭）。
    旧基準（4〜9番人気・0.4以上）は単勝100%/103%・複勝85%/94%で1日22頭と多すぎたため 2026-10-11 に絞った（tools/strategy_sub_picks.py）."""
    from .betting import is_danger, value_horses
    vs = {h.number for h in value_horses(evals)[:1]}
    c = [h for h in evals if 7 <= (h.pop_rank or 0) <= 9 and not h.pop_estimated and h.cond_score >= SUB_COND
         and not is_danger(h) and h.number not in vs and not h.out_of_form]
    return sorted(c, key=lambda h: -(h.p_win / h.p_market if h.p_market else 0))[:n]


def strict_axis(evals: list[HorseEval]) -> list[HorseEval]:
    """妙味条件（厳格: 2024年までの2期間で単勝回収率120%以上が続いた条件）に該当する4番人気以下の馬."""
    return [h for h in evals if h.value_segments and (h.pop_rank or 0) >= 4 and not h.pop_estimated and not h.out_of_form]


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
        L.append("  - 本線（◎の次・少なめ）: " + " / ".join(
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


def front_count(card: dict) -> int | None:
    """前走で前15%の位置にいた馬の数（出馬表の近走の通過順から）. 7割以上の馬で分からなければ None."""
    n = known = 0
    ents = card.get("entries") or []
    for e in ents:
        rec = (e.get("recent") or [None])[0]
        try:
            pos = int(str(rec.get("passing")).split("-")[0]) / max(rec.get("n_runners") or 16, 1)
        except (AttributeError, ValueError, TypeError):
            continue
        known += 1
        n += pos <= 0.15
    return n if ents and known >= 0.7 * len(ents) else None


def pace_blood_horses(card: dict, evals: list[HorseEval]) -> tuple[str | None, list[tuple[int, str]]]:
    """予想展開（前に行く馬の数）× 系統・種牡馬・国別タイプで、2021-23/2024/2025-26の3期間とも人気以上/以下だった組
    （data/knowledge/line_pace.json, tools/line_pace.py, tools/blood_lap.py）. 単独の回収率は100%前後なので材料."""
    import json
    from .config import KNOWLEDGE_DIR
    nf = front_count(card)
    if nf is None:
        return None, []
    fc = "前少(0-1頭)" if nf <= 1 else "前多(4頭+)" if nf >= 4 else "普通(2-3頭)"
    label = f"前走で前にいた馬{nf}頭 → {'スロー・瞬発寄り' if nf <= 1 else '消耗戦になりやすい（消耗71%）' if nf >= 4 else '平均的'}"
    try:
        kb = json.loads((KNOWLEDGE_DIR / "line_pace.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kb = []
    su = card.get("surface"); d = card.get("distance") or 1600
    bd = "短" if d <= 1400 else "マ" if d <= 1800 else "中長"
    slope = "坂" if card.get("course") in ("中山", "阪神", "中京", "東京") else "平坦"
    out = []
    for h in evals:
        vals = {"父系統": h.sire_line, "種牡馬": h.sire, "母父系統": h.damsire_line}
        why = []
        for e in kb:
            who, name, *cond = e["key"]
            if vals.get(who) == name and cond[0] == su and cond[-1] == fc and cond[1:-1] in ([], [bd], [slope]):
                why.append(f"{who}={name}（{' / '.join(cond)}）{'○' if e['ae'][0] >= 1 else '▼'} A/E {'/'.join(f'{x:.2f}' for x in e['ae'])}")
        if why:
            out.append((h.number, "、".join(why)))
    return label, out


def elim_reason(e: dict) -> str | None:
    """来ない馬（5年・3期間とも3着内5%前後, tools/elim_rules.py）."""
    r = [x for x in (e.get("recent") or [])[:3] if x.get("behind") is not None]
    if len(r) < 2:
        return None
    mb = min(x["behind"] for x in r)
    diffs = " / ".join(f"{x['behind']:+.1f}秒" for x in r)
    if mb >= 1.5:
        return f"近{len(r)}走すべて1.5秒以上負け（{diffs}）"
    if (e.get("age") or 0) >= 7 and mb >= 1.0:
        return f"7歳以上で近{len(r)}走すべて1.0秒以上負け（{diffs}）"
    return None


def PED5_FLAGS() -> dict:
    """5代血統表からの祖先フラグ（data/knowledge/ped5_flags.json, tools/ped5_flags.py）."""
    global _PED5
    try:
        return _PED5
    except NameError:
        pass
    import json
    from .config import KNOWLEDGE_DIR
    try:
        _PED5 = json.loads((KNOWLEDGE_DIR / "ped5_flags.json").read_text(encoding="utf-8"))["flags"]
    except (OSError, ValueError, KeyError):
        _PED5 = {}
    return _PED5


SS_LINES_ALL = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
                "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}


def book_condition_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """亀谷『血統の教科書』の切り口（小系統・大系統 × レース条件①〜⑫）で3期間とも人気以上○/以下▼だった組に該当する馬
    （data/knowledge/book_conditions.json, tools/book_conditions.py）."""
    import datetime as _dt
    import json
    from .config import KNOWLEDGE_DIR
    from .knowledge import country_type
    try:
        kb = json.loads((KNOWLEDGE_DIR / "book_conditions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    bm = kb.get("book_map", {}); su = card.get("surface"); co = card.get("course"); d = card.get("distance") or 1600
    if su == "芝":
        bd = "芝〜1400" if d <= 1400 else "芝1600-1800" if d <= 1800 else "芝2000-2400" if d <= 2400 else "芝2500〜"
    else:
        bd = "ダ〜1400" if d <= 1400 else "ダ1600-1900" if d <= 1900 else "ダ2000〜"
    going = card.get("going") or "良"
    base = {("①芝ダ", su), ("②③コース", f"{co}{su}"), ("④距離", bd),
            ("⑤直線", f"{su}・直線{'長' if co in kb.get('long_straight', []) else '短'}"),
            ("⑥坂", f"{su}・{'坂' if co in kb.get('slope', []) else '平坦'}"), ("馬場", f"{su}・{'良' if going.startswith('良') else '道悪'}")}
    wcs = [e.get("weight") for e in card.get("entries") or [] if e.get("weight")]
    if wcs and max(wcs) - min(wcs) >= 4:
        base.add(("⑪ハンデ", f"{su}・斤量差4kg以上"))
    ent = {e.get("number"): e for e in card.get("entries") or []}
    out = []
    for h in evals:
        e = ent.get(h.number, {})
        cs = set(base)
        rec = e.get("recent") or []
        if rec:
            p = rec[0]
            dd = d - (p.get("distance") or d)
            if abs(dd) >= 200:
                cs.add(("⑦距離変更", f"{su}・{'延長' if dd > 0 else '短縮'}"))
            if p.get("surface") and p["surface"] != su:
                cs.add(("⑧芝ダ替わり", f"{p['surface']}→{su}"))
            try:
                days = (_dt.date.fromisoformat(card["date"]) - _dt.date.fromisoformat(p["date"])).days
                if days >= 70:
                    cs.add(("⑩間隔", f"{su}・休み明け(10週+)"))
                elif len(rec) >= 2 and (_dt.date.fromisoformat(p["date"]) - _dt.date.fromisoformat(rec[1]["date"])).days >= 70:
                    cs.add(("⑩間隔", f"{su}・叩き2戦目"))
            except (KeyError, TypeError, ValueError):
                pass
        if e.get("age"):
            cs.add(("⑨年齢", f"{su}・{e['age']}歳" if e["age"] <= 5 else f"{su}・6歳以上"))
        if e.get("sex"):
            cs.add(("⑫性別", f"{su}・{'牝' if str(e['sex']).startswith('牝') else '牡セ'}"))
        mine = {}
        for who, v in (("父", h.sire_line), ("母父", h.damsire_line)):
            if v in bm:
                mine[(who, bm[v][0])] = 1; mine[(who, bm[v][1])] = 1
        why = [f"{r['who']}{r['line']}×{r['value']} {'○' if min(r['ae']) >= 1.1 else '▼'}（A/E {'/'.join(f'{x:.2f}' for x in r['ae'])}）"
               for r in kb.get("rows", []) if (r["who"], r["line"]) in mine and (r["cond"], r["value"]) in cs]
        # サンデー系3タイプ（p56, tools/sunday_tpd.py）: Dサンデーはダートで人気ほど来ない（0.92/0.87/0.89）、Tサンデーは芝2200m以上で人気以上（1.05/1.05/1.04）
        # 本 p63-80 の検証（tools/book_ch3.py）
        if su == "ダ" and rec and all(x.get("surface") == "芝" for x in rec if x.get("surface")):
            why.append("初ダート（前走まで芝のみ）▼（A/E 父・母父のタイプを問わず0.59〜0.89・複勝回収37〜62%）")
        elif su == "ダ" and any(x.get("surface") == "芝" for x in rec[:3]):
            why.append("ダートで近3走に芝出走あり ▽（A/E 良0.92/0.96/0.91・重不良0.90/0.92/0.91。本の『ダート道悪は芝血統』は確認できず）")
        # 本 p91-97 の検証（tools/book_ch3c.py）
        prv = rec[0] if rec else None
        stt = country_type(h.sire_line)
        if prv and prv.get("surface") == "芝" and su == "ダ" and stt == "米国型" and h.damsire_line in SS_LINES_ALL:
            why.append("芝→ダ×父米国型×母父サンデー系 ▼（A/E 0.80/0.77/0.74）")
        if prv and prv.get("surface") == "ダ" and su == "芝" and stt in ("日本型", "米国型"):
            why.append(f"ダ→芝×父{stt} ▼（A/E {'0.73/0.85/0.75' if stt == '日本型' else '0.77/0.60/0.82'}。欧州型は0.87/1.03/1.04）")
        if prv and prv.get("surface") == "ダ" and su == "ダ" and prv.get("distance") and d <= prv["distance"] - 200 and stt == "米国型" and (h.number or 0) >= 10:
            why.append("ダート距離短縮×父米国型×2桁馬番 ○（A/E 1.11/1.11/1.02・複勝回収93/97/88%）")
        # 本 p98-105 の検証（tools/book_ch3d.py）
        if su == "芝" and d >= 2000 and e.get("age") == 3 and str(card.get("date", ""))[5:7] <= "06" and h.sire_line == "ディープインパクト系":
            why.append("3歳前半×父ディープ系×芝2000m以上 ◎（A/E 1.20/1.13/1.16）")
        if su == "ダ" and e.get("age") == 3 and str(card.get("date", ""))[5:7] <= "06" and stt == "日本型":
            why.append("ダート3歳前半×父日本型 ▽（A/E 0.87/0.88/0.93）")
        try:
            gap = (_dt.date.fromisoformat(card["date"]) - _dt.date.fromisoformat(prv["date"])).days if prv else 0
        except (KeyError, TypeError, ValueError):
            gap = 0
        if su == "ダ" and e.get("age") == 3 and str(e.get("sex") or "").startswith("牝") and h.sire_line in ("デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"):
            why.append("ダート3歳×父ダンチヒ系×牝馬 ×（A/E 0.87/0.87/0.80）")
        # 第4章 ナスルーラ系（tools/book_ch4_nasrullah.py）
        pf = set(PED5_FLAGS().get(e.get("horse_id") or "", [])) | ({"サクラバクシンオー"} if "サクラバクシンオー" in (e.get("pedigree") or {}).values() else set())
        if su == "芝" and d <= 1200 and not going.startswith("良") and "サクラバクシンオー" in pf:
            why.append("芝1200以下の道悪×5代にサクラバクシンオー ○（A/E 1.21/1.07/1.11）")
        if su == "芝" and not going.startswith("良") and h.sire_line == "プリンスリーギフト系":
            why.append("芝の道悪×父プリンスリーギフト系 ○（A/E 1.07/1.05/1.16。良は0.84〜1.02）")
        # 第4章 ミスタープロスペクター系（tools/book_ch4_mrp.py）
        if su == "芝" and h.sire == "ロードカナロア":
            if card.get("grade") in ("OP", "L", "G3", "G2", "G1"):
                why.append("芝OP以上×父ロードカナロア ○（A/E 1.10/1.14/1.22）")
            if prv and prv.get("distance") and d <= prv["distance"] - 200:
                why.append("芝の距離短縮×父ロードカナロア ○（A/E 1.12/1.11/1.27・複勝回収90/74/101%）")
        if su == "芝" and d <= 1400 and h.sire == "ルーラーシップ" and (h.pop_rank or 0) >= 4:
            why.append("芝1400以下×父ルーラーシップ×4番人気以下 ◎（A/E 1.37/1.25/1.15。本の『芝1400以下の人気馬は信用できない』の裏返しで人気薄が走る）")
        if su == "芝" and h.sire == "リオンディーズ" and prv and prv.get("distance") and d >= prv["distance"] + 200:
            why.append("芝の距離延長×父リオンディーズ ▼（A/E 0.66/0.81/0.81）")
        if su == "ダ" and h.sire == "ラブリーデイ":
            why.append("ダート×父ラブリーデイ ▼（A/E 0.84/0.70/0.74）")
        if su == "ダ" and h.sire == "ルーラーシップ" and gap >= 63:
            why.append("ダート休み明け×父ルーラーシップ ▼（A/E 0.90/0.79/0.65）")
        if su == "ダ" and h.sire == "ドゥラメンテ" and str(e.get("sex") or "").startswith("牝"):
            why.append("ダート×父ドゥラメンテ×牝馬 ▼（A/E 0.87/0.82/0.87）")
        # 第4章 サンデー系（tools/book_ch4_sunday.py）
        if su == "芝" and h.sire_line == "ディープインパクト系" and h.damsire_line in ("デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"):
            why.append("芝×父ディープ系×母父ダンチヒ系 ○（A/E 1.17/1.10/1.10。本のニックスどおり）")
        if su == "芝" and h.sire_line == "ディープインパクト系" and h.damsire_line in ("キングカメハメハ系", "キングマンボ系", "マキャヴェリアン系"):
            why.append("芝×父ディープ系×母父欧州型ミスプロ系 ○（A/E 1.13/1.11/1.08。本のニックスどおり）")
        if su == "芝" and h.sire_line == "ステイゴールド系" and any(x.sire_line == "ディープインパクト系" and (x.pop_rank or 99) <= 3 for x in evals):
            why.append("芝×父ステイゴールド系（1-3番人気にディープ系あり）: ディープ系の人気馬が崩れたレースでは A/E 1.23/1.23/1.20。人気のディープ系を疑うときの相手")
        # 第4章 サンデー系その他（tools/book_ch4_sunday2.py）
        if su == "芝" and not going.startswith("良") and h.sire == "ダイワメジャー":
            why.append("芝の道悪×父ダイワメジャー ◎（A/E 1.14/1.43/1.44。本の『タフな馬場で有利』のとおり）")
        if su == "ダ" and h.sire_line == "ゴールドアリュール系" and "クラス" in (card.get("name") or "") and card.get("grade") not in ("OP", "L", "G3", "G2", "G1"):
            why.append("ダート平場×父ゴールドアリュール系 ×（A/E 0.86/0.89/0.89。本の『平場より特別戦』のとおり）")
        if su == "ダ" and h.sire_line == "ゴールドアリュール系" and (co, d) in (("東京", 1600), ("京都", 1400), ("中山", 1200)):
            why.append("東京ダ1600・京都ダ1400・中山ダ1200×父ゴールドアリュール系 ×（A/E 0.82/0.56/0.69。本の得意コースは人気先行）")
        if su == "芝" and h.sire_line == "ハーツクライ系" and h.pop_rank == 1:
            why.append("芝×父ハーツクライ系×1番人気 ▽（A/E 0.95/0.95/0.93）")
        # 第4章 ヴァイスリージェント系（tools/book_ch4_nd1.py）
        if su == "ダ" and going.startswith("良") and h.sire_line == "デピュティミニスター系":
            why.append("ダートの良×父ヴァイスリージェント系 ×（A/E 0.84/0.76/0.89。本の『軽い馬場向き』どおり良のダートは割引）")
        if su == "ダ" and str(e.get("sex") or "").startswith("セ") and h.damsire_line == "デピュティミニスター系":
            why.append("ダート×母父ヴァイスリージェント系×セン馬 ○（A/E 1.09/1.33/1.09）")
        # 第4章 ストームバード系・サドラーズウェルズ系（tools/book_ch4_storm.py）
        if h.sire == "ディスクリートキャット" and (e.get("age") or 0) >= 4:
            why.append(f"{su}×父ディスクリートキャット×4歳以上 ○（A/E ダ1.11/1.33/1.14・芝1.19/1.08/1.33）")
        if su == "ダ" and not going.startswith("良") and h.sire_line in ("サドラーズウェルズ系", "ガリレオ系"):
            why.append("ダートの道悪×父サドラーズウェルズ系 ×（A/E 0.72/0.71/0.90）")
        # 第4章 ダンチヒ系（tools/book_ch4_danzig.py）
        if su == "ダ" and co in ("東京", "中京") and h.sire_line in ("デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系") and h.sire != "ハービンジャー":
            why.append("直線の長いダート×父ダンチヒ系 ▽（A/E 0.92/0.74/0.91）")
        # 第4章 ヌレイエフ系（tools/book_ch4_nd2.py）
        if su == "芝" and h.damsire in ("ピヴォタル", "Pivotal", "ファスリエフ", "ストラヴィンスキー", "スピニングワールド", "ブラックホーク"):
            why.append("芝×母父ヌレイエフ系 ▽（A/E 0.93/0.78/0.68）")
        # 第4章 ロベルト系（tools/book_ch4_roberto.py）
        rob = ("スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系")
        is_op = card.get("grade") in ("OP", "L", "G3", "G2", "G1")
        if is_op and (h.pop_rank or 0) >= 6 and su == "ダ" and h.sire_line in rob:
            why.append("ダートOP以上×父ロベルト系×6番人気以下 ◎（A/E 1.36/1.52/1.26。本の『大一番で一発』のとおり）")
        if is_op and (h.pop_rank or 0) >= 6 and su == "芝" and h.damsire_line in rob:
            why.append("芝OP以上×母父ロベルト系×6番人気以下 ○（A/E 1.09/1.43/1.08）")
        if su == "芝" and not going.startswith("良") and h.sire == "エピファネイア":
            why.append("芝の道悪×父エピファネイア ▽（A/E 0.76/0.93/0.73。本の『タフな馬場向き』と逆）")
        if su == "芝" and not going.startswith("良") and h.sire_line in rob and h.sire != "エピファネイア":
            why.append("芝の道悪×父ロベルト系 ▽（A/E 0.88/0.88/0.95）")
        if su == "芝" and h.sire == "スクリーンヒーロー" and card.get("grade") in ("1勝", "2勝"):
            why.append("1-2勝クラスの芝×父スクリーンヒーロー ◎（A/E 1.13/1.19/1.19）")
        if su == "芝" and h.damsire == "ロージズインメイ":
            why.append("芝×母父ロージズインメイ ◎（A/E 1.12/1.12/1.26、芝1600-1800は1.44/1.19/1.35・複勝回収140/83/127%）")
        if su == "芝" and d <= 1400 and h.damsire == "タイキシャトル":
            why.append("芝1400以下×母父タイキシャトル ×（A/E 0.85/0.87/0.70）")
        if su == "ダ" and d <= 1400 and h.sire == "ロージズインメイ":
            why.append("ダ1400以下×父ロージズインメイ ×（A/E 0.84/0.56/0.74）")
        if su == "ダ" and h.sire in ("エンパイアメーカー", "バトルプラン", "アメリカンファラオ", "パイオニアオブザナイル"):
            why.append("ダート×父エンパイアメーカー系 ○（A/E 1桁馬番1.05/1.25/1.22、5番人気以内1.13/1.07/1.13。本の『人気薄・外枠』は確認できず）")
        if su == "芝" and h.sire_line == "ファピアノ系" and co not in ("京都", "新潟", "札幌", "函館", "小倉", "福島"):
            why.append("芝×父ファピアノ系 ▽（A/E 良0.66/0.89/0.90）")
        if su == "芝" and co in ("京都", "新潟", "札幌", "函館", "小倉", "福島") and h.sire_line in ("フォーティナイナー系", "ファピアノ系"):
            why.append(f"平坦な芝×父{h.sire_line} ▼（A/E フォーティナイナー系0.82〜0.90・ファピアノ系0.59〜0.90）")
        # 第4章 ボールドルーラー系（tools/book_ch4_boldruler.py）
        if su == "ダ" and h.sire == "シニスターミニスター":
            why.append("ダート×父シニスターミニスター ○（A/E 1.11/1.15/1.06、6番人気以下は◎1.12/1.20/1.24・複勝回収76/76/119%）")
        elif su == "ダ" and h.sire_line == "エーピーインディ系":
            why.append("ダート×父エーピーインディ系 ○（A/E 1.07/1.11/1.06、直線の短いダートは1.08/1.12/1.08。父サンデー系は0.92〜0.99）")
        # 双馬 第1章「前走より楽なら好走」の検証（tools/souma_rotation.py）: 前走・今回の2走のローテ並び×前走着順×人気
        same = [x for x in rec if x.get("surface") == su and x.get("distance")]
        if len(same) >= 2 and same[0] is rec[0]:
            def _rot(a, b):
                dd = a - b
                return "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"
            r1, r0 = _rot(d, same[0]["distance"]), _rot(same[0]["distance"], same[1]["distance"])
            f0 = same[0].get("finish") or 99
            pr_ = h.pop_rank or 0
            if su == "ダ" and r0 == "延長" and f0 >= 6 and r1 == "短縮":
                why.append("前走ダ延長で凡走→今回短縮 ○（双馬『延長で凡走→楽になって巻き返す』, A/E 全体1.02/1.16/1.17・7番人気以下1.12/1.31/1.31）")
            if r0 == "同距離" and 4 <= f0 <= 5 and pr_ >= 7 and (su == "ダ" and r1 == "同距離" or su == "芝" and r1 == "延長"):
                why.append(f"前走同距離で4-5着→今回{r1}×7番人気以下 ◎（A/E {'1.16/1.40/1.29' if su == 'ダ' else '1.41/1.32/1.25'}。惜敗の人気薄）")
            if su == "芝" and r0 == "同距離" and 4 <= f0 <= 5 and r1 == "短縮" and 4 <= pr_ <= 6:
                why.append("芝・前走同距離で4-5着→今回短縮×4-6番人気 ◎（A/E 1.11/1.23/1.24）")
            if su == "芝" and r0 == "短縮" and 4 <= f0 <= 5 and r1 in ("同距離", "延長") and pr_ >= 7:
                why.append("芝・前走短縮で4-5着→今回同距離/延長×7番人気以下 ◎（A/E 1.10〜1.72）")
            if su == "芝" and r0 == "短縮" and f0 >= 6 and r1 == "延長" and pr_ >= 7:
                why.append("芝・前走短縮で凡走→今回延長×7番人気以下 ×（A/E 0.88/0.57/0.85。短縮でも走れず今回は苦しい延長）")
        # 双馬『1頭の種牡馬のクセ』（tools/souma_ch0.py）
        if su == "ダ" and "タイキシャトル" in pf | ({"タイキシャトル"} if "タイキシャトル" in (h.sire, h.damsire) else set()):
            g = e.get("gate") or 0
            if 1 <= g <= 3:
                why.append("ダート内枠（1-3枠）×タイキシャトルの血 ×（A/E 0.84/0.53/0.77。双馬『砂をかぶるのが苦手』のとおり）")
            elif g >= 4:
                why.append("ダート中外枠（4-8枠）×タイキシャトルの血 ○（A/E 中枠1.18/1.25/1.16・外枠1.18/1.36/0.98）")
        if su == "芝" and "タイキシャトル" in pf | ({"タイキシャトル"} if "タイキシャトル" in (h.sire, h.damsire) else set()) and prv and prv.get("distance") and d >= prv["distance"] + 200:
            why.append("芝の距離延長×タイキシャトルの血 ▽（A/E 0.68/0.91/0.94。双馬『延長が苦手』のとおり）")
        if prv and prv.get("surface") == "ダ" and su == "芝" and (h.sire_line in ("デインヒル系", "プリンスリーギフト系") or h.damsire_line in ("デインヒル系", "プリンスリーギフト系")
                or h.damsire in ("アンバーシャダイ", "タイキシャトル", "タマモクロス", "ダンシングブレーヴ", "カーリアン", "Caerleon")
                or pf & {"カロ系"}):
            why.append("ダ→芝×双馬『芝替わり得意』の血 ×（A/E 0.74/0.69/0.79。得意とされる血統でも芝替わりは割引）")
        if prv and prv.get("surface") == "芝" and su == "ダ" and h.sire_line in ("フォーティナイナー系",):
            why.append("芝→ダ×父フォーティナイナー系 ×（A/E 0.37/0.32/0.73。双馬『ダート替わり得意』と逆）")
        if prv and prv.get("distance") and prv.get("surface") == su:
            ddd = d - prv["distance"]
            if su == "ダ" and ddd >= 200 and h.sire == "パイロ":
                why.append("ダートの距離延長×父パイロ ◎（A/E 1.14/1.87/1.30。双馬『短縮得意』と逆）")
            if su == "ダ" and ddd <= -200 and h.sire == "ジャスタウェイ":
                why.append("ダートの距離短縮×父ジャスタウェイ ◎（A/E 1.22/1.19/1.87）")
            if su == "芝" and ddd <= -200 and h.sire == "ハーツクライ":
                why.append("芝の距離短縮×父ハーツクライ ○（A/E 1.04/1.08/1.31。双馬『短縮苦手』と逆）")
            if su == "芝" and ddd >= 200 and "Chief's Crown" in pf:
                why.append("芝の距離延長×5代にChief's Crown ○（A/E 1.23/1.07/1.22）")
        if su == "芝" and co == "新潟" and d == 1000 and "インリアリティ" in pf:
            why.append("新潟芝1000（直線）×5代にインリアリティ ○（2021-26: 単勝回収111%・なしは53%、3着内A/E 2024-26年 1.04/1.05/1.53。亀谷説。件数少なめ）")
        # OP以上（OP・L・重賞）で強まる傾向（tools/open_class_check.py）
        if card.get("grade") in ("OP", "L", "G3", "G2", "G1"):
            if prv and prv.get("distance") and d <= prv["distance"] - 200 and stt == "米国型":
                why.append("OP以上×距離短縮×父米国型 ○（ダA/E 1.09/1.20/1.25・複勝回収93/97/89%、芝1.06/1.11/1.10）")
            if prv and prv.get("surface") == "芝" and su == "ダ":
                why.append("OP以上×芝→ダ ×（A/E 0.58/0.57/0.87・複勝回収27〜53%）")
            if su == "ダ" and stt == "日本型" and co not in ("東京", "中京"):
                why.append("OP以上×父日本型×ダート直線短 ▽（A/E 0.86/0.91/0.87）")
        if su == "ダ" and gap >= 63 and stt == "日本型":
            why.append("ダート休み明け（中9週以上）×父日本型 ▽（A/E 0.93/0.90/0.95）")
        if su == "芝" and d >= 2500 and country_type(h.damsire_line) == "欧州型":
            why.append("芝2500m以上×母父欧州型 ○（A/E 1.10/1.02/1.08）")
        if su == "芝" and co in ("札幌", "函館") and h.sire_line in ("ステイゴールド系", "ハーツクライ系", "マンハッタンカフェ系"):
            why.append("洋芝×父ステゴ/ハーツ/マンカフェ系 ○（A/E 1.07/1.15/1.13・複勝回収97/91/90%）")
        if su == "ダ" and (e.get("age") or 0) >= 5 and h.sire_line in ("スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"):
            why.append("父ロベルト系×ダート5歳以上 ▽（A/E 0.91/0.89/0.85）")
        if su == "ダ" and h.sire_line in ("ゴールドアリュール系", "ネオユニヴァース系"):
            why.append("Dサンデー×ダート ▼（A/E 0.92/0.87/0.89・人気になりすぎ）")
        if su == "芝" and d >= 2200 and h.sire_line in ("ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "スペシャルウィーク系"):
            why.append("Tサンデー×芝2200m以上 ○（A/E 1.05/1.05/1.04, 差は小さい）")
        if why:
            out.append((h.number, "、".join(why)))
    return out


def mainstream_gap(card: dict, evals: list[HorseEval]) -> tuple[str | None, list[HorseEval]]:
    """主流／反主流のずれ（亀谷『血統の教科書』, tools/mainstream_gap.py）.
    芝の道悪で1〜3番人気がすべて日本型のとき、父が欧州型・米国型の4〜9番人気は3着内A/E 1.14/1.12/1.18・複勝回収102/97/99%（2021-23/2024/2025-26）。
    返り値: (馬場の主流度の説明, 狙いの馬)."""
    from .knowledge import country_type
    if card.get("surface") != "芝":
        return None, []
    co, d, going = card.get("course"), card.get("distance") or 0, card.get("going") or "良"
    good = going.startswith("良")
    if co in ("東京", "中山", "京都", "阪神") and d in (1600, 2000, 2400) and good:
        lab = "主流馬場（中央4場の芝1600/2000/2400・良）: 日本型（サンデー系など）が強い舞台"
    elif not good:
        lab = f"反主流馬場（道悪: {going}）: 欧州型・米国型が浮上しやすい"
    elif co in ("札幌", "函館"):
        lab = "反主流寄り（洋芝）"
    elif co in ("福島", "小倉") or d <= 1200:
        lab = "反主流寄り（小回り平坦・芝1200以下）"
    else:
        lab = "準主流（良・非根幹距離など）"
    top = [h for h in evals if h.pop_rank and h.pop_rank <= 3 and not h.pop_estimated]
    if len(top) < 3 or good:
        return lab, []
    if all(country_type(h.sire_line) == "日本型" for h in top):
        picks = [h for h in evals if 4 <= (h.pop_rank or 0) <= 9 and country_type(h.sire_line) in ("欧州型", "米国型") and not h.out_of_form]
        return lab + " → 1〜3番人気がすべて日本型（主流）＝ずれのあるレース", picks
    return lab, []


def sire_recent_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """最新の種牡馬傾向（2024年・2025-26年の両方で人気以上○/以下▼, data/knowledge/sire_profiles_modern.json, tools/sire_profiles_modern.py）と、
    産駒実績からの実際のタイプ（本の分類が古い・系統名と働きがずれる種牡馬の補正）."""
    import json
    from .config import KNOWLEDGE_DIR
    try:
        kb = json.loads((KNOWLEDGE_DIR / "sire_profiles_modern.json").read_text(encoding="utf-8"))["sires"]
    except (OSError, ValueError, KeyError):
        return []
    su = card.get("surface"); co = card.get("course"); d = card.get("distance") or 1600
    going = card.get("going") or "良"
    bd = (("芝〜1400" if d <= 1400 else "芝1600-1800" if d <= 1800 else "芝2000〜") if su == "芝" else ("ダ〜1400" if d <= 1400 else "ダ1600〜"))
    base = {su, bd, f"{su}・{'良' if going.startswith('良') else '道悪'}", f"{su}・{'坂' if co in ('中山', '阪神', '中京', '東京') else '平坦'}",
            f"{su}・直線{'長' if co in ('東京', '新潟', '阪神', '京都', '中京') else '短'}"}
    ent = {e.get("number"): e for e in card.get("entries") or []}
    out = []
    for h in evals:
        p = kb.get(h.sire or "")
        if not p:
            continue
        e = ent.get(h.number, {})
        cs = set(base)
        if e.get("age"):
            cs.add(f"{su}・{'2-3歳' if e['age'] <= 3 else '4歳以上'}")
        rec = (e.get("recent") or [None])[0]
        if rec and rec.get("distance") and abs(d - rec["distance"]) >= 200:
            cs.add(f"{su}・{'延長' if d > rec['distance'] else '短縮'}")
        why = [f"{'○' if r['ae'][0] >= 1 else '▼'}{r['cond']}（{r['ae'][0]:.2f}/{r['ae'][1]:.2f}）" for r in p.get("recent", []) if r["cond"] in cs]
        # 世代の上昇/下降（重賞馬が出て繁殖牝馬の質が変わる等。3歳時の成績で世代を比較, tools/sire_profiles_modern.py）
        if p.get("crop_trend") and e.get("age"):
            crop = str(int(str(card.get("date", "2026"))[:4]) - e["age"])
            ys = sorted(p.get("crops", {}))
            if ys and crop >= ys[-1]:
                why.append(f"{'○' if p['crop_trend'].startswith('上昇') else '▼'}世代が{p['crop_trend'][:2]}（3歳時A/E " + " ".join(y[2:] + "年生" + format(p['crops'][y][1], '.2f') for y in ys[-3:]) + "）")
        typ = p.get("work_type") or ""
        tag = f"{h.sire}: 実績タイプ {typ}" + (f"・{p['tpd']}" if p.get("tpd") else "") + f"・芝の平均勝ち距離{p.get('avg_win_turf') or '-'}m"
        if why:
            out.append((h.number, tag + " / 最新の傾向 " + "、".join(why)))
    return out


def course_blood_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """コース別・コース×展開別の血統傾向（2021-23と2024-26の両方で人気以上○/以下▼・大きな件数のものだけ, data/knowledge/course_blood.json,
    tools/course_blood.py）. 2021-24年で選んだものが2025-26年も同じ向きだったのは65%（上積み+4.5%）なので材料扱い."""
    import json
    from .config import KNOWLEDGE_DIR
    try:
        kb = json.loads((KNOWLEDGE_DIR / "course_blood.json").read_text(encoding="utf-8"))["rows"]
    except (OSError, ValueError, KeyError):
        return []
    course = f"{card.get('course')}{card.get('surface')}{card.get('distance')}"
    nf = front_count(card)
    keys = {course} | ({f"{course}|{'前少' if nf <= 1 else '前多' if nf >= 4 else '普通'}"} if nf is not None else set())
    rows = [r for r in kb if r["key"] in keys]
    if not rows:
        return []
    ent = {e.get("number"): e for e in card.get("entries") or []}
    out = []
    for h in evals:
        flags = set(PED5_FLAGS().get(ent.get(h.number, {}).get("horse_id") or "", []))
        mine = {("父", h.sire), ("父系統", h.sire_line), ("母父", h.damsire), ("母父系統", h.damsire_line)} | {("5代", f) for f in flags}
        why = [f"{r['unit']}{'=' if r['unit'] != '5代' else 'に'}{r['name']}（{r['key'].replace('|', '・展開')}）{'○' if r['ae'][0] >= 1 else '▼'} A/E {r['ae'][0]:.2f}/{r['ae'][1]:.2f}"
               for r in rows if (r["unit"], r["name"]) in mine]
        if why:
            out.append((h.number, "、".join(why)))
    return out


def horse_conditions(card: dict, e: dict) -> list[str]:
    """tools/sire_quirks.py の conditions と同じ区分で、レース前に分かるこの馬の条件を返す（出馬表の近走から）."""
    import datetime as _dt
    su = card.get("surface"); co = card.get("course"); d = card.get("distance") or 1600
    GRL = {"1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}
    c = [su]
    g = e.get("gate")
    if g:
        c.append(f"{su}・{'内枠1-3' if g <= 3 else '外枠6-8' if g >= 6 else '中枠4-5'}")
    c.append(f"{su}・{'良' if (card.get('going') or '良').startswith('良') else '道悪'}")
    c.append(f"{su}・{'坂' if co in ('中山', '阪神', '中京', '東京') else '平坦'}")
    c.append(f"{su}・直線{'長' if co in ('東京', '新潟', '阪神', '京都', '中京') else '短'}")
    n = len(card.get("entries") or [])
    c.append(f"{su}・{'〜12頭' if n <= 12 else '13-15頭' if n <= 15 else '16頭〜'}")
    a = e.get("age")
    if a:
        c.append(f"{su}・{'2-3歳' if a <= 3 else '4歳' if a == 4 else '5歳以上'}")
    c.append(f"{su}・{'牝' if str(e.get('sex') or '').startswith('牝') else '牡セ'}")
    try:
        m = int(str(card.get("date"))[5:7])
        c.append(f"{su}・{'春' if 3 <= m <= 5 else '夏' if 6 <= m <= 8 else '秋' if 9 <= m <= 11 else '冬'}")
    except ValueError:
        pass
    prev = (e.get("recent") or [None])[0]
    if prev:
        if prev.get("surface") and prev["surface"] != su:
            c.append(f"{prev['surface']}→{su}")
        elif prev.get("distance"):
            dd = d - prev["distance"]
            c.append(f"{su}・{'延長' if dd >= 200 else '短縮' if dd <= -200 else '同距離'}")
        try:
            days = (_dt.date.fromisoformat(card["date"]) - _dt.date.fromisoformat(prev["date"])).days
            c.append(f"{su}・{'中2週以内' if days <= 21 else '中3-8週' if days <= 63 else '9週以上'}")
        except (KeyError, TypeError, ValueError):
            pass
        if e.get("weight") and prev.get("weight_carried"):
            w = e["weight"] - prev["weight_carried"]
            if w >= 1:
                c.append(f"{su}・斤量増")
            elif w <= -1:
                c.append(f"{su}・斤量減")
        f = prev.get("finish")
        if f:
            c.append(f"{su}・前走{'1-3着' if f <= 3 else '4-9着' if f <= 9 else '10着以下'}")
        b = prev.get("behind")
        if b is not None and f and f > 1:
            c.append(f"{su}・前走{'0.5秒内' if b <= 0.5 else '0.5-1.5秒' if b < 1.5 else '1.5秒以上'}負け")
        g0, g1 = GRL.get(prev.get("grade") or "", 4), GRL.get(card.get("grade") or "", 4)
        c.append(f"{su}・{'昇級' if g1 > g0 else '降級' if g1 < g0 else '同級'}")
    return c


def sire_quirk_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """種牡馬（父・母父）×条件のクセ（網羅スキャン, data/knowledge/sire_quirks.json, tools/sire_quirks.py）.
    2021-24年で選んだものが2025-26年も同じ向きだったのは65%・上積み+4.6%なので材料."""
    import json
    from .config import KNOWLEDGE_DIR
    try:
        kb = json.loads((KNOWLEDGE_DIR / "sire_quirks.json").read_text(encoding="utf-8"))["rows"]
    except (OSError, ValueError, KeyError):
        return []
    idx = defaultdict(list)
    for r in kb:
        idx[(r["who"], r["name"])].append(r)
    ent = {e.get("number"): e for e in card.get("entries") or []}
    out = []
    for h in evals:
        e = ent.get(h.number, {})
        cs = set(horse_conditions(card, e))
        why = []
        for who, nm in (("父", h.sire), ("母父", h.damsire)):
            for r in idx.get((who, nm), []):
                if r["cond"] in cs:
                    why.append(f"{who}{nm}×{r['cond']} {r['mark']}（A/E {'/'.join(f'{v:.2f}' for v in r['ae'])}）")
        if why:
            out.append((h.number, "、".join(why)))
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
    labels = {"★": "★ 血統の穴（8番人気以下で血統要素が最上位。単独では単勝・複勝・ワイド・馬連・3連複どの買い方も回収率56〜91%で負け越し。妙味条件(厳格)と重なる馬だけ買う＝厳格軸の買い目に含まれる。それ以外は見るだけ）", "専門家": "専門家の見解に該当", "検証済み": "検証済みの傾向（3期間で回収率100%超）に該当", "走る条件": "人気帯の中で走る条件が重なる（検証: 7〜9番人気の満点は単勝101%/172%。10番人気以下は複勝60〜70%台で単独では買わない。ヒモ候補）",
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
    mg_lab, mg = mainstream_gap(card, evals)
    if mg_lab:
        L.append(f"- 馬場の主流度: {mg_lab}")
    if mg:
        L.append("- ★主流／反主流のずれ（芝の道悪で人気上位が日本型ばかり。反主流血統の4〜9番人気は検証で3着内A/E 1.14/1.12/1.18・複勝回収102/97/99%）: "
                 + "、".join(f"{h.number}{h.name}（{h.pop_rank}人気・父{h.sire}）" for h in mg))
    pl, pb = pace_blood_horses(card, evals)
    if pl:
        L.append(f"- 展開予想: {pl}")
    if pb:
        L.append("- 展開×血統（この展開で3期間とも人気以上○/以下▼の系統・種牡馬。単独の回収率は100%前後なので材料）:")
        nm = {h.number: h for h in evals}
        for num, txt in pb:
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    bk = book_condition_horses(card, evals)
    if bk:
        L.append("- 系統×レース条件（亀谷『血統の教科書』の切り口。3期間とも人気以上○/以下▼。▼は消しの材料、○は単独の回収率100%前後なので材料）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(bk, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    sq = sire_quirk_horses(card, evals)
    if sq:
        L.append("- 種牡馬のクセ（父・母父×ローテ・枠・間隔・馬場・前走など。2021-23/2024/2025-26の3期間とも人気以上○/以下▼）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(sq, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    cb = course_blood_horses(card, evals)
    if cb:
        L.append("- コース別の血統傾向（このコースで2021-23年・2024-26年とも人気以上○/以下▼。2025-26年の再現率65%なので材料）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(cb, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    sr = sire_recent_horses(card, evals)
    if sr:
        L.append("- 最新の種牡馬傾向（2024年・2025-26年とも人気以上○/以下▼。本に無い新しい種牡馬も産駒実績から分類）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(sr, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
            h = nm.get(num)
            L.append(f"  - {horse_line(h) if h else num}：{txt}")
    el = [(e.get("number"), elim_reason(e)) for e in card.get("entries") or []]
    el = [(n, w) for n, w in el if w]
    if el:
        nm = {h.number: h for h in evals}
        L.append("- 消し（3着内率5%前後。推奨からは外してある）: " + "、".join(
            f"{n}{nm[n].name if n in nm else ''}（{nm[n].pop_rank if n in nm else '?'}人気）{w}" for n, w in el))
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


GUIDE = """## 買い方の早見表（過去1年の実払戻で検証した結果。上から優先）
| 項目 | 買う？ | 買い方 | 検証の回収率（前半/後半） |
|---|---|---|---|
| ◎妙味条件(厳格)の軸 | **買う（中心）** | 穴の軸から人気馬へ流す: 軸の単勝＋ワイド（軸→1〜5番人気）＋馬連（軸→1〜3番人気）＋3連複（軸−1・2番人気−モデル上位5頭）。買い目カードの点をそのまま | 146% / 140% |
| 本線 | 買う（少なめ） | 本線馬の単勝・複勝＋本線馬から馬連（買い目カードの点） | 114% / 120% |
| 準本線 | 少額 | 単勝・複勝だけ | 単勝101%/172%・複勝94%/123% |
| 遊び | 買わない | （負け越し） | 60〜80%台 |
| ★血統の穴・走る条件・回収率の高い条件・牝系・直結コース・前走0.6秒差・開催×血統・専門家・系統の型 | 買わない | 見るだけ（どれも単独では負け越し。◎や本線に重なっていれば、その馬はすでに買い目に入っている） | 56〜91% |
| 危険な人気馬 | — | 消しではない。軸・1着付けにしない | — |
"""

