"""双馬 第3章 p152-153 馬場替わりの注目血統の検証（2026-10-15）.
芝→ダ替わり: 父がダート替わり得意リスト（ヴァイスリージェント系・エーピーインディ系・ゴールドアリュール・スマートファルコン・フォーティナイナー系・
  米国型ストームキャット系・ブライアンズタイム系・カネヒキリ・タートルボウル・ワイルドラッシュ）/ 母父が同リスト / どちらも無し × 人気帯、馬体重500kg以上
ダ→芝替わり: 父・母父が芝替わり得意リスト（カロ系・デインヒル系・プリンスリーギフト系・タイキシャトル・トウルビヨン・フェアリーキング・カーリアン等）× 人気帯、
  過去に芝で好走（5着以内）しているか（ジュンザワールドの例: 芝馬がダートを使われている）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。
使い方: python3 tools/surface_switch.py → docs/analysis/surface_switch.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRT_LINES = {"デピュティミニスター系", "エーピーインディ系", "ゴールドアリュール系", "フォーティナイナー系", "ストームキャット系", "ヘネシー系", "ブライアンズタイム系"}
DIRT_NAMES = {"スマートファルコン", "カネヒキリ", "タートルボウル", "ワイルドラッシュ", "アジュディケーティング", "アフリート", "ディアブロ", "Capote", "Crafty Prospector",
              "クラフティプロスペクター", "Saint Ballado", "セイントバラード"}
TURF_LINES = {"デインヒル系", "プリンスリーギフト系"}
TURF_NAMES = {"タイキシャトル", "アンバーシャダイ", "タマモクロス", "ダンシングブレーヴ", "カーリアン", "Caerleon", "コジーン", "Cozzene", "フェアリーキング", "Fairy King"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: dict(date=r[1], su=r[2], pay=json.loads(r[3]) if r[3] else {}) for r in
             c.execute("select race_id,date,surface,payouts from races where surface in ('芝','ダ')")}
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, bw, sire, ds, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.body_weight,h.sire,h.damsire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, bw=bw or 0,
                                  sd=sl in DIRT_LINES or sire in DIRT_NAMES, dd=dsl in DIRT_LINES or ds in DIRT_NAMES,
                                  st=sl in TURF_LINES or sire in TURF_NAMES, dt=dsl in TURF_LINES or ds in TURF_NAMES))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        for x in rows[rid]:
            H = hist[x["hid"]]
            if not H or H[-1][0] == su:
                continue
            pb = pband(x["pop"]); K = []
            if su == "ダ":
                tag = "父がダート替わり得意" if x["sd"] else "母父がダート替わり得意" if x["dd"] else "リストの血なし"
                K.append(("芝→ダ替わり×血統", tag, pb))
                if x["bw"]:
                    K.append(("芝→ダ替わり×馬体重", "500kg以上" if x["bw"] >= 500 else "500kg未満", pb))
            else:
                tag = "父が芝替わり得意" if x["st"] else "母父が芝替わり得意" if x["dt"] else "リストの血なし"
                K.append(("ダ→芝替わり×血統", tag, pb))
                good_turf = any(h[0] == "芝" and h[1] <= 5 for h in H)
                K.append(("ダ→芝替わり×過去の芝", "芝で5着以内あり" if good_turf else "芝で5着以内なし（芝初出走を含まず）" if any(h[0] == "芝" for h in H) else "芝初出走", pb))
            for k in K:
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for x in rows[rid]:
            hist[x["hid"]].append((su, x["fin"]))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 双馬 第3章 p152-153 馬場替わりの注目血統の検証（自動生成 tools/surface_switch.py）", "",
         "- 前走（DB 内, 7R以降・未勝利除く）と今回で芝ダが替わった馬。A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 見方 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {mark(ae)}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "surface_switch.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
