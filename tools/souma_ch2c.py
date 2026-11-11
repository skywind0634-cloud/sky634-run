"""双馬 第2章（p86-97）ダイワメジャー・ルーラーシップ・ロードカナロアのクセの検証（2026-10-15）. 内回り/外回り（races.layout）も使う.
ダイワメジャー（＋後継カレンブラックヒル・アドマイヤマーズ）: ①短縮◎・延長× ②厳しく先行（前走で前15%）③前走ハイペース（実際のテンが速い）を先行して負け→同距離◎
  ④スロー予想（瞬発力勝負）× / ハイ予想◎
ルーラーシップ: ⑤距離（芝2400m以上◎・1400m以下）⑥ローカル芝2600 / 初めての2400m以上 ⑦芝1600→1200のような大幅短縮× ⑧新潟芝外回り◎（内回りと比較）
  ⑨高速日×（当日・前日の同場の芝の勝ちタイム）
ロードカナロア（＋後継サートゥルナーリア）: ⑩人気サイドで走る（人気帯）⑪初めての短縮×・2回目以降の短縮○ ⑫高速日◎
  ⑬母父サンデー系は延長OK / 母父米国型（スピード）は延長× ⑭距離変更の幅（±200m=少し / 400m以上=大幅）
共通: ⑮内回り/外回り別（京都・阪神・新潟・中山の芝）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ch2c.py → docs/analysis/souma_ch2c.md
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
LOCAL = {"福島", "小倉", "函館", "札幌", "新潟"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, n, f3, lay, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,n_runners,first3f,layout,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, n=n or 16, f3=f3, lay=lay, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}
    for rid, hid, fin, pop, num, pas, tsec, sire, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.passing,r.time_sec,h.sire,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        g = ("ダイワメジャー" if sire == "ダイワメジャー" else "ダイワメジャー後継" if sire in ("カレンブラックヒル", "アドマイヤマーズ")
             else "ルーラーシップ" if sire == "ルーラーシップ" else "ロードカナロア" if sire == "ロードカナロア"
             else "サートゥルナーリア" if sire == "サートゥルナーリア" else None)
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, p0=p0, g=g, dsl=dsl, dt=country_type(dsl) if dsl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    order = sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r))
    cm = defaultdict(list); cf = defaultdict(list); day = defaultdict(list); hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in order:
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        rs = rows[rid]
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
        dspeed = None if len(sp) < 2 else "高速日" if sum(sp) / len(sp) <= -0.5 else "時計がかかる日" if sum(sp) / len(sp) >= 0.5 else "平均的な日"
        known = [hist[x["hid"]][-1][2] for x in rs if hist[x["hid"]] and hist[x["hid"]][-1][2] is not None]
        nf = sum(k <= 0.15 for k in known) if rs and len(known) >= 0.7 * len(rs) else None
        pace = None if nf is None else "スロー予想" if nf <= 1 else "ハイ予想" if nf >= 4 else "平均予想"
        f3d = R["f3"] - sum(cf[key][-200:]) / len(cf[key][-200:]) if R["f3"] and len(cf[key]) >= 10 else None
        for x in rs:
            g = x["g"]
            if not g:
                continue
            H = [h for h in hist[x["hid"]] if h[0] == su]
            pv = H[-1] if H else None
            dd = R["dist"] - pv[1] if pv else None
            r1 = None if dd is None else "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"
            pb = pband(x["pop"]); K = []
            lay = f"{R['co']}{su}{'外回り' if R['lay'] == '外' else '内回り' if R['lay'] == '内' else '直線' if R['lay'] == '直' else ''}" if R["lay"] else None
            if lay:
                K.append(("⑮内回り/外回り", lay, "全体"))
            if dspeed and su == "芝":
                K.append(("⑨⑫当日・前日の同場の芝の時計", dspeed, "全体"))
            if r1:
                K.append(("①⑪ローテ", f"{su}・{r1}", "全体"))
                K.append(("①⑪ローテ×人気", f"{su}・{r1}", pb))
                K.append(("⑭距離変更の幅", f"{su}・{'同距離' if r1 == '同距離' else ('少し' if abs(dd) <= 200 else '大幅（400m以上）') + r1}", "全体"))
            if pace:
                K.append(("④展開予想", f"{su}・{pace}", "全体"))
            if g.startswith("ダイワメジャー") and pv:
                if pv[2] is not None:
                    K.append(("②前走の位置取り", f"{su}・{'前15%' if pv[2] <= 0.15 else '後方40%' if pv[2] > 0.6 else '中団'}", "全体"))
                if r1 == "同距離" and pv[2] is not None and pv[2] <= 0.25 and pv[3] >= 4 and pv[4] is not None:
                    K.append(("③前走で先行して4着以下→同距離", f"{su}・前走のテン{'速い' if pv[4] <= -0.5 else '遅い' if pv[4] >= 0.5 else '平均'}", "全体"))
            if g == "ルーラーシップ" and su == "芝":
                bd = "1400m以下" if R["dist"] <= 1400 else "1600-1800m" if R["dist"] <= 1800 else "2000-2200m" if R["dist"] <= 2200 else "2400m以上"
                K.append(("⑤芝の距離", bd, pb))
                if R["dist"] >= 2400:
                    first = not any(h[1] >= 2400 for h in H)
                    K.append(("⑥芝2400m以上", f"{'初めて' if first else '経験あり'}・{'ローカル' if R['co'] in LOCAL else '中央4場'}", "全体"))
                if r1 == "短縮" and dd <= -400:
                    K.append(("⑦芝の大幅短縮（400m以上）", "全体", "全体"))
            if g in ("ロードカナロア", "サートゥルナーリア"):
                if r1 == "短縮":
                    n_s = sum(1 for i in range(1, len(H)) if H[i][1] <= H[i - 1][1] - 200)
                    K.append(("⑪短縮の経験", f"{su}・{'初めての短縮' if n_s == 0 else '2回目以降の短縮'}", "全体"))
                if r1 in ("延長", "同距離", "短縮") and x["dsl"]:
                    t = "母父サンデー系" if x["dsl"] in SS else f"母父{x['dt']}" if x["dt"] else None
                    if t:
                        K.append(("⑬母父×ローテ", f"{su}・{t}・{r1}", "全体"))
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
        for x in rs:
            hist[x["hid"]].append((su, R["dist"], x["p0"] / max(R["n"], 1) if x["p0"] else None, x["fin"], f3d))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 双馬 第2章（p86-97）ダイワメジャー・ルーラーシップ・ロードカナロアのクセの検証（自動生成 tools/souma_ch2c.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。内回り/外回りはレース結果の表記（races.layout）。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 父 | 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | {k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ch2c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
