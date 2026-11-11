"""上がりの速さをペース込みで見直す（2026-10-15, ユーザー指摘: スローなら残り600mからのよーいドンで上がりは速くなる）.
1) テン3F（コース平均との差）と上がり3Fの関係: テンが遅いほど上がりが速いか。回帰の傾きでペース補正した上がり（補正上がり）を作る
2) ディープインパクト・ディープ系後継: テン（遅い/平均/速い）× 上がり（速い/平均/遅い）の組合せ、補正上がり別
3) キンカメ系後継×母父米国型の「高速日」: 勝ちタイム基準 / 補正上がり基準 / テンが速いのに上がりも速い日
4) 双馬 p60-64 の「当日・前日の上がりが速い日はダ延長×」を補正上がりで再確認
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/pace_adj_check.py → docs/analysis/pace_adj_check.md
"""
import datetime as dt
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def rot(a, b):
    dd = a - b
    return "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"


def b3(v, fast="速い", slow="遅い"):
    return fast if v <= -0.5 else slow if v >= 0.5 else "平均"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, f3, l3, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,first3f,last3f,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, f3=f3, l3=l3, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}
    for rid, hid, fin, pop, num, tsec, sire, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.time_sec,h.sire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        g = ("ディープインパクト" if sire == "ディープインパクト" else "ディープ系後継" if sl == "ディープインパクト系"
             else "キンカメ系後継" if sl == "キングカメハメハ系" and sire != "キングカメハメハ" else None)
        rows[rid].append(dict(hid=hid, fin=fin, p=min(pop, 14), num=num, g=g, dt=country_type(dsl) if dsl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    order = sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r))
    # 1) 各レースのコース平均との差（それまでの直近200レース）
    cm = defaultdict(lambda: defaultdict(list)); D = {}
    for rid in order:
        R = races[rid]; key = (R["co"], R["su"], R["dist"]); d = {}
        for kind, v in (("f3", R["f3"]), ("l3", R["l3"]), ("wt", wtime.get(rid))):
            L = cm[kind][key]
            d[kind] = v - sum(L[-200:]) / len(L[-200:]) if v and len(L) >= 10 else None
            if v:
                cm[kind][key].append(v)
        D[rid] = d
    slope = {}
    for su in ("芝", "ダ"):
        xs = [(D[r]["f3"], D[r]["l3"]) for r in races if races[r]["su"] == su and D[r]["f3"] is not None and D[r]["l3"] is not None
              and races[r]["date"] < "2024-01-01"]
        mx = sum(x for x, _ in xs) / len(xs); my = sum(y for _, y in xs) / len(xs)
        slope[su] = sum((x - mx) * (y - my) for x, y in xs) / sum((x - mx) ** 2 for x, _ in xs)
    for rid in races:
        d = D[rid]
        d["adj"] = d["l3"] - slope[races[rid]["su"]] * d["f3"] if d["f3"] is not None and d["l3"] is not None else None
    L = ["# 上がりの速さをペース込みで見直す（自動生成 tools/pace_adj_check.py）", "",
         "- テン3F・上がり3F・勝ちタイムは、同じ場・芝ダ・距離の直近200レースの平均との差。補正上がり＝上がり差 − 傾き×テン差（傾きは2021-23で推定）。",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", ""]
    L.append("## 1) テンと上がりの関係（2021-23で推定）\n")
    for su in ("芝", "ダ"):
        L.append(f"- {su}: テンが1秒遅いと上がりは **{-slope[su]:.2f}秒速くなる**（傾き {slope[su]:.2f}）")
    tab = defaultdict(lambda: [0, 0])
    for r in races:
        d = D[r]
        if d["f3"] is not None and d["l3"] is not None:
            t = tab[(races[r]["su"], b3(d["f3"]), b3(d["l3"]))]; t[0] += 1
    L += ["", "| 芝ダ | テン | 上がり速い | 平均 | 上がり遅い |", "|---|---|---|---|---|"]
    for su in ("芝", "ダ"):
        for f in ("遅い", "平均", "速い"):
            n = sum(tab[(su, f, l)][0] for l in ("速い", "平均", "遅い"))
            L.append(f"| {su} | テン{f} | " + " | ".join(f"{tab[(su, f, l)][0] / n * 100:.0f}%" for l in ("速い", "平均", "遅い")) + " |")
    # 2)〜4)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    day = defaultdict(list); hist = {}
    for rid in order:
        R = races[rid]; su = R["su"]; pr = per(R["date"]); d = D[rid]
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
        dayk = {}
        if len(sp) >= 2:
            for i, nm in ((0, "勝ちタイム"), (1, "上がり（補正なし）"), (2, "補正上がり")):
                v = [s[i] for s in sp if s[i] is not None]
                if len(v) >= 2:
                    dayk[nm] = sum(v) / len(v)
        for x in rows[rid]:
            K = []
            if x["g"] in ("ディープインパクト", "ディープ系後継") and su == "芝" and d["f3"] is not None and d["l3"] is not None:
                K.append((x["g"], "②テン×上がり（結果）", f"テン{b3(d['f3'])}・上がり{b3(d['l3'])}"))
                K.append((x["g"], "②補正上がり（結果）", b3(d["adj"])))
            if x["g"] == "キンカメ系後継" and su == "芝" and x["dt"] == "米国型":
                for nm, v in dayk.items():
                    K.append(("キンカメ系後継×母父米国型", f"③当日・前日の同場の{nm}", b3(v)))
            pv = hist.get(x["hid"])
            if su == "ダ" and pv and pv[0] == "ダ" and rot(R["dist"], pv[1]) == "延長":
                for nm, v in dayk.items():
                    K.append(("ダ・延長", f"④当日・前日の同場の{nm}", b3(v)))
            for k in K:
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        day[(R["date"], R["co"], su)].append((d["wt"], d["l3"], d["adj"]))
        for x in rows[rid]:
            hist[x["hid"]] = (su, R["dist"])

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L += ["", "## 2)〜4) 馬券への影響", "", "| 対象 | 見方 | 区分 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "pace_adj_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
