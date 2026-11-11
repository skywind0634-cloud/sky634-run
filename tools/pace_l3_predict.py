"""予想ペース × 馬の上がり能力（レース前に分かる情報だけ, 2026-10-15）.
ユーザー指摘: スローなら残り600mからのよーいドンで上がりの速い馬が来る。ペースが予想できれば上がり能力は予想に使える。
- 予想ペース: 前走で前15%にいた馬の数（0-1頭=スロー予想 / 2-3頭=平均 / 4頭以上=ハイ予想）。実際のテン（コース平均との差）との一致も確認
- 馬の上がり能力（それまでの DB の成績から）:
  a) 前走の上がり順位（1位 / 2-3位 / 4位以下）
  b) 近3走で上がり3位以内の回数（2回以上 / 1回 / 0回）
  c) 近3走の上がり順位の平均（出走頭数で割った割合, 上位20%以内）
  d) 芝で上がり33.5秒以下の経験（芝のみ）
  e) 前走の位置取り（最初のコーナー: 前15% / 中団 / 後方40%）＝脚質
- 予想ペース × 能力 × 芝ダ × 人気帯 の A/E。比較用に実際のペース（結果）でも同じ表を作る
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/pace_l3_predict.py → docs/analysis/pace_l3_predict.md
"""
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
        races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, n=n or 16, f3=f3, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, pas, l3 in c.execute(
            "select race_id,horse_id,finish,popularity,number,passing,last3f from results where finish is not null and popularity is not null"):
        if rid not in races:
            continue
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        rows[rid].append(dict(hid=hid, fin=fin, p=min(pop, 14), pop=pop, num=num, p0=p0, l3=l3))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = defaultdict(list)  # hid -> [(su, pos_ratio, l3rank, l3rank_ratio, l3)]
    cm = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    acc = defaultdict(lambda: defaultdict(int))
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        rs = rows[rid]
        known = [hist[x["hid"]][-1][1] for x in rs if hist[x["hid"]] and hist[x["hid"]][-1][1] is not None]
        nf = sum(k <= 0.15 for k in known) if rs and len(known) >= 0.7 * len(rs) else None
        pace = None if nf is None else "スロー予想(前0-1頭)" if nf <= 1 else "ハイ予想(前4頭+)" if nf >= 4 else "平均予想(前2-3頭)"
        f3d = R["f3"] - sum(cm[key][-200:]) / len(cm[key][-200:]) if R["f3"] and len(cm[key]) >= 10 else None
        actual = None if f3d is None else "実際スロー" if f3d >= 0.5 else "実際ハイ" if f3d <= -0.5 else "実際平均"
        if pace and actual:
            acc[(su, pace)][actual] += 1
        for x in rs:
            H = [h for h in hist[x["hid"]] if h[0] == su][-3:]
            if not H:
                continue
            F = []
            r1 = H[-1][2]
            F.append(("a前走の上がり順位", "1位" if r1 == 1 else "2-3位" if r1 <= 3 else "4位以下"))
            n3 = sum(h[2] <= 3 for h in H)
            if len(H) >= 2:
                F.append(("b近3走の上がり3位以内", "2回以上" if n3 >= 2 else "1回" if n3 == 1 else "0回"))
                rr = [h[3] for h in H if h[3] is not None]
                if rr:
                    m = sum(rr) / len(rr)
                    F.append(("c近3走の上がり順位の平均", "上位20%以内" if m <= 0.2 else "上位20-50%" if m <= 0.5 else "下位50%"))
            if su == "芝":
                F.append(("d芝で上がり33.5秒以下の経験", "あり" if any(h[4] and h[4] <= 33.5 for h in hist[x["hid"]] if h[0] == "芝") else "なし"))
            pz = H[-1][1]
            if pz is not None:
                F.append(("e前走の位置取り", "前15%" if pz <= 0.15 else "後方40%" if pz > 0.6 else "中団"))
            pb = pband(x["pop"])
            for f, v in F:
                for pk in ((pace, "予想"), (actual, "結果")):
                    if pk[0]:
                        k = (pk[1], su, pk[0], f, v, pb)
                        a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        if R["f3"]:
            cm[key].append(R["f3"])
        l3s = sorted(x["l3"] for x in rs if x["l3"])
        for x in rs:
            rk = l3s.index(x["l3"]) + 1 if x["l3"] else 99
            hist[x["hid"]].append((su, x["p0"] / max(R["n"], 1) if x["p0"] else None, rk, rk / max(len(l3s), 1) if x["l3"] else None, x["l3"]))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 予想ペース × 馬の上がり能力（自動生成 tools/pace_l3_predict.py）", "",
         "- 予想ペース＝前走で前15%にいた馬の数。上がり能力はそれまでの成績（DB 内, 同じ芝ダ, 近3走）。すべてレース前に分かる情報。",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "## 予想ペースと実際のペース（テン3Fがコース平均より0.5秒以上遅い=スロー / 速い=ハイ）", "",
         "| 芝ダ | 予想 | 実際スロー | 実際平均 | 実際ハイ | レース数 |", "|---|---|---|---|---|---|"]
    for k in sorted(acc):
        n = sum(acc[k].values())
        L.append(f"| {k[0]} | {k[1]} | " + " | ".join(f"{acc[k][a] / n * 100:.0f}%" for a in ("実際スロー", "実際平均", "実際ハイ")) + f" | {n} |")
    for typ in ("予想", "結果"):
        L += ["", f"## {'レース前の予想ペース' if typ == '予想' else '実際のペース（参考: ペースが当たったときの上限）'} × 上がり能力", "",
              "| 芝ダ | ペース | 能力 | 区分 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|---|"]
        for k in sorted(x for x in agg if x[0] == typ):
            A = agg[k]
            if min(x[0] for x in A) < 40:
                continue
            ae = [x[1] / x[2] for x in A]
            L.append(f"| {k[1]} | {k[2]} | {k[3]} | {mark(ae)}{k[4]} | {k[5]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                     + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "pace_l3_predict.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
