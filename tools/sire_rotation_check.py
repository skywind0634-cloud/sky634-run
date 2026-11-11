"""種牡馬ごとのローテのクセを汎用に検証する（双馬 第2章 p118 以降, 2026-10-15）.
各種牡馬について: ①ローテ（芝ダ×短縮/同距離/延長）×人気 ②変更の幅（少し=200m / 大幅=400m以上）
 ③前走ローテ×前走の結果（3着内 / 6着以下）→今回ローテ（「延長失敗後の短縮」「短縮好走後の同距離・延長」など）
 ④年齢（2-3歳 / 4歳以上）×ローテ ⑤芝→ダ / ダ→芝替わり
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。
使い方: python3 tools/sire_rotation_check.py <出力名> <種牡馬1> <種牡馬2> ... → docs/analysis/<出力名>.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def rot(dd):
    return None if dd is None else "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"


def main(name, sires):
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, su, dist, pay in c.execute("select race_id,date,surface,distance,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, su=su, dist=dist or 1600, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, age, sire in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.age,h.sire from results r left join horses h using(horse_id) "
            "where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, age=age or 9, sire=sire))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        for x in rows[rid]:
            if x["sire"] in sires:
                Hall = hist[x["hid"]]
                H = [h for h in Hall if h["su"] == su]
                pv = H[-1] if H else None
                dd = R["dist"] - pv["dist"] if pv else None
                r1 = rot(dd); pb = pband(x["pop"]); K = []
                if r1:
                    K.append(("①ローテ", f"{su}・{r1}", "全体"))
                    K.append(("①ローテ×人気", f"{su}・{r1}", pb))
                    if r1 != "同距離":
                        K.append(("②変更の幅", f"{su}・{'少し（200m）' if abs(dd) <= 200 else '大幅（400m以上）'}{r1}", "全体"))
                    if pv["rot"]:
                        K.append(("③前走ローテ×前走の結果→今回", f"{su}・前走{pv['rot']}で{'3着内' if pv['fin'] <= 3 else '6着以下' if pv['fin'] >= 6 else '4-5着'}→今回{r1}", "全体"))
                    K.append(("④年齢×ローテ", f"{su}・{'2-3歳' if x['age'] <= 3 else '4歳以上'}・{r1}", "全体"))
                if Hall and Hall[-1]["su"] != su:
                    K.append(("⑤芝ダ替わり", f"{Hall[-1]['su']}→{su}", pb))
                for k in K:
                    k = (x["sire"],) + k
                    a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h["su"] == su]
            hist[x["hid"]].append(dict(su=su, dist=R["dist"], fin=x["fin"], rot=rot(R["dist"] - H[-1]["dist"]) if H else None))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = [f"# 種牡馬のローテのクセ: {'・'.join(sires)}（自動生成 tools/sire_rotation_check.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。各日7R以降（未勝利除く）。前走は DB 内の同じ芝ダの前走。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 父 | 見方 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | {k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / f"{name}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
