"""双馬 第2章（p108-117）キンシャサノキセキ・サウスヴィグラス・ヴィクトワールピサ・ネオユニヴァースのクセの検証（2026-10-15）.
キンシャサノキセキ: ①芝の延長◎ ②芝・前走短縮で凡走→今回同距離 ③ダートは外枠◎・内枠× ④ダ→芝替わり◎ ⑤芝の時計がかかる日（当日・前日の同場）◎
サウスヴィグラス（父・母父）: ⑥ダートの短縮◎ ⑦外枠 ⑧前走で先行できず凡走（最初のコーナー前15%より後ろ・6着以下）→今回 ⑨前走楽勝（1着・2着に0.5秒以上）→次走×
ヴィクトワールピサ: ⑩短縮◎・延長×
ネオユニヴァース（父・母父）: ⑪延長◎ ⑫芝の時計がかかる日◎ ⑬予想テン3F（今回コース平均−前走）が遅くなる◎ / 速くなる×
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ch2e.py → docs/analysis/souma_ch2e.md
"""
import datetime as dt
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, n, f3, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,n_runners,first3f,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, n=n or 16, f3=f3, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}; second = {}
    for rid, hid, fin, pop, num, gate, pas, tsec, sire, ds in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.gate,r.passing,r.time_sec,h.sire,h.damsire "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        if fin == 2 and tsec:
            second[rid] = tsec
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        gs = []
        for nm in ("キンシャサノキセキ", "サウスヴィグラス", "ヴィクトワールピサ", "ネオユニヴァース"):
            if sire == nm:
                gs.append("父" + nm)
            if ds == nm and nm in ("サウスヴィグラス", "ネオユニヴァース"):
                gs.append("母父" + nm)
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, gate=gate or 0, p0=p0, tsec=tsec, gs=gs))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    order = sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r))
    cm = defaultdict(list); cf = defaultdict(list); day = defaultdict(list); hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in order:
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
        dspeed = None if len(sp) < 2 else "高速日" if sum(sp) / len(sp) <= -0.5 else "時計がかかる日" if sum(sp) / len(sp) >= 0.5 else "平均的な日"
        fmean = sum(cf[key][-200:]) / len(cf[key][-200:]) if len(cf[key]) >= 10 else None
        for x in rows[rid]:
            if not x["gs"]:
                continue
            Hall = hist[x["hid"]]
            H = [h for h in Hall if h["su"] == su]
            pv = H[-1] if H else None
            dd = R["dist"] - pv["dist"] if pv else None
            r1 = None if dd is None else "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"
            pb = pband(x["pop"])
            for g in x["gs"]:
                K = []
                if r1:
                    K.append(("ローテ", f"{su}・{r1}", "全体"))
                    K.append(("ローテ×人気", f"{su}・{r1}", pb))
                if g == "父キンシャサノキセキ":
                    if su == "芝" and r1 == "同距離" and pv and pv["rot"] == "短縮":
                        K.append(("②芝・前走短縮→今回同距離", "前走6着以下" if pv["fin"] >= 6 else "前走5着以内", "全体"))
                    if su == "ダ":
                        K.append(("③ダートの枠", "1-3枠" if x["gate"] <= 3 else "4-6枠" if x["gate"] <= 6 else "7-8枠", "全体"))
                    if su == "芝" and Hall and Hall[-1]["su"] == "ダ":
                        K.append(("④ダ→芝替わり", "全体", pb))
                    if su == "芝" and dspeed:
                        K.append(("⑤当日・前日の同場の芝", dspeed, "全体"))
                if g.endswith("サウスヴィグラス") and su == "ダ":
                    K.append(("⑦ダートの枠", "1-3枠" if x["gate"] <= 3 else "4-6枠" if x["gate"] <= 6 else "7-8枠", pb))
                    if pv and pv["pos"] is not None:
                        if pv["pos"] > 0.15 and pv["fin"] >= 6:
                            K.append(("⑧前走で先行できず6着以下→今回", f"{'7-8枠' if x['gate'] >= 7 else '1-6枠'}・{r1}", "全体"))
                        if pv["fin"] == 1 and pv["margin"] is not None and pv["margin"] >= 0.5:
                            K.append(("⑨前走楽勝（0.5秒以上）→今回", "全体", "全体"))
                if g.endswith("ネオユニヴァース"):
                    if su == "芝" and dspeed:
                        K.append(("⑫当日・前日の同場の芝", dspeed, "全体"))
                    if fmean and pv and pv["f3"]:
                        tg = fmean - pv["f3"]
                        K.append(("⑬予想テン3F差（+は前走より遅い）", f"{su}・{'+0.5秒以上' if tg >= 0.5 else '-0.5秒以下' if tg <= -0.5 else '±0.5秒'}", "全体"))
                for k in K:
                    k = (g,) + k
                    a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        wt = wtime.get(rid)
        if wt and len(cm[key]) >= 10:
            day[(R["date"], R["co"], su)].append(wt - sum(cm[key][-200:]) / len(cm[key][-200:]))
        if wt:
            cm[key].append(wt)
        if R["f3"]:
            cf[key].append(R["f3"])
        mg = second[rid] - wt if wt and rid in second else None
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h["su"] == su]
            dd = R["dist"] - H[-1]["dist"] if H else None
            hist[x["hid"]].append(dict(su=su, dist=R["dist"], fin=x["fin"], f3=R["f3"], margin=mg if x["fin"] == 1 else None,
                                       pos=x["p0"] / max(R["n"], 1) if x["p0"] else None,
                                       rot=None if dd is None else "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 双馬 第2章（p108-117）キンシャサノキセキ・サウスヴィグラス・ヴィクトワールピサ・ネオユニヴァースの検証（自動生成 tools/souma_ch2e.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 父/母父 | 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | {k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ch2e.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
