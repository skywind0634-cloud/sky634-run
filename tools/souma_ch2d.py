"""双馬 第2章（p98-107）ハービンジャー・ゴールドアリュール・マンハッタンカフェのクセの検証（2026-10-15）. 後継（同系統の他の種牡馬）でも検証.
ハービンジャー: ①延長得意 ②2-3歳は短縮苦手・4-5歳で短縮をこなす ③条件戦は延長、OP以上は短縮
ゴールドアリュール（系）: ④ダートの延長× ⑤前走短縮で好走（3着内）→今回 ⑥東京・京都（軽いダート）◎ vs ローカル
  ⑦サンデー系が来るダート（当日・前日の同場ダートで父サンデー系の3着内が人気以上）◎
マンハッタンカフェ（系）: ⑧母父米国型は短縮・母父欧州型は延長 ⑨ダートの内枠（1-3枠）× ⑩馬体重（大型）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ch2d.py → docs/analysis/souma_ch2d.md
"""
import datetime as dt
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

SS = {"ディープインパクト系", "ステイゴールド系", "ハーツクライ系", "ダイワメジャー系", "サンデーサイレンス系", "マンハッタンカフェ系", "スペシャルウィーク系",
      "フジキセキ系", "アグネスタキオン系", "ゴールドアリュール系", "ネオユニヴァース系", "ダンスインザダーク系", "キズナ系"}
OPEN = {"OP", "L", "G3", "G2", "G1"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, grade, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,grade,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, grade=grade, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, gate, age, bw, sire, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.gate,r.age,r.body_weight,h.sire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        g = ("ハービンジャー" if sire == "ハービンジャー" else "ゴールドアリュール" if sire == "ゴールドアリュール"
             else "ゴールドアリュール系後継" if sl == "ゴールドアリュール系" else "マンハッタンカフェ系" if sl == "マンハッタンカフェ系" else None)
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, gate=gate or 0, age=age or 9, bw=bw or 0, g=g, ss=sl in SS,
                              dt=country_type(dsl) if dsl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    day = defaultdict(lambda: [0.0, 0])  # (date, co, su) -> [父サンデー系の3着内 − 見込み, レース数]
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        D0, D1 = day[(R["date"], R["co"], su)], day[(prev_day, R["co"], su)]
        ssday = None if D0[1] + D1[1] < 2 else "サンデー系が来ている（+0.5頭以上）" if D0[0] + D1[0] >= 0.5 else "サンデー系が来ていない（-0.5頭以下）" if D0[0] + D1[0] <= -0.5 else "普通"
        for x in rows[rid]:
            g = x["g"]
            if not g:
                continue
            H = [h for h in hist[x["hid"]] if h[0] == su]
            pv = H[-1] if H else None
            dd = R["dist"] - pv[1] if pv else None
            r1 = None if dd is None else "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"
            pb = pband(x["pop"]); K = []
            if r1:
                K.append(("ローテ", f"{su}・{r1}", "全体"))
                K.append(("ローテ×人気", f"{su}・{r1}", pb))
            if g == "ハービンジャー" and r1 and su == "芝":
                K.append(("②年齢×ローテ", f"{'2-3歳' if x['age'] <= 3 else '4-5歳' if x['age'] <= 5 else '6歳以上'}・{r1}", "全体"))
                K.append(("③クラス×ローテ", f"{'OP以上' if R['grade'] in OPEN else '条件戦'}・{r1}", "全体"))
            if g.startswith("ゴールドアリュール") and su == "ダ":
                if pv and pv[2] == "短縮" and pv[3] <= 3 and r1:
                    K.append(("⑤前走短縮で3着内→今回", r1, "全体"))
                K.append(("⑥競馬場", "東京・京都" if R["co"] in ("東京", "京都") else "ローカル" if R["co"] in ("福島", "新潟", "小倉", "函館", "札幌") else "中山・阪神・中京", pb))
                if ssday:
                    K.append(("⑦当日・前日の同場ダートで父サンデー系が", ssday, "全体"))
            if g == "マンハッタンカフェ系":
                if r1 and x["dt"] in ("米国型", "欧州型"):
                    K.append(("⑧母父タイプ×ローテ", f"{su}・母父{x['dt']}・{r1}", "全体"))
                if su == "ダ":
                    K.append(("⑨ダートの枠", "1-3枠" if x["gate"] <= 3 else "4-8枠", "全体"))
                if x["bw"]:
                    K.append(("⑩馬体重", f"{su}・{'500kg以上' if x['bw'] >= 500 else '500kg未満'}", "全体"))
            for k in K:
                k = (g,) + k
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        D0[1] += 1
        for x in rows[rid]:
            if x["ss"]:
                D0[0] += (x["fin"] <= 3) - exp[x["p"]]
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h[0] == su]
            dd = R["dist"] - H[-1][1] if H else None
            hist[x["hid"]].append((su, R["dist"], None if dd is None else "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離", x["fin"]))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 双馬 第2章（p98-107）ハービンジャー・ゴールドアリュール・マンハッタンカフェのクセの検証（自動生成 tools/souma_ch2d.py）", "",
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
    (ROOT / "docs" / "analysis" / "souma_ch2d.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
