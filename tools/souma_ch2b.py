"""双馬 第2章（p78-85）ハーツクライ・ステイゴールドのクセの検証（2026-10-15）. 後継（同系統の他の種牡馬）でも検証する.
ハーツクライ: ①延長得意・短縮苦手（母父を問わない）②2-3歳は2000m以上への延長で穴、出走馬の多くが延長のとき有利
  ③ハイペースで追走させると末脚を失う（展開予想＝前走で前15%にいた馬の数）
ステイゴールド: ④タフな馬場（芝の道悪 / 当日・前日の同場の勝ちタイムが遅い）◎、高速馬場× ⑤小回り（中山・ローカル）◎、広いコース×
  ⑥延長も苦にしない ⑦上がりのかかる競馬が得意（展開予想・補正上がり）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ch2b.py → docs/analysis/souma_ch2b.md
"""
import datetime as dt
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

SMALL = {"中山", "福島", "小倉", "函館", "札幌"}
WIDE = {"東京", "新潟", "京都"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def rot(a, b):
    dd = a - b
    return "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, n, going, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,n_runners,going,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, n=n or 16, going=going or "良", pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}
    for rid, hid, fin, pop, num, age, pas, tsec, sire, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.age,r.passing,r.time_sec,h.sire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        gs = []
        if sire == "ハーツクライ":
            gs.append("ハーツクライ")
        elif sl == "ハーツクライ系":
            gs.append("ハーツ系後継")
        if sl == "ステイゴールド系":
            gs.append("ステゴ系（全体）")
            if sire in ("オルフェーヴル", "ゴールドシップ"):
                gs.append(sire)
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, age=age or 9, p0=p0, gs=gs, dt=country_type(dsl) if dsl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    order = sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r))
    cm = defaultdict(list); day = defaultdict(list); hist = {}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in order:
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        rs = rows[rid]
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
        dspeed = None if len(sp) < 2 else "高速（-0.5秒以上速い）" if sum(sp) / len(sp) <= -0.5 else "時計がかかる（+0.5秒以上遅い）" if sum(sp) / len(sp) >= 0.5 else "平均"
        known = [hist[x["hid"]][2] for x in rs if x["hid"] in hist and hist[x["hid"]][2] is not None]
        nf = sum(k <= 0.15 for k in known) if rs and len(known) >= 0.7 * len(rs) else None
        pace = None if nf is None else "スロー予想" if nf <= 1 else "ハイ予想" if nf >= 4 else "平均予想"
        rots = [rot(R["dist"], hist[x["hid"]][1]) for x in rs if x["hid"] in hist and hist[x["hid"]][0] == su]
        ext_share = sum(r == "延長" for r in rots) / len(rots) if rots else 0
        for x in rs:
            if not x["gs"]:
                continue
            pv = hist.get(x["hid"])
            r1 = rot(R["dist"], pv[1]) if pv and pv[0] == su else None
            pb = pband(x["pop"]); young = x["age"] <= 3
            for g in x["gs"]:
                K = []
                if g in ("ハーツクライ", "ハーツ系後継"):
                    if r1:
                        K.append(("①ローテ×人気", f"{su}・{r1}", pb))
                        K.append(("①ローテ（全体）", f"{su}・{r1}", "全体"))
                        if x["dt"]:
                            K.append(("①ローテ×母父タイプ", f"{su}・{r1}・母父{x['dt']}", "全体"))
                        if su == "芝" and young and r1 == "延長" and R["dist"] >= 2000:
                            K.append(("②2-3歳×芝2000m以上への延長", "全体", pb))
                        if su == "芝" and r1 == "延長":
                            K.append(("②芝の延長×出走馬の延長の割合", "延長馬が半数以上" if ext_share >= 0.5 else "延長馬が半数未満", "全体"))
                    if pace:
                        K.append(("③展開予想", f"{su}・{pace}", "全体"))
                else:
                    if su == "芝":
                        K.append(("④芝の馬場状態", "良" if R["going"].startswith("良") else "道悪", "全体"))
                        if dspeed:
                            K.append(("④当日・前日の同場の芝の時計", dspeed, "全体"))
                        ct = "小回り（中山・ローカル）" if R["co"] in SMALL else "広い（東京・新潟・京都）" if R["co"] in WIDE else "阪神・中京"
                        K.append(("⑤コース", ct, "全体"))
                        K.append(("⑤コース×人気", ct, pb))
                        if r1:
                            K.append(("⑥ローテ", f"芝・{r1}", "全体"))
                        if pace:
                            K.append(("⑦展開予想", f"芝・{pace}", "全体"))
                    elif r1:
                        K.append(("⑥ローテ", f"ダ・{r1}", "全体"))
                for k in K:
                    k = (g,) + k
                    a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        wt = wtime.get(rid)
        if wt and len(cm[key]) >= 10:
            day[(R["date"], R["co"], su)].append(wt - sum(cm[key][-200:]) / len(cm[key][-200:]))
        if wt:
            cm[key].append(wt)
        for x in rs:
            hist[x["hid"]] = (su, R["dist"], x["p0"] / max(R["n"], 1) if x["p0"] else None)

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 双馬 第2章（p78-85）ハーツクライ・ステイゴールドのクセの検証（自動生成 tools/souma_ch2b.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。後継＝同じ系統の他の種牡馬。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 父 | 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | {k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ch2b.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
