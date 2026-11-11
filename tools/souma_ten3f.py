"""双馬 第1章（p36-42）: テン3Fの前走比・延長得意の年齢・芝/ダートスタートの例外の検証（2026-10-15）.
1) 実際のテン3F差（今回−前走, 同じ芝ダ）: 2秒以上遅い / 0.5-2秒遅い / ±0.5 / 0.5-2秒速い / 2秒以上速い × ローテ（結果, 理解用）
2) 予想テン3F差（今回コース×距離の過去平均テン3F − 前走の実際のテン3F）: レース前に使える版 × 人気帯
3) 父ハーツクライ/ハービンジャー × 延長 × 2-3歳/4歳以上
4) ダ1400(芝スタート: 京都・阪神・中京)→ダ1200 / ダ1200→ダ1400（同場の組合せは問わない）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ten3f.py → docs/analysis/souma_ten3f.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TURF_START = {("東京", 1600), ("中山", 1200), ("福島", 1150), ("新潟", 1200), ("京都", 1400), ("阪神", 1400), ("阪神", 2000), ("中京", 1400)}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def band(d):
    return "〜-2.0秒" if d <= -2 else "-2.0〜-0.5秒" if d <= -0.5 else "±0.5秒" if d < 0.5 else "+0.5〜+2.0秒" if d < 2 else "+2.0秒〜"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, su, dist, f3, pay in c.execute("select race_id,date,course,surface,distance,first3f,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, f3=f3, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, age, sire in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.age,h.sire from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, age=age, sire=sire))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    cmean = defaultdict(list)
    hist = {}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        mean = sum(cmean[key][-200:]) / len(cmean[key][-200:]) if len(cmean[key]) >= 10 else None
        for x in rows[rid]:
            pv = hist.get(x["hid"])
            K = []
            band_p = "1-3番人気" if x["pop"] <= 3 else "4-6番人気" if x["pop"] <= 6 else "7番人気以下"
            if pv and pv["su"] == su:
                dd = R["dist"] - pv["dist"]; rot = "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"
                if R["f3"] and pv["f3"]:
                    K.append(("①実際のテン3F差（今回−前走, +は遅い=楽）", f"{su}・{band(R['f3'] - pv['f3'])}", "全体"))
                    K.append(("①実際のテン3F差×ローテ", f"{su}・{rot}・テン{'遅く' if R['f3'] - pv['f3'] >= 0.5 else '速く' if R['f3'] - pv['f3'] <= -0.5 else '同程度'}", "全体"))
                if mean and pv["f3"]:
                    K.append(("②予想テン3F差（コース平均−前走, レース前に使える）", f"{su}・{band(mean - pv['f3'])}", band_p))
                if x["sire"] in ("ハーツクライ", "ハービンジャー") and rot == "延長":
                    K.append(("③父ハーツクライ/ハービンジャー×延長", f"{su}・{'2-3歳' if (x['age'] or 9) <= 3 else '4歳以上'}", "全体"))
                if su == "ダ" and R["co"] in ("京都", "阪神", "中京"):
                    if pv["dist"] == 1400 and R["dist"] == 1200:
                        K.append(("④芝スタートの例外", "ダ1400(芝スタート)→ダ1200（短縮だがテンは遅くなる）", "全体"))
                    if pv["dist"] == 1200 and R["dist"] == 1400:
                        K.append(("④芝スタートの例外", "ダ1200→ダ1400(芝スタート)（延長だがテンは速くなる）", "全体"))
                if su == "ダ" and pv["su"] == "ダ":
                    ts_now, ts_prev = (R["co"], R["dist"]) in TURF_START, (pv["co"], pv["dist"]) in TURF_START
                    if ts_now != ts_prev:
                        K.append(("④芝スタートの例外（全場）", f"前走{'芝' if ts_prev else 'ダ'}スタート→今回{'芝' if ts_now else 'ダ'}スタート・{rot}", "全体"))
            for k in K:
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        if R["f3"]:
            cmean[key].append(R["f3"])
        for x in rows[rid]:
            hist[x["hid"]] = dict(su=su, dist=R["dist"], f3=R["f3"], co=R["co"])
    L = ["# 双馬 第1章（p36-42）テン3F・延長得意・芝/ダートスタート例外の検証（自動生成 tools/souma_ten3f.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。テン3Fはレースの前半3F（先頭のタイム）。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ten3f.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    # 予想表示用: コース×芝ダ×距離の直近200レースの平均テン3F（keiba/digest.py の予想テン3F差）
    tbl = {f"{k[0]}|{k[1]}|{k[2]}": round(sum(v[-200:]) / len(v[-200:]), 2) for k, v in cmean.items() if len(v) >= 10}
    (ROOT / "data" / "knowledge" / "course_ten3f.json").write_text(json.dumps(tbl, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
