"""1〜6R・新馬・未勝利のおすすめ（2026-11-12 ユーザー「下級条件や未勝利・新馬のほうが血統の影響がありそう。7レースより前も、血統やフラグでおすすめのレース・馬を出して」）.
cards_early/<日付>/（python -m keiba.cli build-cards --early）の各レースで、tools/flag_backtest.py と同じ材料（book_condition_horses・pace_l3_horses・course_check_horses）
のフラグ点（○◎の数 − ×▽▼の数）を出し、
  ★未勝利の単勝: 未勝利戦でフラグ点が一番高い馬（+5以上）の単勝100円。
    全レースDBで材料を2021-24だけで選んだフラグの確かめ（EARLY=1 FB_DB=data/keiba_all.db … flag_backtest.py 2025-01-01 2026-11-08）で
    2025 回収122%（804レース）・2026 122%（649レース）。+4以上 112/118%、+6以上 125/112% と区切りをずらしても100%超。
  新馬・1〜6Rの1勝クラスは年でぶれる（新馬 +5: 61/73%、1勝 +5: 67/58%）ので参考（フラグ点の上位だけ出す）。ワイド・3連複は100%前後で安定しないので出さない。
  ★7・8Rの穴馬（2026-11-12 ユーザー「7R・8Rもおすすめのレースと穴馬だけ。全部出すのは9R以降」）: cards/<日付>/ の7R・8Rで、単勝10〜50倍・フラグ点+5以上の馬の単勝100円（全部）。
    材料を2021-24だけで選んだフラグの7R以降の確かめ（flag_backtest_rows_oos2）で 2025年111%（389点）・2026年145%（312点）。+6 120/162%・+7 116/170%・+8 120/126% と区切りをずらしても100%超
    （50倍以上まで入れると2025年が93%に下がる）。7・8Rの本線の単勝は【今日買うもの】（tools/race_sheet.py）に残る。
使い方: python3 tools/early_picks.py <土曜の日付> → predictions/<土曜>/early.md
"""
import datetime as dt, json, re, sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# 1〜8Rの券は、全レースDBで選んだ多角的な総当たり（multi_angle_scan_all.json）の目盛りで確かめたので、その版で判定する（2026-11-13）
import os  # noqa: E402
if (ROOT / "data" / "knowledge" / "multi_angle_scan_all.json").exists():
    os.environ.setdefault("MULTI_ANGLE_SCAN_FILE", str(ROOT / "data" / "knowledge" / "multi_angle_scan_all.json"))
PLUS, MINUS = re.compile(r"[◎○]（"), re.compile(r"[×▽▼]（")
TH = 5


def kind(c):
    if (c.get("race_no") or 0) in (7, 8) and not any(w in (c.get("name") or "") for w in ("新馬", "未勝利")) and c.get("grade") not in ("新馬", "未勝利"):
        return "7・8R"
    n = c.get("name") or ""
    return "新馬" if c.get("grade") == "新馬" or "新馬" in n else "未勝利" if c.get("grade") == "未勝利" or "未勝利" in n else "1勝以上"


def scores(card):
    from keiba import digest as D
    ents = card["entries"]
    evals = [SimpleNamespace(number=e["number"], name=e.get("name") or str(e["number"]), sire=e.get("sire"), damsire=e.get("damsire"),
                             sire_line=e.get("sire_line") or "", damsire_line=e.get("damsire_line") or "",
                             pop_rank=e.get("popularity"), odds=e.get("odds")) for e in ents]
    txt = defaultdict(str)
    for f in (D.book_condition_horses, D.pace_l3_horses, D.course_check_horses):
        try:
            for num, t in f(card, evals):
                txt[num] += " " + t
        except Exception as ex:  # noqa: BLE001
            print(f"{card['race_id']} {f.__name__}: {ex}", file=sys.stderr)
    return {e["number"]: (len(PLUS.findall(txt[e["number"]])) - len(MINUS.findall(txt[e["number"]])), txt[e["number"]].strip()) for e in ents}


_ST = {}


def notable(card):
    """9R以降の予想と同じ判定（keiba/digest.py の race_digest）で、面白い馬・危険な人気馬を拾う（2026-11-12 ユーザー「8R以前はフラグの高い馬や血統注目馬、走る条件、妙味条件などで面白い馬が入れば出して。危険な人気馬も」）."""
    from keiba import analysis, db, digest
    from keiba.model import evaluate_race
    if "st" not in _ST:
        _ST["conn"] = db.connect(); _ST["st"] = analysis.build_stats(_ST["conn"])
    try:
        ev = evaluate_race(card, _ST["st"], _ST["conn"], n_sims=0)
        d = digest.race_digest(ev, digest.flag_scores(card, ev))
    except Exception as ex:  # noqa: BLE001
        print(f"{card.get('race_id')} race_digest: {ex}", file=sys.stderr)
        return {}, []
    tags = defaultdict(list)
    for cat, lab in (("★", "血統注目"), ("専門家", "専門家"), ("検証済み", "検証済み"), ("走る条件", "走る条件"), ("妙味条件", "妙味条件"), ("牝系", "牝系")):
        for h, why in d.get(cat, []):
            tags[h.number].append(lab + (f"（{why[:60]}）" if why and cat in ("★", "専門家") else ""))
    danger = [(h.number, why) for h, why in d.get("危険", [])]
    return tags, danger


def main(sat):
    s = dt.date.fromisoformat(sat)
    L = [f"# 1〜8R・新馬・未勝利のおすすめ {s}〜{s + dt.timedelta(days=1)}（tools/early_picks.py）", "",
         "- おすすめの馬＝フラグ点（○◎の数 − ×▽▼の数）の上位。◎＝最上位、○▲＝2・3番手（+4以上）。券は材料を2021-24だけで選んだフラグで2025年・2026年を答え合わせして両年100%を超えた形（実際の払戻・均等買い）を買う。",
         "- 未勝利（◎+5以上）: ◎の単勝＋複勝 110%/107%・的中44〜49%（単勝だけなら122%/122%・的中20%、12頭以下は複勝だけでも110%/103%・的中62〜65%）。",
         "- 新馬: ◎（+5以上）→1〜3番人気の馬連 188%/125%・的中20〜28%、ワイド ◎（+4以上）→1番人気 128%/124%・的中18〜20%（どちらもレース数は少なめ）。単勝は負け。",
         "- 7・8R: ワイド ◎（+5以上）→1番人気 102%/162%・的中22%（12頭以下は31〜33%）、+4以上の上位3頭（◎○▲）の馬連ボックス3点 102%/150%・的中11%、穴馬（単勝10〜50倍・+5以上）の単勝 111%/145%。7・8Rの◎厳格・★フラグ軸・本線などは【今日買うもの】の方。",
         "- 1〜6Rの1勝クラスは年でぶれるので馬だけ参考。馬券は自己責任で。", ""]
    recs, notes = [], []
    for d in (s, s + dt.timedelta(days=1)):
        folder = ROOT / "cards_early" / d.isoformat()
        cards = [json.load(open(p)) for p in folder.glob("*.json")]
        cards += [c for c in (json.load(open(p)) for p in (ROOT / "cards" / d.isoformat()).glob("*.json")) if (c.get("race_no") or 0) in (7, 8)]
        cards.sort(key=lambda c: (c.get("course") or "", c.get("race_no") or 0))
        if not cards:
            L += [f"## {d}: 出馬表なし（cards_early/{d}/）", ""]
            continue
        L += [f"## {d}", ""]
        for c in cards:
            sc = scores(c)
            k = kind(c)
            ents = {e["number"]: e for e in c["entries"]}
            rank = sorted(sc.items(), key=lambda kv: (-kv[1][0], ents[kv[0]].get("popularity") or 99))
            top_n, (top_s, _) = rank[0]
            marks = {}
            for m, (n, (v, _)) in zip("◎○▲", rank):
                if v >= 4:
                    marks[n] = m
            nm = lambda n: f"{marks.get(n, '')}{n}{ents[n].get('name') or ''}（+{sc[n][0]}" + (f"・{ents[n]['popularity']}人気" + (f"{ents[n]['odds']}倍" if ents[n].get("odds") else "") + "）" if ents[n].get("popularity") else "）")
            tag = f"{d.strftime('%m/%d')} {c.get('course')}{c.get('race_no')}R（{k}）"
            p3 = [e["number"] for e in sorted(ents.values(), key=lambda e: e.get("popularity") or 99)[:3]] if all(e.get("popularity") for e in ents.values()) else None
            p3s = "・".join(map(str, [x for x in p3 if x != top_n])) if p3 else "1〜3番人気（オッズが入ってから）"
            tk = []
            p1 = (p3[0] if p3[0] != top_n else None) if p3 else "?"   # ◎が1番人気なら1番人気へのワイドは買わない（確かめたときと同じ）
            p1s = "1番人気（オッズが入ってから・◎が1番人気なら買わない）" if p1 == "?" else str(p1)
            if k == "未勝利" and top_s >= TH:
                tk = [f"◎{top_n}の単勝", f"◎{top_n}の複勝"]
            elif k == "新馬" and top_s >= 4:
                if top_s >= TH:
                    tk.append(f"馬連 {top_n}→{p3s}")
                if p1:
                    tk.append(f"ワイド {top_n}-{p1s}")
            if k == "7・8R" and top_s >= TH and p1:
                tk.append(f"ワイド {top_n}-{p1s}")
            if k == "7・8R":
                top3 = [n for n in marks]
                if len(top3) == 3:
                    tk.append("馬連ボックス " + "・".join(map(str, top3)) + "（3点）")
                ana = [n for n, (v, _) in rank if v >= TH and (10 <= (ents[n].get("odds") or 0) < 50 or not ents[n].get("odds"))]
                tk += [f"穴馬 {n}の単勝" + ("" if ents[n].get("odds") else "（10〜50倍なら）") for n in ana]
            tags, danger = notable(c)
            fun = [n for n in ents if (n in tags and sc[n][0] >= -2) or sc[n][0] >= 4]   # フラグ点が大きくマイナスの馬は材料が1つあっても出さない
            fun.sort(key=lambda n: (-sc[n][0] - 2 * len(tags.get(n, [])), ents[n].get("popularity") or 99))
            fun_s = "、".join(f"{marks.get(n, '')}{n}{ents[n].get('name') or ''}（{'+' if sc[n][0] >= 0 else ''}{sc[n][0]}"
                              + (f"・{ents[n]['popularity']}人気" if ents[n].get("popularity") else "")
                              + ("・" + "・".join(t.split("（")[0] for t in tags.get(n, [])) if tags.get(n) else "") + "）" for n in fun[:5])
            dng_s = "、".join(f"{n}{ents[n].get('name') or ''}（{ents[n].get('popularity')}人気）" for n, _ in danger)
            if fun_s or dng_s:
                notes.append(f"{tag}: " + (f"面白い馬 {fun_s}" if fun_s else "") + (f" ／ 危険な人気馬 {dng_s}" if dng_s else ""))
            head = f"### {c.get('course')}{c.get('race_no')}R {c.get('name') or ''}（{k}・{c.get('surface')}{c.get('distance')}m・{len(ents)}頭）"
            L.append(head + ("　**おすすめ**" if tk else ""))
            if tk:
                recs.append(f"{tag}: " + "、".join(nm(n) for n in marks) + " → " + " ／ ".join(tk))
                L.append("- 買う: " + " ／ ".join(tk))
            shown = [n for n, (v, _) in rank if v >= 3] + [n for n in ents if n in tags and -2 <= sc[n][0] < 3]
            for n in shown:
                v, t = sc[n]; e = ents[n]
                pop = (f"{e['popularity']}人気" + (f" {e['odds']}倍" if e.get("odds") else "")) if e.get("popularity") else "人気未定"
                tg = ("【" + "・".join(tags[n]) + "】") if tags.get(n) else ""
                L.append(f"- {marks.get(n, '')}{n} {e.get('name')}（{pop}・父{e.get('sire')}・母父{e.get('damsire')}）フラグ点{v:+d}{tg}: {t[:300]}")
            for n, why in danger:
                e = ents[n]
                L.append(f"- ⚠危険な人気馬 {n} {e.get('name')}（{e.get('popularity')}人気）: {why[:200]}（消しではなく軸・1着付けにしない）")
            if not shown and not danger:
                L.append("- 目立つ馬なし")
            L.append("")
    L[8:8] = (["## 【買うもの】1〜8R（確かめた券。1点100円。9R以降の【今日買うもの】と一緒に買う）", ""] + ([f"- {b}" for b in recs] or ["- なし"]) + [""]
              + ["## 【面白い馬・危険な人気馬】（フラグ点の高い馬・血統注目・専門家・検証済み・走る条件・妙味条件・牝系。危険な人気馬は消しではなく軸・1着付けにしない）", ""]
              + ([f"- {b}" for b in notes] or ["- なし"]) + [""])
    out = ROOT / "predictions" / sat / "early.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:14 + len(recs) + len(notes)]))


if __name__ == "__main__":
    main(sys.argv[1])
