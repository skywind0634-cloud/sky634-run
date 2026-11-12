"""1〜6R・新馬・未勝利のおすすめ（2026-11-12 ユーザー「下級条件や未勝利・新馬のほうが血統の影響がありそう。7レースより前も、血統やフラグでおすすめのレース・馬を出して」）.
cards_early/<日付>/（python -m keiba.cli build-cards --early）の各レースで、tools/flag_backtest.py と同じ材料（book_condition_horses・pace_l3_horses・course_check_horses）
のフラグ点（○◎の数 − ×▽▼の数）を出し、
  ★未勝利の単勝: 未勝利戦でフラグ点が一番高い馬（+5以上）の単勝100円。
    全レースDBで材料を2021-24だけで選んだフラグの確かめ（EARLY=1 FB_DB=data/keiba_all.db … flag_backtest.py 2025-01-01 2026-11-08）で
    2025 回収122%（804レース）・2026 122%（649レース）。+4以上 112/118%、+6以上 125/112% と区切りをずらしても100%超。
  新馬・1〜6Rの1勝クラスは年でぶれる（新馬 +5: 61/73%、1勝 +5: 67/58%）ので参考（フラグ点の上位だけ出す）。ワイド・3連複は100%前後で安定しないので出さない。
使い方: python3 tools/early_picks.py <土曜の日付> → predictions/<土曜>/early.md
"""
import datetime as dt, json, re, sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PLUS, MINUS = re.compile(r"[◎○]（"), re.compile(r"[×▽▼]（")
TH = 5


def kind(c):
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


def main(sat):
    s = dt.date.fromisoformat(sat)
    L = [f"# 1〜6R・新馬・未勝利のおすすめ {s}〜{s + dt.timedelta(days=1)}（tools/early_picks.py）", "",
         "- ★未勝利の単勝＝未勝利戦でフラグ点が一番高い馬（+5以上）の単勝100円。材料を2021-24だけで選んだフラグで、2025年 回収122%（804レース）・2026年 122%（649レース）。",
         "- 新馬・1勝クラスは年でぶれるので参考。フラグ点＝○◎の数 − ×▽▼の数。馬券は自己責任で。", ""]
    buys = []
    for d in (s, s + dt.timedelta(days=1)):
        folder = ROOT / "cards_early" / d.isoformat()
        cards = sorted((json.load(open(p)) for p in folder.glob("*.json")), key=lambda c: (c.get("course") or "", c.get("race_no") or 0))
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
            buy = k == "未勝利" and top_s >= TH
            head = f"### {c.get('course')}{c.get('race_no')}R {c.get('name') or ''}（{k}・{c.get('surface')}{c.get('distance')}m・{len(ents)}頭）"
            L.append(head + ("　**★未勝利の単勝**" if buy else ""))
            if buy:
                e = ents[top_n]
                buys.append(f"{d.strftime('%m/%d')} {c.get('course')}{c.get('race_no')}R 単勝 {top_n} {e.get('name')}（フラグ点+{top_s}"
                            + (f"・{e['popularity']}番人気 {e['odds']}倍" if e.get("popularity") else "") + "）")
            for n, (v, t) in rank:
                if v < 3:
                    break
                e = ents[n]
                pop = f"{e['popularity']}人気 {e.get('odds')}倍" if e.get("popularity") else "人気未定"
                L.append(f"- {'★買う ' if buy and n == top_n else ''}{n} {e.get('name')}（{pop}・父{e.get('sire')}・母父{e.get('damsire')}）フラグ点+{v}: {t[:300]}")
            if rank[0][1][0] < 3:
                L.append("- フラグ点+3以上の馬なし")
            L.append("")
    L[5:5] = ["## 【買うもの】★未勝利の単勝（1点100円）", ""] + ([f"- {b}" for b in buys] or ["- なし"]) + [""]
    out = ROOT / "predictions" / sat / "early.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12 + len(buys)]))


if __name__ == "__main__":
    main(sys.argv[1])
