"""週次予想レポート(predictions/YYYY-MM-DD/README.md)の生成と、レース選定."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import knowledge as K
from .betting import BetPlan, build_plan, value_plan
from .config import MAX_RACES_PER_WEEK, PREDICTIONS_DIR, distance_band, is_target_race
from .model import AXIS_JA, HorseEval, evaluate_race

WEEKDAY_JA = "月火水木金土日"
GRADE_BONUS = {"G1": 0.06, "G2": 0.04, "G3": 0.03, "L": 0.01, "OP": 0.01}


def race_confidence(evals: list[HorseEval], plan: BetPlan, card: dict) -> float:
    """推奨度: 推奨買い目の推定的中率 + 本命の勝率 + 血統情報の充足度 + 重賞ボーナス."""
    coverage = sum(1 for h in evals if h.sire) / max(len(evals), 1)
    edge = 0.0
    for h in evals[:3]:
        if h.p_market:
            edge = max(edge, h.p_win / h.p_market - 1)
    return (0.5 * plan.p_any_hit + 0.4 * evals[0].p_win + 0.1 * coverage
            + 0.1 * min(edge, 1.0) + GRADE_BONUS.get(card.get("grade") or "", 0))


def analyze_cards(cards: list[dict], st=None, conn=None) -> list[dict]:
    out = []
    for c in cards:
        if not c.get("entries") or len(c["entries"]) < 5:
            continue
        if not is_target_race(c.get("race_no"), c.get("grade"), c.get("surface"), c.get("name")):
            continue   # 第6レース以前・未勝利戦・障害は対象外
        evals = evaluate_race(c, st, conn)
        plan = build_plan(evals)
        vplan = value_plan(evals, len(c["entries"]))
        out.append({"card": c, "evals": evals, "plan": plan, "vplan": vplan, "conf": race_confidence(evals, plan, c)})
    return out


def select_races(analyzed: list[dict], k: int | None = None) -> list[dict]:
    """推奨レース = 本線（妙味馬の単複＋馬連）が成立するレース全部（レース数は固定しない。k を指定すればその数まで）."""
    sel = [a for a in analyzed if a.get("vplan")]
    if not sel:   # 前売りオッズが無い（妙味馬を判定できない）ときは、従来の推奨度で上位5レースを暫定表示
        return sorted(analyzed, key=lambda a: -a["conf"])[:k or MAX_RACES_PER_WEEK]
    sel.sort(key=lambda a: (a["card"].get("date") or "", a["card"].get("course") or "", a["card"].get("race_no") or 0))
    return sel[:k] if k else sel


def _date_ja(s: str) -> str:
    d = dt.date.fromisoformat(s)
    return f"{d.month}/{d.day}({WEEKDAY_JA[d.weekday()]})"


def race_title(c: dict) -> str:
    g = f"({c['grade']})" if c.get("grade") in ("G1", "G2", "G3", "L") else ""
    return (f"{_date_ja(c['date'])} {c.get('course','')}{c.get('race_no','')}R {c.get('name','')}{g} "
            f"{c.get('surface','')}{c.get('distance','')}m")


def race_section(a: dict, idx: int) -> str:
    c, evals, plan = a["card"], a["evals"], a["plan"]
    band = distance_band(c.get("distance") or 1600)
    course = K.courses()["courses"].get(c.get("course") or "", {})
    cinfo = course.get("turf" if c.get("surface") == "芝" else "dirt", {})
    cd_note = K.courses()["course_distance_notes"].get(f"{c.get('course')}{c.get('surface')}{c.get('distance')}")
    L = [f"## {idx}. {race_title(c)}", ""]
    if c.get("provisional_numbers"):
        L.append("- ⚠️ **枠順未確定**: 馬番は出馬表の掲載順の仮番号です。買い目は馬名で確認してください（枠順確定後に作り直します）")
    L.append(f"- 想定馬場: {c.get('going') or '良(想定)'}　推奨度スコア: {a['conf']:.3f}")
    if cinfo.get("feature"):
        L.append(f"- コース特性: {cinfo['feature']}")
    if cd_note:
        L.append(f"- 条件メモ: {cd_note}")
    dem = sorted(cinfo.get("demand", {}).items(), key=lambda x: -x[1])
    if dem:
        L.append("- 求められる血統適性: " + "、".join(f"{AXIS_JA[k]}" for k, v in dem if v > 0)
                 + f"、{AXIS_JA[band]}")
    fc = c.get("_forecast")
    if fc:
        exp = c.get("expected_pace")
        L += ["", "### 展開予想", "",
              f"- 予想ペース: **{fc.pace}**（ラップ型: {exp or fc.pace_type}戦）",
              f"- {fc.note}",
              "- 逃げ候補: " + ("、".join(f"{n}番{nm}" for n, nm in fc.nige) or "不在（スロー濃厚）"),
              "- 先行勢: " + ("、".join(f"{n}番{nm}" for n, nm in fc.senko[:6]) or "-")]
        fav = {"消耗": "差し・追込", "持続": "先行〜好位差し", "瞬発": "逃げ・先行＋上がり最速級", "平均": "先行・好位"}
        L.append(f"- 展開上有利な脚質: {fav.get(exp or fc.pace_type, '-')}")
    L += ["", "| 印 | 馬番 | 馬名 | 父(系統) | 母父(系統) | 脚質 | 距離 | 騎手 | 単勝 | 予測勝率 | 予測複勝率 |",
          "|:-:|--:|---|---|---|:-:|:-:|---|--:|--:|--:|"]
    for h in evals:
        mk = plan.marks.get(h.number, "")
        odds = f"{h.odds:.1f}" if h.odds else "-"
        L.append(f"| {mk} | {h.number or '-'} | {h.name} | {h.sire or '?'}（{h.sire_line}） | "
                 f"{h.damsire or '?'}（{h.damsire_line}） | {h.style or '-'} | {h.dist_change} | {h.jockey or '-'} | {odds} | "
                 f"{h.p_win:.1%} | {h.p_top3:.1%} |")
    L += ["", "### 血統的根拠（印上位）", ""]
    for h in evals:
        mk = plan.marks.get(h.number)
        if not mk:
            continue
        L.append(f"**{mk} {h.number} {h.name}**（予測勝率 {h.p_win:.1%}）")
        for e in h.evidence:
            L.append(f"- {e}")
        comp = "、".join(f"{k}:{v:+.2f}" for k, v in sorted(h.components.items(), key=lambda x: -abs(x[1])))
        L.append(f"- スコア内訳: {comp}")
        L.append("")
    # 望田潤氏の見方（当てはまる見解を、モデルの数字とは別に一覧で）
    mochi = [(h, e) for h in evals for e in h.evidence if "望田" in e]
    if mochi:
        L += ["### 望田潤氏の見方（この条件に当てはまる血統評価）", ""]
        for h, e in mochi[:8]:
            L.append(f"- {h.number} {h.name}: {e.split(']: ', 1)[-1]}")
        L.append("")
    from .model import BLOOD_COMPS
    from .validate import GROUP_JA
    ana = [h for h in evals if plan.marks.get(h.number) == "★"]
    if ana:
        L += ["### ★ 血統の穴（8番人気以下で血統要素が高い馬。複勝でも押さえる）", ""]
        for h in ana:
            parts = sorted(((k, v) for k, v in h.components.items() if k in BLOOD_COMPS and v > 0), key=lambda x: -x[1])[:4]
            L.append(f"- {h.number} {h.name}（{h.pop_rank}番{'評価（前売り前のためモデルの評価順）' if h.pop_estimated else '人気'}"
                     f"・単勝{h.odds or '-'}倍・父{h.sire or '?'}・母父{h.damsire or '?'}）: 血統要素の合計 {h.blood_upside:+.2f}"
                     f"（{'、'.join(f'{GROUP_JA.get(k, k)}{v:+.2f}' for k, v in parts)}）")
        L += ["- 検証: 8番人気以下で血統要素が最大の馬は3着内率が人気薄全体の1.18〜1.28倍（2024・2025〜）。"
              "複勝回収は70〜74%で人気薄全体（67%）より上だが100%未満。", ""]
    # 全頭の血統評価（考察文・★評価・距離/スピード/底力/コース）
    from . import commentary as CM
    from .db import connect as _connect
    try:
        _conn = _connect()
    except Exception:   # noqa: BLE001
        _conn = None
    G = CM.grades(evals, c, _conn)
    ents = {e.get("number"): e for e in c.get("entries", [])}
    L += ["### 血統評価（全頭）", "", "| 馬番 | 馬名 | 評価 | 距離 | スピード | 底力 | コース |", "|--:|---|:-:|:-:|:-:|:-:|:-:|"]
    for h in evals:
        g = G[h.number]
        L.append(f"| {h.number} | {h.name} | {'★' * int(g['評価'])}{'☆' if g['評価'] % 1 else ''} {g['評価']:.1f} | "
                 f"{g['距離']} | {g['スピード']} | {g['底力']} | {g['コース']} |")
    L.append("")
    for h in evals:
        try:
            txt = CM.write(_conn, c, ents.get(h.number, {}), h)
        except Exception as e:   # noqa: BLE001
            txt = f"（考察の生成に失敗: {e}）"
        L.append(f"- **{h.number} {h.name}**（{G[h.number]['評価']:.1f}）: {txt}")
    L.append("")
    danger = [h for h in evals if h.pop_band in ("1-3番人気", "4-6番人気") and h.cond_score <= -0.3]
    if danger:
        L += ["### 危険な人気馬（人気帯の平均より来ない条件が重なる）", ""]
        for h in danger:
            why = next((e for e in h.evidence if "来ない条件" in e), "")
            L.append(f"- {h.number} {h.name}（{h.pop_band}・予測勝率{h.p_win:.1%}）: {why}")
        L.append("")
    nm = {h.number: h.name for h in evals}
    vp = a.get("vplan")
    if vp:
        L += [f"### 本線の買い目（{len(vp.tickets)}点）", "", f"- {vp.strategy}",
              "- 検証（過去1年）: 妙味馬の単複は回収率117%・的中24%。妙味馬を含む馬連（期待値1.2倍以上・想定2000円以上・14頭以下）は回収率130%前後・的中10%前後（docs/analysis/strategy.md）",
              f"- 推定的中率（いずれか的中）: {vp.p_any_hit:.1%}", "",
              "| 券種 | 買い目 | 推定的中率 | 想定配当 |", "|---|---|--:|--:|"]
        for t in vp.tickets:
            lab = "-".join(str(x) for x in t.horses) + "（" + "・".join(nm.get(x, "?") for x in t.horses) + "）"
            est = f"{getattr(t, 'est_pay', 0):,.0f}円" if getattr(t, "est_pay", 0) else "-"
            L.append(f"| {t.kind} | {lab} | {t.p_hit:.1%} | {est} |")
        L.append("")
    L += ["### 参考: ◎軸の買い目（" + f"{len(plan.tickets)}点。検証では回収率70〜84%で負け越し）", "", f"- 戦略: {plan.strategy}",
          f"- 推定的中率（いずれか的中）: {plan.p_any_hit:.1%}", "",
          "| 券種 | 買い目 | 推定的中率 |", "|---|---|--:|"]
    for t in plan.tickets:
        lab = "-".join(str(x) for x in t.horses)
        if c.get("provisional_numbers"):   # 仮番号のときは馬名も
            lab += "（" + "・".join(nm.get(x, "?") for x in t.horses) + "）"
        L.append(f"| {t.kind} | {lab} | {t.p_hit:.1%} |")
    L.append("")
    # DBが拾った材料を持つ馬を全部（本線＝妙味馬の単複・★・専門家の見解・走る条件・妙味条件・牝系・危険）
    from . import digest
    L += ["#### 注目馬一覧（本線は妙味馬の単複。ほかはDBの材料。買うかは自分で選ぶ）", "",
          digest.text(c, evals, "").split("\n", 1)[1], ""]
    return "\n".join(L)


def write_week_report(analyzed_selected: list[dict], sat: dt.date, n_candidates: int,
                      st=None, out_dir: Path = PREDICTIONS_DIR, notes: list[str] | None = None,
                      graded: list[dict] | None = None) -> Path:
    folder = out_dir / sat.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    sun = sat + dt.timedelta(days=1)
    L = [f"# {sat.year}年 {_date_ja(sat.isoformat())}・{_date_ja(sun.isoformat())} 血統予想", "",
         f"- 生成日時: {dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')} JST",
         f"- 分析対象: {n_candidates}レース → 推奨 {len(analyzed_selected)}レース（本線＝妙味馬の単複＋馬連が成立するレース。レース数は固定しない）",
         f"- 血統DB: 実績 {st.n_races if st else 0} レース集計済み ＋ 血統ナレッジ（data/knowledge）",
         ""]
    for n in notes or []:
        L.append(f"> {n}")
    if notes:
        L.append("")
    L += ["## 今週の推奨レース一覧（本線＝妙味馬の単複＋馬連）", "", "| # | レース | 妙味馬 | 人気・単勝 | 予測勝率 | 買い目 | 推定的中率 |",
          "|--:|---|---|---|--:|---|--:|"]
    if analyzed_selected and not analyzed_selected[0].get("vplan"):
        L.insert(-3, "> 前売りオッズが無いため妙味馬を判定できません。暫定で推奨度の高いレースを表示しています（オッズ公開後に作り直します）。")
    for i, a in enumerate(analyzed_selected, 1):
        vp = a.get("vplan")
        if not vp:
            h = a["evals"][0]
            L.append(f"| {i} | {race_title(a['card'])} | （◎{h.number} {h.name}） | - | {h.p_win:.1%} | 参考: ◎軸 | {a['plan'].p_any_hit:.1%} |")
            continue
        v = next(h for h in a["evals"] if h.number == vp.tickets[0].horses[0])
        n_um = sum(t.kind == "馬連" for t in vp.tickets)
        L.append(f"| {i} | {race_title(a['card'])} | {v.number} {v.name} | {v.pop_rank}人気・{v.odds or '-'}倍 | "
                 f"{v.p_win:.1%} | 単複{'＋馬連' + str(n_um) + '点' if n_um else ''} | {vp.p_any_hit:.1%} |")
    L.append("")
    for i, a in enumerate(analyzed_selected, 1):
        L.append(race_section(a, i))
    # 推奨に入らなかった重賞も、印と★ 血統の穴は必ず載せる（買うかは任意。推奨の集計には含めない）
    graded = sorted(graded or [], key=lambda a: (a["card"].get("date") or "", a["card"].get("race_no") or 0))
    if graded:
        L += ["## 重賞（推奨外・印と★ 血統の穴の参考）", "",
              "推奨基準には届かなかったが、重賞は印と血統の穴を必ず示す。買い目は参考。", ""]
        for i, a in enumerate(graded, len(analyzed_selected) + 1):
            L.append(race_section(a, i).replace("## ", "## 【参考】", 1))
    L += ["---", "", "### 注意事項", "",
          "- 予測勝率は血統適性・実績集計・近走・人的要因（騎手/調教師）・オッズ（取得時）を統合したモデル推定値であり、的中を保証するものではありません。",
          "- 馬場状態・枠順・当日オッズで評価は変わります。当日の馬場発表と馬体重を必ず確認してください。",
          "- 馬券の購入は20歳以上・自己責任で、無理のない範囲でお楽しみください。", ""]
    p = folder / "README.md"
    p.write_text("\n".join(L), encoding="utf-8")
    picks = [{
        "race_id": a["card"].get("race_id"), "title": race_title(a["card"]),
        "ranking": [{"number": h.number, "name": h.name, "p_win": round(h.p_win, 4),
                     "p_top3": round(h.p_top3, 4)} for h in a["evals"]],
        "tickets": [{"kind": t.kind, "horses": list(t.horses), "p_hit": round(t.p_hit, 4)}
                    for t in (a["vplan"] or a["plan"]).tickets],
    } for a in analyzed_selected]
    for a in graded:
        picks.append({"race_id": a["card"].get("race_id"), "title": race_title(a["card"]), "reference": True,
                      "ranking": [{"number": h.number, "name": h.name, "p_win": round(h.p_win, 4)} for h in a["evals"]],
                      "tickets": [{"kind": t.kind, "horses": list(t.horses), "p_hit": round(t.p_hit, 4)}
                                  for t in a["plan"].tickets]})
    (folder / "picks.json").write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    _update_index(out_dir)
    return p


def _update_index(out_dir: Path):
    weeks = sorted([d.name for d in out_dir.iterdir() if d.is_dir()], reverse=True)
    L = ["# 週次 血統予想アーカイブ", "", "| 週 | 予想 | 結果検証 |", "|---|---|---|"]
    for w in weeks:
        rev = "[検証](%s/review.md)" % w if (out_dir / w / "review.md").exists() else "-"
        L.append(f"| {w} | [予想]({w}/README.md) | {rev} |")
    (out_dir / "README.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def review_week(conn, sat: dt.date, out_dir: Path = PREDICTIONS_DIR) -> Path | None:
    """レース後の検証: 推奨買い目の的中・払戻・回収率を集計して review.md に書く."""
    folder = out_dir / sat.isoformat()
    pj = folder / "picks.json"
    if not pj.exists():
        return None
    picks = json.loads(pj.read_text(encoding="utf-8"))
    L = [f"# {sat.isoformat()} 週 予想検証", "", "| レース | 1-2-3着 | ◎着順 | 的中券種 | 払戻 | 投資 |", "|---|---|---|---|--:|--:|"]
    tot_in = tot_out = 0
    for p in picks:
        rid = p.get("race_id")
        race = conn.execute("SELECT * FROM races WHERE race_id=?", (rid,)).fetchone() if rid else None
        if not race:
            L.append(f"| {p['title']} | 未取得 | - | - | - | - |")
            continue
        res = conn.execute("SELECT number, finish FROM results WHERE race_id=? AND finish IS NOT NULL ORDER BY finish",
                           (rid,)).fetchall()
        order = [r["number"] for r in res[:3]]
        fin = {r["number"]: r["finish"] for r in res}
        pay = json.loads(race["payouts"] or "{}")
        hits, ret = [], 0
        for t in p["tickets"]:
            key = {"単勝": "単勝", "複勝": "複勝", "馬連": "馬連", "ワイド": "ワイド", "三連複": "3連複"}[t["kind"]]
            combo_sorted = "-".join(str(x) for x in sorted(t["horses"]))
            for c, yen in pay.get(key, []) + pay.get(t["kind"], []):
                nums = sorted(int(x) for x in c.replace("→", "-").split("-") if x.strip().isdigit())
                if "-".join(map(str, nums)) == combo_sorted:
                    hits.append(f"{t['kind']} {combo_sorted}")
                    ret += yen or 0
        invest = 100 * len(p["tickets"])
        if not p.get("reference"):   # 参考掲載の重賞は合計に含めない
            tot_in += invest
            tot_out += ret
        top = p["ranking"][0]["number"]
        L.append(f"| {p['title']}{'（参考）' if p.get('reference') else ''} | {'-'.join(map(str, order))} | {fin.get(top, '-')} | "
                 f"{'、'.join(hits) or 'なし'} | {ret} | {invest} |")
    L += ["", f"**合計: 投資 {tot_in}円 / 払戻 {tot_out}円 / 回収率 {tot_out / tot_in:.0%}**" if tot_in else "", ""]
    out = folder / "review.md"
    out.write_text("\n".join(L), encoding="utf-8")
    _update_index(out_dir)
    return out
