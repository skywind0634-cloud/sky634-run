"""チャット・予想ページ向けの「レースごとの注目馬一覧」.

本線（妙味馬の単複）だけでなく、DBが拾った材料を持つ馬を全部並べる（買うかは読む人が選ぶ）:
- 本線: 4〜9番人気で予測勝率が市場の1.3倍以上、かつ人気帯の中で走る条件がプラス（単複の本線。検証 docs/analysis/strategy.md）
- ★: 8番人気以下で血統要素の合計が高い馬
- 専門家: 望田潤・亀谷敬正・白井寿昭などの見解のうち、種牡馬・配合を名指しした具体的なもの
- 走る条件: 人気帯の平均より走る条件が重なる馬（cond_score ≥ 0.4）
- 妙味条件: 過去の複数期間で回収率100%超の条件に当てはまる馬
- 牝系: 母・2代母の一族がこの条件で人気以上に走る（初めての条件なら特に）
- 危険（過信禁物の人気馬）: 1〜3番人気でフラグ点-2以下かつ予測勝率が市場以下、または来ない条件が重なり予測勝率が市場の0.8倍未満の馬（消しではない）
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


DANGER_TOP3 = {1: "3着内49〜56%（1番人気の平均62%）", 2: "3着内42〜43%（2番人気の平均51%）", 3: "3着内32〜37%（3番人気の平均39%）"}


def is_overrated(h: HorseEval, flag: int | None) -> bool:
    """過信禁物の人気馬（2026-10-17 見直し, docs/analysis/danger_recheck.md）.
    旧基準（来ない条件 -0.3 以下だけ）は後半期に3着内率が同人気の平均と変わらなかった（A/E 0.86/0.96）。
    フラグ点-2以下かつ予測勝率が市場以下、または来ない条件-0.3以下かつ予測勝率が市場の0.8倍未満に絞る（過去1年で A/E 0.81/0.88）。
    それでも1番人気は半分以上3着内に来るので、消しではなく軸・1着付けにしないための印."""
    if (h.pop_rank or 99) > 3:
        return False
    ratio = h.p_win / h.p_market if h.p_market else 1.0
    if flag is not None and flag <= -2 and ratio < 1.0:   # モデルが市場より高く見ている馬（本線候補）とは矛盾させない
        return True
    return h.cond_score <= -0.3 and ratio < 0.8


def race_digest(evals: list[HorseEval], flags: dict | None = None) -> dict:
    """カテゴリ → [(馬, 一言)]. flags は flag_scores の結果（無ければ来ない条件だけで判定）."""
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
        fl = (flags or {}).get(h.number)
        if is_overrated(h, fl):
            why = ([f"フラグ点{fl:+d}"] if fl is not None and fl <= -2 else []) + ([f"予測/市場 {h.p_win / h.p_market:.2f}"] if h.p_market else [])
            out["危険"].append((h, DANGER_TOP3[h.pop_rank] + "。" + "・".join(why) + "。" + _short(_pick(h, "来ない条件"), 140)))
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
    lw = longshot_wide(card, evals)
    if lw:
        L.append("  - 穴ワイド（7番人気以下で材料が重なる上位2頭→1〜4番人気。検証 回収94%/108%・的中17〜19%・払戻中央約2,000円。"
                 "旧「遊び」は負け越しだったので置き換え）: " + " / ".join(lw))
    return (["**買い目カード**"] + L) if L else []


def longshot_net(card: dict, evals: list[HorseEval]) -> dict:
    """7番人気以下の馬番 → 材料の重なり（走る条件0.4以上・妙味条件・★血統穴 の数＋フラグ点）.
    過去1年で7番人気以下の3着内率は −1以下 5.5% → +3以上 11〜14%（docs/analysis/longshot_stack.md）."""
    sc = flag_scores(card, evals)
    star = {h.number for h in longshot_picks(evals)}
    return {h.number: int(h.cond_score >= 0.4) + int(bool(h.value_segments) or (h.value_edge or 0) > 0.15)
            + int(h.number in star) + sc.get(h.number, 0)
            for h in evals if (h.pop_rank or 0) >= 7}


def longshot_wide(card: dict, evals: list[HorseEval], th: int = 3) -> list[str]:
    """穴ワイド: 材料の重なり th 以上の上位2頭 × 1〜4番人気（tools/longshot_stack.py）."""
    net = longshot_net(card, evals)
    nm = {h.number: h for h in evals}
    pop = {h.pop_rank: h.number for h in evals if h.pop_rank}
    cand = sorted([n for n, v in net.items() if v >= th], key=lambda n: (-net[n], nm[n].pop_rank))[:2]
    return [f"{n}{nm[n].name}（{nm[n].pop_rank}人気・重なり{net[n]:+d}）→ ワイド " + "、".join(f"{n}-{pop[p]}" for p in (1, 2, 3, 4) if p in pop)
            for n in cand]


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


def pace_l3_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """展開予想（前走で前にいた馬の数）× 馬の上がり能力・位置取り（近3走, 同じ芝ダ）で3期間一貫した組（tools/pace_l3_predict.py）.
    スローなら残り600mからのよーいドン、ハイなら差し・上がりの脚がある馬。"""
    nf = front_count(card)
    if nf is None:
        return []
    su = card.get("surface"); pace = "スロー" if nf <= 1 else "ハイ" if nf >= 4 else "平均"
    tag = f"{pace}予想（前に行く馬{nf}頭）"
    ent = {e.get("number"): e for e in card.get("entries") or []}
    out = []
    for h in evals:
        e = ent.get(h.number, {}); pr = h.pop_rank or 0
        same = [x for x in (e.get("recent") or []) if x.get("surface") == su][:3]
        if not same:
            continue
        ranks = [r for r in (l3_rank(x) for x in same) if r is not None]
        r1 = l3_rank(same[0])
        n3 = sum(r <= 3 for r in ranks) if len(ranks) >= 2 else None
        try:
            pos = int(str(same[0].get("passing")).split("-")[0]) / max(same[0].get("n_runners") or 16, 1)
        except (ValueError, TypeError):
            pos = None
        fast = any((x.get("last3f") or 99) <= 33.5 for x in e.get("recent") or [] if x.get("surface") == "芝")
        why = []
        if su == "芝" and pace == "ハイ":
            if pr and pr <= 3 and n3 is not None and n3 <= 1:
                why.append(f"人気馬で近3走の上がり3位以内{n3}回 ×（A/E 0回0.77/0.79/0.85・1回0.87/0.67/0.85。速い流れを差せない）")
            elif pr and pr <= 3 and not fast:
                why.append("人気馬で芝の上がり33.5秒以下の経験なし ×（A/E 0.84/0.75/0.80）")
            if pr >= 7 and pos is not None and pos > 0.6:
                why.append("人気薄で前走後方 ◎（差し届く, A/E 1.48/1.24/1.18）")
            if pr >= 7 and r1 is not None and 2 <= r1 <= 3:
                why.append("人気薄で前走上がり2-3位 ◎（A/E 1.17/1.30/1.95）")
        if su == "芝" and pace == "スロー":
            if pr >= 7 and n3 is not None and n3 >= 2:
                why.append("人気薄で近3走の上がり3位以内2回以上 ○（よーいドン向き, A/E 1.10/1.07/1.13）")
            if pr >= 7 and pos is not None and pos > 0.6:
                why.append("人気薄で前走後方 ×（スローで届かない, A/E 0.87/0.89/0.88）")
            if pr and pr <= 3 and pos is not None and 0.15 < pos <= 0.6:
                why.append("人気馬で前走中団 ○（A/E 1.06/1.09/1.06）")
        if su == "芝" and pace == "平均":
            if pr >= 7 and r1 is not None and 2 <= r1 <= 3:
                why.append("人気薄で前走上がり2-3位 ○（A/E 1.08/1.12/1.35）")
            if pr and pr <= 3 and r1 is not None and r1 >= 4:
                why.append("人気馬で前走上がり4位以下 ▽（A/E 0.93/0.92/0.94）")
            if 4 <= pr <= 6 and pos is not None and 0.15 < pos <= 0.6:
                why.append("4-6番人気で前走中団 ○（A/E 1.12/1.07/1.07）")
        if su == "ダ" and pace == "ハイ":
            if pr and pr <= 3 and r1 is not None and r1 >= 4:
                why.append("人気馬で前走上がり4位以下 ▽（A/E 0.88/0.89/0.95）")
            if pr >= 7 and pos is not None and 0.15 < pos <= 0.6:
                why.append("人気薄で前走中団 ◎（A/E 1.20/1.14/1.20）")
        if su == "ダ" and pace == "平均" and pr >= 7 and pos is not None and 0.15 < pos <= 0.6:
            why.append("人気薄で前走中団 ◎（A/E 1.11/1.10/1.10）")
        if su == "ダ" and pace == "スロー":
            if 4 <= pr <= 6 and r1 is not None and 2 <= r1 <= 3:
                why.append("4-6番人気で前走上がり2-3位 ○（A/E 1.07/1.08/1.09）")
            if pr >= 7 and pos is not None and pos > 0.6:
                why.append("人気薄で前走後方 ▽（A/E 0.95/0.87/0.88）")
        if why:
            out.append((h.number, f"{tag}: " + "、".join(why)))
    return out


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


def ten3f_gap(card: dict, prev: dict | None) -> float | None:
    """予想テン3F差＝今回コースの平均テン3F − 前走の実際のテン3F（+は前走より遅い=楽, tools/souma_ten3f.py）."""
    global _TEN3F
    import json
    import sqlite3
    from .config import DB_PATH, KNOWLEDGE_DIR
    if not prev or not prev.get("race_id") or prev.get("surface") != card.get("surface"):
        return None
    try:
        _TEN3F
    except NameError:
        try:
            _TEN3F = json.loads((KNOWLEDGE_DIR / "course_ten3f.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _TEN3F = {}
    mean = _TEN3F.get(f"{card.get('course')}|{card.get('surface')}|{card.get('distance')}")
    if mean is None:
        return None
    try:
        with sqlite3.connect(DB_PATH) as c:
            row = c.execute("select first3f from races where race_id=?", (str(prev["race_id"]),)).fetchone()
    except sqlite3.Error:
        return None
    return mean - row[0] if row and row[0] else None


def l3_rank(prev: dict | None) -> int | None:
    """近走1走の上がり3Fのレース内順位（DB にそのレースがある場合だけ, tools/souma_ability.py）."""
    import sqlite3
    from .config import DB_PATH
    if not prev or not prev.get("race_id") or not prev.get("number"):
        return None
    try:
        with sqlite3.connect(DB_PATH) as c:
            rs = c.execute("select number,last3f from results where race_id=? and last3f is not null", (str(prev["race_id"]),)).fetchall()
    except sqlite3.Error:
        return None
    mine = [l for n, l in rs if n == prev["number"]]
    return 1 + sorted(l for _, l in rs).index(mine[0]) if mine else None


def souma_good(x: dict) -> bool | None:
    """双馬の好走＝人気より上の着順で5着以内かつ上がり3位以内（上がり順位が分からなければ None）."""
    fin, pop = x.get("finish") or 99, x.get("popularity") or 0
    if not (fin <= 5 and fin < pop):
        return False
    r = l3_rank(x)
    return None if r is None else r <= 3


def turf_day_dev(card: dict, surface: str = "芝") -> float | None:
    """当日（先のレース）・前日の同場の勝ちタイムとコース平均との差の平均（-は速い, DB に結果がある場合だけ, tools/souma_ch2a.py）. surface でダートも可."""
    import datetime as _dt
    import sqlite3
    from .config import DB_PATH
    try:
        d0 = card["date"]; d1 = (_dt.date.fromisoformat(d0) - _dt.timedelta(days=1)).isoformat()
        with sqlite3.connect(DB_PATH) as c:
            rs = c.execute("select ra.race_id,ra.date,ra.distance,r.time_sec from races ra join results r using(race_id) where ra.course=? and ra.surface=? "
                           "and r.finish=1 and r.time_sec is not null and (ra.date=? and ra.race_no<? or ra.date=?)",
                           (card.get("course"), surface, d0, card.get("race_no") or 99, d1)).fetchall()
            devs = []
            for rid, dte, dist, t in rs:
                m = c.execute("select avg(t) from (select r.time_sec t from races ra join results r using(race_id) where ra.course=? and ra.surface=? "
                              "and ra.distance=? and r.finish=1 and r.time_sec is not null and ra.date<? order by ra.date desc limit 200)",
                              (card.get("course"), surface, dist, dte)).fetchone()[0]
                if m:
                    devs.append(t - m)
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        return None
    return sum(devs) / len(devs) if len(devs) >= 2 else None


def fast_turf_day(card: dict) -> bool | None:
    """芝の高速日（当日・前日の同場の勝ちタイムが平均0.5秒以上速い）."""
    v = turf_day_dev(card)
    return None if v is None else v <= -0.5


# 双馬 第3章 p153 馬場替わりの注目血統（tools/surface_switch.py）
SWITCH_DIRT_LINES = {"デピュティミニスター系", "エーピーインディ系", "ゴールドアリュール系", "フォーティナイナー系", "ストームキャット系", "ヘネシー系", "ブライアンズタイム系"}
SWITCH_DIRT_NAMES = {"スマートファルコン", "カネヒキリ", "タートルボウル", "ワイルドラッシュ", "アジュディケーティング", "アフリート", "ディアブロ"}
SWITCH_TURF_NAMES = {"タイキシャトル", "アンバーシャダイ", "タマモクロス", "ダンシングブレーヴ", "カーリアン", "Caerleon", "コジーン", "Cozzene", "フェアリーキング"}

# 双馬 p138-141 高速血統（母父の系統）と、ダートで前が止まらない馬場に強い父系（tools/speed_blood.py）
SPEED_DAM_LINES = {"ボールドルーラー系", "エーピーインディ系", "デピュティミニスター系", "ストームキャット系", "ヘネシー系", "ミスタープロスペクター系",
                   "フォーティナイナー系", "ファピアノ系", "ゴーンウエスト系", "シーキングザゴールド系", "スマートストライク系", "キングマンボ系", "キングカメハメハ系"}
DIRT_FRONT_LINES = {"エーピーインディ系", "ボールドルーラー系", "ヘネシー系", "ストームキャット系", "ファピアノ系", "キングカメハメハ系", "ゴーンウエスト系"}

# 双馬『延長が得意な種牡馬』リスト（p51）
SOUMA_EXT_SIRES = {"アイルハヴアナザー", "ウォーエンブレム", "エンパイアメーカー", "オレハマッテルゼ", "キャプテンスティーヴ", "キンシャサノキセキ", "ゴールドシップ",
                   "コンデュイット", "スズカマンボ", "チーフベアハート", "チチカステナンゴ", "ディープスカイ", "デュランダル", "ドリームジャーニー", "ネオユニヴァース",
                   "ノヴェリスト", "ハーツクライ", "ハービンジャー", "フォーティナイナーズサン", "ホワイトマズル", "マリエンバード", "メイショウサムソン", "ヨハネスブルグ", "ワークフォース"}

TURF_START_DIRT = {("東京", 1600), ("中山", 1200), ("福島", 1150), ("新潟", 1200), ("京都", 1400), ("阪神", 1400), ("阪神", 2000), ("中京", 1400)}


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
    nfront = front_count(card)
    tdev = turf_day_dev(card, su) if su in ("芝", "ダ") else None
    _rs = []
    for _e in card.get("entries") or []:
        _p = (_e.get("recent") or [None])[0]
        if _p and _p.get("surface") == su and _p.get("distance"):
            _rs.append(d >= _p["distance"] + 200)
    ext_share = sum(_rs) / len(_rs) if _rs else 0
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
        # 双馬 第1章 p43-51 苦手ローテでの善戦・好走の定義（tools/souma_ability.py）
        if len(same) >= 2 and same[0] is rec[0]:
            pr_ = h.pop_rank or 0
            f0, p0 = same[0].get("finish") or 99, same[0].get("popularity") or 0
            beat = f0 <= 5 and f0 < p0
            l3r = l3_rank(same[0])
            if r0 == "同距離" and r1 == "同距離" and beat and pr_ >= 7 and not (4 <= f0 <= 5):
                why.append(f"前走同距離で人気より上の{f0}着→今回同距離×7番人気以下 ◎（A/E ダ1.18/1.37/1.26・芝1.13/1.45/1.27。前走の好走が人気に反映されていない）")
            if r0 == "同距離" and r1 == "同距離" and beat and pr_ and pr_ <= 3 and l3r is not None:
                if su == "ダ" and l3r >= 4:
                    why.append("ダ・前走同距離で人気より上の5着以内（上がり4位以下）→同距離×1-3番人気 ▽（A/E 0.89/0.91/0.91。前に行った恵まれの好走は人気になりすぎ）")
                if su == "芝" and l3r <= 3:
                    why.append("芝・前走同距離で双馬の好走→同距離×1-3番人気 ▽（A/E 0.95/0.88/0.88）")
            if su == "ダ" and r0 == "短縮" and r1 == "延長" and pr_ >= 7 and not beat and l3r is not None and l3r >= 4:
                why.append("ダ・前走短縮で凡走（上がり4位以下）→今回延長×7番人気以下 ×（A/E 0.84/0.54/0.86）")
            # その馬の短縮型・延長型（過去の短縮/延長で双馬の好走が3回に1回以上）
            cnt = {"短縮": [0, 0], "延長": [0, 0]}
            for i in range(len(same) - 1):
                rr = _rot(same[i]["distance"], same[i + 1]["distance"])
                if rr in cnt:
                    cnt[rr][0] += 1; cnt[rr][1] += bool(souma_good(same[i]))
            sk = cnt["短縮"][0] and cnt["短縮"][1] * 3 >= cnt["短縮"][0]
            ek = cnt["延長"][0] and cnt["延長"][1] * 3 >= cnt["延長"][0]
            # 双馬 p52-64「異質な馬」（tools/souma_ch1b.py）: 血統の向きと逆のローテで好走歴
            g_s, g_e = cnt["短縮"][1] > 0, cnt["延長"][1] > 0
            ext_b = stt == "欧州型" or h.sire in SOUMA_EXT_SIRES
            if stt == "米国型" and g_e and r1 == "同距離" and (pr_ >= 7 or (su == "ダ" and pr_ <= 3)):
                why.append(f"父米国型なのに延長で好走歴→今回同距離 {'◎' if pr_ >= 7 else '○'}（双馬『異質な馬は能力が高い』, A/E "
                           + ("7番人気以下 ダ1.22/1.36/1.11・芝1.62/1.20/1.69）" if pr_ >= 7 else "ダ1-3番人気 1.13/1.09/1.09）"))
            if su == "ダ" and stt == "米国型" and g_s and not g_e and r1 == "延長" and pr_ >= 7:
                why.append("ダ・父米国型で短縮でだけ好走歴→今回延長×7番人気以下 ◎（A/E 1.12/1.89/1.63。本の『短縮向き』と逆）")
            if ext_b and g_s and r1 == "短縮" and pr_ >= 7:
                why.append("ダ・延長向き血統なのに短縮で好走歴→今回短縮×7番人気以下 ○（A/E 1.15/1.06/1.88）" if su == "ダ"
                           else "芝・延長向き血統（父欧州型/双馬リスト）なのに短縮で好走歴→今回短縮×7番人気以下 ×（A/E 0.67/0.58/0.76。本の『異質な馬を狙え』と逆）")
            if su == "芝" and ext_b and g_e and not g_s and r1 == "短縮" and pr_ >= 7:
                why.append("芝・延長向き血統で延長でだけ好走歴→今回短縮×7番人気以下 ×（A/E 0.78/0.89/0.82）")
            if su == "芝" and ext_b and g_e and not g_s and r1 == "同距離" and 4 <= pr_ <= 6:
                why.append("芝・延長向き血統で延長でだけ好走歴→今回同距離×4-6番人気 ×（A/E 0.88/0.84/0.87）")
            if su == "ダ" and r1 == "同距離" and pr_ >= 7 and (e.get("age") == 2 or (e.get("age") == 3 and str(card.get("date", ""))[5:7] <= "06")):
                why.append("2-3歳（3歳は6月まで）のダ・同距離×7番人気以下 ◎（A/E 1.34/1.37/1.22・複勝回収135/113/132%）")
            if su == "ダ" and r1 == "延長" and not going.startswith("良"):
                why.append("ダートの道悪×延長 ▽（A/E 0.94/0.82/0.90）")
            if pr_ >= 7:
                if su == "芝" and sk and ek and r1 == "同距離":
                    why.append("芝・短縮でも延長でも双馬の好走あり→今回同距離×7番人気以下 ◎（A/E 1.21/1.25/1.59）")
                elif su == "芝" and sk and r1 == "延長":
                    why.append("芝・短縮型（短縮で好走）→今回延長×7番人気以下 ◎（A/E 1.15/1.14/1.14。本は短縮を狙えとするが、実際は能力の裏付けとして効く）")
                elif su == "芝" and ek and r1 == "短縮":
                    why.append("芝・延長型（延長で好走）→今回短縮×7番人気以下 ○（A/E 1.08/1.22/1.23）")
                elif su == "ダ" and sk and r1 == "同距離":
                    why.append("ダ・短縮型（短縮で好走）→今回同距離×7番人気以下 ◎（A/E 1.22/1.14/1.18）")
        if su == "ダ" and prv and prv.get("surface") == "ダ" and prv.get("distance") and d <= prv["distance"] - 200 and "Affirmed" in pf:
            why.append("ダートの距離短縮×5代にAffirmed ○（A/E 1.41/1.08/1.28。双馬は延長得意とするが短縮で走る）")
        # 双馬 第2章 ディープインパクト・キングカメハメハ（tools/souma_ch2a.py, 後継種牡馬でも検証）
        dct = country_type(h.damsire_line) if h.damsire_line else None
        male = not str(e.get("sex") or "").startswith("牝")
        if su == "芝" and h.sire_line == "ディープインパクト系" and h.sire != "ディープインパクト" and dct == "欧州型":
            ag = e.get("age") or 0
            if ag <= 3 and male:
                why.append("芝×父ディープ系後継×母父欧州型×2-3歳牡 ○（A/E 1.07/1.16/1.08。双馬『母父欧州型は完成が遅い』と逆）")
            elif ag == 4 and not male:
                why.append("芝×父ディープ系後継×母父欧州型×4歳牝 ○（A/E 1.10/1.30/1.08）")
            elif ag >= 5 and not male:
                why.append("芝×父ディープ系後継×母父欧州型×5歳以上牝 ▽（A/E 0.94/0.71/0.92。双馬『牝は劣化しにくい』と逆）")
        # 双馬 第2章 ハーツクライ・ステイゴールド（tools/souma_ch2b.py, 後継種牡馬でも検証）
        pv_ = rec[0] if rec else None
        r1_ = None
        if pv_ and pv_.get("surface") == su and pv_.get("distance"):
            r1_ = "短縮" if d <= pv_["distance"] - 200 else "延長" if d >= pv_["distance"] + 200 else "同距離"
        if su == "芝" and h.sire == "ハーツクライ" and r1_ == "同距離":
            why.append("芝の同距離×父ハーツクライ ▽（A/E 0.89/0.92/0.91）")
        if su == "ダ" and h.sire_line == "ハーツクライ系" and h.sire not in ("ハーツクライ", "ジャスタウェイ") and r1_ == "短縮":
            why.append("ダートの距離短縮×父ハーツ系後継 ○（A/E 1.22/1.09/1.82。双馬『ハーツは短縮苦手』と逆）")
        if su == "芝" and h.sire_line == "ハーツクライ系" and h.sire != "ハーツクライ" and r1_ == "延長" and ext_share >= 0.5:
            why.append(f"芝の延長×父ハーツ系後継×出走馬の{ext_share:.0%}が延長 ×（A/E 0.85/0.82/0.62。双馬『他馬が初めての延長なら有利』と逆）")
        if su == "芝" and h.sire_line == "ステイゴールド系":
            if tdev is not None and tdev >= 0.5:
                why.append(f"芝の時計がかかる日（当日・前日の同場 +{tdev:.1f}秒）×父ステゴ系 ○（A/E 1.14/1.09/1.10。双馬『タフな馬場』のとおり。道悪かどうかでは差なし）")
            if co in ("中山", "福島", "小倉", "函館", "札幌"):
                if 4 <= (h.pop_rank or 0) <= 6:
                    why.append("小回り芝（中山・ローカル）×父ステゴ系×4-6番人気 ◎（A/E 1.25/1.29/1.20。双馬『小回り適性』のとおり）")
                elif (h.pop_rank or 0) >= 7 and h.sire == "ゴールドシップ":
                    why.append("小回り芝×父ゴールドシップ×7番人気以下 ▽（A/E 0.90/0.73/0.77）")
        # 内回り/外回り（tools/layout_check.py, レース結果の表記で判定。出馬表に無ければ距離から一意に決まる場合だけ）
        if su == "芝" and co in ("京都", "阪神", "中山", "新潟"):
            from . import knowledge as _K
            lay = card.get("layout") or (None if (co, d) in (("京都", 1400), ("京都", 1600), ("新潟", 2000))
                                         else _K._LAYOUT.get((co, "芝"), {}).get(d))
            try:
                ppos = int(str(rec[0].get("passing")).split("-")[0]) / max(rec[0].get("n_runners") or 16, 1) if rec else None
            except (ValueError, TypeError):
                ppos = None
            pr2 = h.pop_rank or 0
            if co == "京都" and lay == "外":
                if h.sire_line == "ディープインパクト系":
                    why.append("京都芝外回り×父ディープ系 ○（A/E 1.20/1.15/1.09。内回りは1.09/0.87/0.94で差がない）")
                elif stt == "日本型":
                    why.append("京都芝外回り×父日本型 ○（A/E 1.13/1.09/1.06。欧州型は0.92/0.97/0.98）")
            if co == "阪神" and lay == "外":
                if pr2 and pr2 <= 3 and ppos is not None and 0.15 < ppos <= 0.6:
                    why.append("阪神芝外回り×前走中団×1-3番人気 ◎（A/E 1.15/1.16/1.14）")
                if h.sire_line == "キングカメハメハ系":
                    why.append("阪神芝外回り×父キンカメ系 ○（A/E 1.11/1.54/1.05）")
            if co == "中山" and lay == "内" and ppos is not None:
                if 4 <= pr2 <= 6 and 0.15 < ppos <= 0.6:
                    why.append("中山芝内回り×前走中団×4-6番人気 ◎（A/E 1.23/1.42/1.13）")
                if pr2 >= 7 and ppos > 0.6:
                    why.append("中山芝内回り×前走後方×7番人気以下 ▽（A/E 0.81/0.92/0.63。直線が短く届かない）")
            if co == "中山" and lay == "外" and h.sire_line == "シンボリクリスエス系":
                why.append("中山芝外回り×父シンボリクリスエス系 ×（A/E 0.74/0.84/0.77）")
        # 双馬 第2章 ハービンジャー・ゴールドアリュール・マンハッタンカフェ（tools/souma_ch2d.py, 後継含む）
        if su == "ダ" and h.sire_line == "ゴールドアリュール系" and h.sire != "ゴールドアリュール" and (h.pop_rank or 0) >= 7:
            if r1_ == "延長":
                why.append("ダートの延長×父ゴールドアリュール系後継×7番人気以下 ×（A/E 0.36/0.00/0.31。双馬『延長で嫌う』のとおり）")
            if co in ("東京", "京都"):
                why.append("東京・京都ダート×父ゴールドアリュール系後継×7番人気以下 ×（A/E 0.85/0.60/0.60。双馬『軽いダートが得意』と逆）")
        if su == "芝" and h.sire == "ハービンジャー" and r1_ == "同距離" and 4 <= (h.pop_rank or 0) <= 6:
            why.append("芝の同距離×父ハービンジャー×4-6番人気 ×（A/E 0.79/0.82/0.70）")
        if h.sire_line == "マンハッタンカフェ系":
            bw_ = e.get("body_weight") or (rec[0].get("body_weight") if rec else None)
            if bw_ and su == "芝" and bw_ < 500:
                why.append("芝×父マンハッタンカフェ系×500kg未満 ○（A/E 1.31/1.07/1.53。双馬『コンパクトな馬は良い馬』のとおり）")
            if bw_ and su == "ダ" and bw_ >= 500:
                why.append("ダート×父マンハッタンカフェ系×500kg以上 ○（A/E 1.08/1.41/1.10。大型はダートでパワーを活かす）")
        # 双馬 第2章 キンシャサノキセキ・サウスヴィグラス・ネオユニヴァース（tools/souma_ch2e.py）
        if su == "芝" and h.sire == "キンシャサノキセキ" and r1_ == "同距離" and (h.pop_rank or 0) >= 7:
            why.append("芝の同距離×父キンシャサノキセキ×7番人気以下 ◎（A/E 1.11/1.27/1.18）")
        if su == "ダ" and h.damsire == "サウスヴィグラス" and r1_ == "同距離":
            why.append("ダートの同距離×母父サウスヴィグラス ○（A/E 1.07/1.16/1.08）")
        if su == "芝" and h.damsire == "ネオユニヴァース" and fast_turf_day(card):
            why.append("芝の高速日×母父ネオユニヴァース ×（A/E 0.86/0.65/0.74。双馬『高速決着に対応できない』のとおり）")
        # 双馬 第2章 p118-127 ブラックタイド（後継キタサンブラック）・ヘニーヒューズ・ジャスタウェイ（tools/sire_rotation_check.py → docs/analysis/souma_ch2f.md）
        if h.sire == "キタサンブラック" and r1_:
            if su == "芝" and r1_ == "延長":
                why.append("芝の延長×父キタサンブラック ○（A/E 1.12/1.10/1.10。父ブラックタイドの『短縮向き』と逆）")
            if su == "芝" and r1_ == "短縮" and (e.get("age") or 0) >= 4:
                why.append("芝の短縮×父キタサンブラック×4歳以上 ◎（A/E 1.43/1.32/1.13）")
            if su == "ダ" and r1_ == "同距離" and (e.get("age") or 0) >= 4:
                why.append("ダートの同距離×父キタサンブラック×4歳以上 ○（A/E 1.12/1.07/1.16）")
        if su == "ダ" and h.sire == "ヘニーヒューズ" and r1_:
            if r1_ == "短縮" and (e.get("age") or 0) >= 4:
                why.append("ダートの短縮×父ヘニーヒューズ×4歳以上 ○（A/E 1.15/1.17/1.07。双馬『短縮ならいつでも狙える』のとおり）")
            sm = [x for x in rec if x.get("surface") == "ダ" and x.get("distance")]
            if r1_ == "同距離" and len(sm) >= 2 and abs(sm[0]["distance"] - sm[1]["distance"]) < 200 and 4 <= (sm[0].get("finish") or 0) <= 5:
                why.append("ダ・前走同距離で4-5着→今回同距離×父ヘニーヒューズ ×（A/E 0.88/0.85/0.60）")
        if su == "芝" and h.sire == "ジャスタウェイ" and r1_ == "同距離" and (h.pop_rank or 0) >= 7:
            why.append("芝の同距離×父ジャスタウェイ×7番人気以下 ◎（A/E 1.43/1.18/1.55）")
        # 双馬 第3章 p152-153 馬場替わりの注目血統（tools/surface_switch.py）。前走と芝ダが替わった馬
        if prv and prv.get("surface") in ("芝", "ダ") and prv["surface"] != su:
            prs2 = h.pop_rank or 0
            if su == "ダ":
                in_list = h.sire_line in SWITCH_DIRT_LINES or h.damsire_line in SWITCH_DIRT_LINES or h.sire in SWITCH_DIRT_NAMES or h.damsire in SWITCH_DIRT_NAMES
                bw2 = e.get("body_weight") or prv.get("body_weight")
                if not in_list and 4 <= prs2 <= 6:
                    why.append("芝→ダ替わり×双馬のダート替わり血統なし×4-6番人気 ×（A/E 0.79/0.67/0.82。リストの血があっても人気以上には走らない）")
                if bw2 and bw2 >= 500 and prs2 >= 4:
                    why.append("芝→ダ替わり×馬体重500kg以上×4番人気以下 ×（A/E 4-6番人気0.72/0.65/0.85・7番人気以下0.70/0.66/0.84。双馬『大型の芝馬がダートを使われる』の逆側も成り立たない）")
            else:
                in_list = h.sire_line in ("デインヒル系", "プリンスリーギフト系") or h.damsire_line in ("デインヒル系", "プリンスリーギフト系") \
                    or h.sire in SWITCH_TURF_NAMES or h.damsire in SWITCH_TURF_NAMES or "カロ系" in pf
                if not in_list and prs2 and prs2 <= 3:
                    why.append("ダ→芝替わり×双馬の芝替わり血統なし×1-3番人気 ×（A/E 0.85/0.85/0.88）")
                if prs2 >= 7 and not any(x.get("surface") == "芝" for x in rec):
                    why.append("ダ→芝替わり×芝初出走×7番人気以下 ×（A/E 0.69/0.53/0.78）")
        # 双馬 p138-141 高速血統（tools/speed_blood.py）。当日・前日の同場の勝ちタイムで馬場の速さを判定
        fast_dam = (h.damsire_line in SPEED_DAM_LINES and h.damsire not in ("キングズベスト", "ワークフォース", "ルーラーシップ")) or "インリアリティ" in pf
        prs = h.pop_rank or 0
        if su == "芝" and tdev is not None:
            if tdev <= -0.5 and fast_dam and prs and prs <= 3:
                why.append(f"芝の高速日（{tdev:+.1f}秒）×母系に高速血統×1-3番人気 ▽（A/E 0.93/0.94/0.94。高速血統の人気馬は人気になりすぎ）")
            if tdev <= -0.5 and fast_dam and h.sire_line in SS_LINES_ALL and 4 <= prs <= 6:
                why.append(f"芝の高速日（{tdev:+.1f}秒）×父サンデー系×母系に高速血統×4-6番人気 ○（A/E 1.09/1.24/1.08。双馬『高速対応は牝系で決まる』のとおり）")
            if tdev >= 0.5 and not fast_dam and prs >= 7:
                why.append(f"芝の時計がかかる日（+{tdev:.1f}秒）×母系に高速血統なし×7番人気以下 ◎（A/E 1.15/1.10/1.16）")
        if su == "ダ" and h.sire_line in DIRT_FRONT_LINES and prs >= 7:
            if not going.startswith("良") and not going.startswith("稍"):
                why.append("ダートの重・不良×父が米国の先行型×7番人気以下 ○（A/E 1.07/1.49/1.05。双馬『前が止まらない馬場』のとおり）")
            elif tdev is not None and tdev >= 0.5:
                why.append(f"ダートの時計がかかる日（+{tdev:.1f}秒）×父が米国の先行型×7番人気以下 ○（A/E 1.08/1.32/1.09）")
        # 双馬 第2章 ダイワメジャー・ルーラーシップ・ロードカナロア（tools/souma_ch2c.py）
        prr = h.pop_rank or 0
        if su == "芝" and h.sire == "ダイワメジャー":
            if r1_ == "延長" and prr >= 7:
                why.append("芝の延長×父ダイワメジャー×7番人気以下 ×（A/E 0.54/0.51/0.69。双馬『延長が苦手』のとおり。短縮が得意は確認できず）")
            try:
                if pv_ and pv_.get("surface") == "芝" and int(str(pv_.get("passing")).split("-")[0]) / max(pv_.get("n_runners") or 16, 1) > 0.6:
                    why.append("芝×父ダイワメジャー×前走後方 ▽（A/E 0.87/0.94/0.90。先行して持続力を活かせないと割引）")
            except (ValueError, TypeError):
                pass
        if su == "芝" and h.sire == "ルーラーシップ":
            if r1_ == "延長" and prr >= 7:
                why.append("芝の延長×父ルーラーシップ×7番人気以下 ○（A/E 1.07/1.05/1.10）")
            if r1_ == "短縮" and pv_ and d == pv_["distance"] - 200:
                why.append("芝の200m短縮×父ルーラーシップ ○（A/E 1.17/1.36/1.08。少しの短縮なら走る）")
        if h.sire == "ロードカナロア":
            if su == "ダ" and r1_ in ("同距離", "短縮") and prr >= 7:
                why.append(f"ダートの{r1_}×父ロードカナロア×7番人気以下 ◎（A/E {'1.40/1.17/1.23' if r1_ == '同距離' else '1.42/1.52/1.32'}）")
            if su == "芝" and r1_ == "短縮":
                sm = [x for x in rec if x.get("surface") == "芝" and x.get("distance")]
                if any(sm[i]["distance"] <= sm[i + 1]["distance"] - 200 for i in range(len(sm) - 1)):
                    why.append("芝の2回目以降の短縮×父ロードカナロア ◎（A/E 1.11/1.25/1.13。双馬『初めての短縮は苦手・経験すると対応』。初めては1.11/0.87/1.51で不安定）")
                if h.damsire_line in SS_LINES_ALL:
                    why.append("芝の短縮×父ロードカナロア×母父サンデー系 ◎（A/E 1.17/1.17/1.50）")
            if su == "芝" and r1_ == "延長" and prr >= 7:
                why.append("芝の延長×父ロードカナロア×7番人気以下 ▽（A/E 0.94/0.61/0.81）")
        # ペースが緩む瞬発力勝負（スロー予想＝前走で前にいた馬0-1頭）で走るか（tools/pace_adj_check.py, 上がりの速さはペース補正して確認）
        if su == "芝" and 1600 <= d <= 1800 and h.sire_line == "ディープインパクト系" and nfront is not None:
            if nfront <= 1:
                why.append(f"芝1600-1800×父ディープ系×スロー予想（前に行く馬{nfront}頭）○（A/E 後継1.13/1.10/1.06・ディープ本人1.05/1.25/1.69。双馬『ペースが緩む瞬発力勝負』のとおり）")
            elif nfront >= 4:
                why.append(f"芝1600-1800×父ディープ系×消耗戦予想（前に行く馬{nfront}頭）×（A/E 後継0.72/0.65/0.84）")
        if su == "芝" and h.sire == "ディープインパクト" and male and (e.get("age") or 0) >= 4 and dct == "米国型":
            bw = e.get("body_weight") or (rec[0].get("body_weight") if rec else None)
            if bw and bw < 500:
                why.append("芝×父ディープ×牡4歳以上×母父米国型×500kg未満 ○（A/E 1.07/1.39/1.42。双馬『母父米国型の牡は古馬で劣化』は500kg未満では当たらない）")
        if su == "芝" and h.sire_line == "キングカメハメハ系" and h.sire != "キングカメハメハ" and dct == "米国型":
            if co == "東京":
                why.append("東京芝×父キンカメ系後継×母父米国型 ○（A/E 1.11/1.07/1.17）")
            if fast_turf_day(card):
                why.append("芝の高速日（当日・前日の同場が速い）×父キンカメ系後継×母父米国型 ×（A/E 0.74/0.89/0.80。双馬『キンカメは高速馬場向き』は母父米国型では逆）")
        # 双馬 第1章 p36-42 テン3Fの前走比・芝スタートの例外（tools/souma_ten3f.py）
        tg = ten3f_gap(card, prv)
        if tg is not None:
            pr_ = h.pop_rank or 0
            if su == "ダ" and abs(tg) < 0.5 and pr_ >= 7:
                why.append(f"ダート・予想テン3Fが前走と同程度（{tg:+.1f}秒）×7番人気以下 ○（A/E 1.11/1.13/1.09）")
            if su == "芝" and tg <= -2 and 4 <= pr_ <= 6:
                why.append(f"芝・予想テン3Fが前走より2秒以上速い（{tg:+.1f}秒）×4-6番人気 ○（A/E 1.08/1.07/1.10）")
            if su == "芝" and tg >= 2 and pr_ >= 7:
                why.append(f"芝・予想テン3Fが前走より2秒以上遅い（{tg:+.1f}秒）×7番人気以下 ×（A/E 0.62/0.83/0.78。双馬『テンが遅くなると楽』と逆）")
        if su == "ダ" and prv and prv.get("surface") == "ダ" and prv.get("distance") and d >= prv["distance"] + 200 \
                and (prv.get("course"), prv["distance"]) in TURF_START_DIRT and (co, d) not in TURF_START_DIRT:
            why.append("前走芝スタートのダート→今回ダートスタートで延長 ▽（A/E 0.92/0.85/0.91）")
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


def course_check_horses(card: dict, evals: list[HorseEval]) -> list[tuple[int, str]]:
    """data/knowledge/course_sire_flags.json（tools/course_sire_check.py）の3期間一貫した組に当てはまる馬."""
    import json
    from .config import KNOWLEDGE_DIR
    from .knowledge import country_type
    try:
        kb = json.loads((KNOWLEDGE_DIR / "course_sire_flags.json").read_text(encoding="utf-8"))["specs"]
    except (OSError, ValueError, KeyError):
        return []
    co, su, d = card.get("course"), card.get("surface"), card.get("distance")
    specs = [(sp, v) for sp, v in kb.items() if sp.split("|")[0] == co and sp.split("|")[1] == su
             and (not sp.split("|")[2] or str(d) in sp.split("|")[2].split(","))]
    if not specs:
        return []
    m = int(str(card.get("date") or "2026-01-01")[5:7])
    season = "1-2月" if m <= 2 else "3-6月" if m <= 6 else "7-8月" if m <= 8 else "9-12月"
    dv = turf_day_dev(card, su)
    ds_ = None if dv is None else "高速日" if dv <= -0.5 else "時計がかかる日" if dv >= 0.5 else "平均的な日"
    ent = {e.get("number"): e for e in card.get("entries") or []}
    out = []
    for h in evals:
        e = ent.get(h.number, {})
        pb = "1-3番人気" if (h.pop_rank or 99) <= 3 else "4番人気以下"
        g = e.get("gate") or 0
        gb = "1-3枠" if g <= 3 else "4-6枠" if g <= 6 else "7-8枠"
        age = e.get("age") or 9
        sex = "牝" if str(e.get("sex") or "").startswith("牝") else "牡セ"
        fl = PED5_FLAGS().get(e.get("horse_id") or "", [])
        st = country_type(h.sire_line) if h.sire_line else None
        keys = set()
        if h.sire:
            keys |= {("①父×人気", h.sire, pb), ("①父", h.sire, "全体"), ("②父×性別", h.sire, sex),
                     ("③父×年齢", h.sire, "2-3歳" if age <= 3 else "4歳" if age == 4 else "5歳以上")}
        if h.damsire:
            keys.add(("④母父", h.damsire, "全体"))
        if h.damsire_line:
            keys.add(("④母父系統", h.damsire_line, "全体"))
        if h.sire:
            keys.add(("⑨クラス×父", h.sire, "OP以上" if card.get("grade") in ("OP", "L", "G3", "G2", "G1") else "条件戦"))
        keys |= {("⑤5代の祖先", f, "全体") for f in fl}
        if st:
            keys.add(("⑥時期×父の国別タイプ", f"{season}・父{st}", "全体"))
        if "サドラーズウェルズ/ミルリーフ" in fl:
            keys.add(("⑥時期×5代にサドラーズ/ミルリーフ", season, "全体"))
        rec = (e.get("recent") or [None])[0]
        try:
            pz = int(str(rec.get("passing")).split("-")[0]) / max(rec.get("n_runners") or 16, 1)
            keys.add(("⑦前走の位置取り×枠", f"{'前15%' if pz <= 0.15 else '後方40%' if pz > 0.6 else '中団'}・{gb}", "全体"))
        except (AttributeError, ValueError, TypeError):
            pass
        if ds_ and g:
            keys.add(("⑧当日の時計×枠", f"{ds_}・{gb}", "全体"))
        why = []
        for sp, v in specs:
            where = f"{co}{su}{sp.split('|')[2] or '全体'}"
            for r in v["rows"]:
                if tuple(r["k"]) in keys:
                    k = r["k"]
                    why.append(f"{where}・{k[0][1:]}={k[1]}{'' if k[2] == '全体' else '×' + k[2]} {r['mark']}（A/E {'/'.join(f'{x:.2f}' for x in r['ae'])}）")
        if why:
            out.append((h.number, "、".join(why)))
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


def flag_scores(card: dict, evals: list[HorseEval]) -> dict:
    """馬番 → フラグ点（○◎の数 − ×▽▼の数。book_condition_horses・pace_l3_horses・course_check_horses。tools/flag_backtest.py）."""
    import re
    txt = {}
    for f in (book_condition_horses, pace_l3_horses, course_check_horses):
        try:
            for num, t in f(card, evals):
                txt[num] = txt.get(num, "") + " " + t
        except Exception:  # noqa: BLE001 — 1つの材料の失敗で予想を止めない
            pass
    return {h.number: len(re.findall(r"[◎○]（", txt.get(h.number, ""))) - len(re.findall(r"[×▽▼]（", txt.get(h.number, ""))) for h in evals}


def flag_picks(card: dict, evals: list[HorseEval]) -> list[str]:
    """フラグ点の買い目（tools/flag_strategy.py, 2021-23/2024/2025-26 の3期間とも回収率100%超の組。フラグ選定期間内の確認なので今後の週で検証）."""
    sc = flag_scores(card, evals)
    pop = {h.number: h.pop_rank for h in evals if h.pop_rank}
    nm = {h.number: h.name for h in evals}
    out = []
    one = [n for n, p in pop.items() if p == 1]
    if one and sc.get(one[0], 0) <= -2:
        cand = sorted([n for n, p in pop.items() if 2 <= p <= 6 and sc.get(n, 0) >= 1], key=lambda n: (-sc[n], pop[n]))
        if cand and sc[cand[0]] >= 2:
            ax = cand[0]
            wide = [n for n in cand[1:5]]
            out.append(f"**★フラグ点: 1番人気{one[0]}{nm[one[0]]}が点{sc[one[0]]:+d}（過信禁物）** → "
                       f"単勝 {'・'.join(f'{n}{nm[n]}' for n in cand if sc[n] >= 2)}（2-6番人気で+2以上。検証 単勝115/113/140%・複勝94/100/104%）"
                       + (f"、ワイド {ax}-{'・'.join(map(str, wide))}（検証 ワイド133/137/195%・的中率17〜23%）" if wide else ""))
    for n, p in sorted(pop.items(), key=lambda x: x[1]):
        if 4 <= p <= 6 and sc.get(n, 0) >= 3:
            out.append(f"**★フラグ点: {n}{nm[n]}（{p}番人気・点{sc[n]:+d}）** → 単勝・複勝（4-6番人気で+3以上。検証 単勝103/115/103%・複勝101/104/99%・3着内率約38%）")
    return out


def g1_history_lines(card: dict, evals: list[HorseEval]) -> list[str]:
    """G1 は必ず予想する（2026-10-15 ユーザー指示）。DB 内の同名 G1 の過去の1〜3着の傾向（前走のレース・クラス・人気帯・父系統）と、各出走馬の当てはまり（tools/g1_history.py）."""
    import re
    import sqlite3
    from collections import defaultdict
    from .config import DB_PATH
    if card.get("grade") != "G1":
        return []
    nm0 = card.get("name") or ""
    key = re.sub(r"^第\d+回|\(.*?\)|（.*?）|GI+|Ｇ.*$", "", nm0).strip()[:4]
    if key.startswith("天皇賞"):
        key = "天皇賞(秋)" if "秋" in nm0 or str(card.get("date", ""))[5:7] >= "09" else "天皇賞(春)"
    if not key:
        return []
    try:
        with sqlite3.connect(DB_PATH) as c:
            base = defaultdict(lambda: [0, 0])
            for p, f in c.execute("select popularity, finish from results where finish is not null and popularity is not null"):
                b = base[min(p, 14)]; b[0] += 1; b[1] += f <= 3
            exp = {p: v[1] / v[0] for p, v in base.items()}
            agg = defaultdict(lambda: [0, 0, 0.0])
            yrs = []
            for rid, date in c.execute("select race_id, date from races where grade='G1' and name like ? and date < ? order by date", (f"%{key}%", card.get("date") or "9999")):
                yrs.append(date[:4])
                for hid, fin, pop, sl in c.execute("select r.horse_id,r.finish,r.popularity,h.sire_line from results r left join horses h using(horse_id) "
                                                   "where r.race_id=? and r.finish is not null and r.popularity is not null", (rid,)):
                    pv = c.execute("select ra.name, ra.grade from results x join races ra using(race_id) where x.horse_id=? and ra.date<? order by ra.date desc limit 1",
                                   (hid, date)).fetchone()
                    for k in (("前走", pv[0] if pv else "DBになし"), ("前走クラス", (pv[1] or "条件戦") if pv else "DBになし"),
                              ("人気", "1-3番人気" if pop <= 3 else "4-6番人気" if pop <= 6 else "7番人気以下"), ("父系統", sl)):
                        a = agg[k]; a[0] += 1; a[1] += fin <= 3; a[2] += exp[min(pop, 14)]
    except sqlite3.Error:
        return []
    if not yrs:
        return [f"**G1 {card.get('name')}**: DB に過去の同名G1なし（傾向は WebSearch で補う）"]
    L = [f"**G1 {card.get('name')} 過去{len(yrs)}回（{yrs[0]}〜{yrs[-1]}）の1〜3着の傾向**（3着内/頭数・A/E。回数が少ないので参考）"]
    top = sorted([(k, a) for k, a in agg.items() if a[1] >= 2 or (a[0] >= 10 and a[1] == 0)], key=lambda x: -x[1][1])[:10]
    L.append("  - " + "、".join(f"{k[0]}={k[1]} {a[1]}/{a[0]}（{a[1] / a[2]:.2f}）" for k, a in top))
    ent = {e.get("number"): e for e in card.get("entries") or []}
    for h in sorted(evals, key=lambda h: h.pop_rank or 99):
        e = ent.get(h.number, {}); rec = (e.get("recent") or [None])[0] or {}
        pvn, pvg = "DBになし", "DBになし"
        if rec.get("race_id"):
            try:
                with sqlite3.connect(DB_PATH) as c:
                    row = c.execute("select name, grade from races where race_id=?", (str(rec["race_id"]),)).fetchone()
                if row:
                    pvn, pvg = row[0], row[1] or "条件戦"
            except sqlite3.Error:
                pass
        ks = [("前走", pvn), ("前走クラス", pvg), ("人気", "1-3番人気" if (h.pop_rank or 99) <= 3 else "4-6番人気" if (h.pop_rank or 99) <= 6 else "7番人気以下"),
              ("父系統", h.sire_line)]
        hit = [f"{k[1]} {agg[k][1]}/{agg[k][0]}" for k in ks if k in agg and agg[k][0] >= 3]
        L.append(f"  - {h.number}{h.name}（{h.pop_rank}人気）前走 {rec.get('race_name', '?')} {rec.get('finish', '?')}着: " + ("、".join(hit) or "過去の該当なし"))
    return L


def text(card: dict, evals: list[HorseEval], title: str) -> str:
    sc_ = flag_scores(card, evals)
    d = race_digest(evals, sc_)
    L = [f"### {title}"]
    L += g1_history_lines(card, evals)
    L += flag_picks(card, evals)
    if any(sc_.values()):
        L.append("フラグ点（○−×）: " + "、".join(f"{h.number}{h.name}({h.pop_rank}人気){sc_[h.number]:+d}"
                                              for h in sorted(evals, key=lambda h: h.pop_rank or 99) if sc_.get(h.number)))
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
              "妙味条件": "回収率の高い条件に該当", "牝系": "牝系がこの条件で走る", "危険": "過信禁物の人気馬（1〜3番人気。2021-26年の検証で、どんな条件の組み合わせでも1番人気は半分以上3着内に来る＝馬券から消してはいけない。同じ人気の平均より3着内率が5〜10ポイント低いだけなので、軸・1着付けにしない。3連複・ワイドのヒモには残す）"}
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
    pl3 = pace_l3_horses(card, evals)
    if pl3:
        L.append("- 展開×上がり能力（展開予想と近3走の上がり順位・位置取り。3期間とも人気以上○/以下×）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(pl3, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
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
    cc = course_check_horses(card, evals)
    if cc:
        L.append("- コース別の種牡馬・血統・枠（コース別種牡馬本の主張を検証し、3期間とも一貫した組。tools/course_sire_check.py）:")
        nm = {h.number: h for h in evals}
        for num, txt in sorted(cc, key=lambda x: (nm[x[0]].pop_rank or 99) if x[0] in nm else 99):
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
| 過信禁物の人気馬 | — | 消しではない（1番人気は半分以上3着内）。軸・1着付けにしない。ヒモには残す | — |
"""

