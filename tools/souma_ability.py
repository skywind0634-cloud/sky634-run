"""双馬 第1章（p43-51）: 苦手ローテでの善戦・好走の定義（人気より上の5着以内＋上がり3位以内）・延長が得意な血統リストの検証（2026-10-15）.
1) 前走のローテ × 前走の内容（本の好走 / 人気より上の5着以内だが上がり4位以下 / 上がり3位以内だが着順は人気以下 / 凡走）→ 今回のローテ × 人気帯
2) その馬の過去の短縮・延長での本の好走（3回に1回以上）からの「短縮型・延長型」× 今回ローテ
3) 苦手ローテでの善戦: 本の延長得意血統でない馬が延長で人気より上の5着以内 → 次走（短縮/同距離/延長）
4) 延長が得意な血統リスト（父・母父・5代の祖先）× 延長 / 短縮 × 芝ダ × 2-3歳/4歳以上、延長での上がり3位以内率
5) 本のリストに頼らない全種牡馬の延長 A/E（100走以上）: 延長が得意/苦手な現役種牡馬の発掘（2021-24で選んで2025-26で確認）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。前走は DB 内（7R以降・未勝利除く）の同じ芝ダの前走。
使い方: python3 tools/souma_ability.py [ped5_full.json] → docs/analysis/souma_ability.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT_SIRES = {"アイルハヴアナザー", "ウォーエンブレム", "エンパイアメーカー", "オレハマッテルゼ", "キャプテンスティーヴ", "キンシャサノキセキ", "ゴールドシップ",
             "コンデュイット", "スズカマンボ", "チーフベアハート", "チチカステナンゴ", "ディープスカイ", "デュランダル", "ドリームジャーニー", "ネオユニヴァース",
             "ノヴェリスト", "ハーツクライ", "ハービンジャー", "フォーティナイナーズサン", "ホワイトマズル", "マリエンバード", "メイショウサムソン", "ヨハネスブルグ", "ワークフォース"}
EXT_DS = {"アサティス", "エルコンドルパサー", "オジジアン", "クロコルージュ", "コマンダーインチーフ", "スキャターザゴールド", "ホワイトマズル", "ミシル", "メジロマックイーン",
          "El Corredor", "エルコレドール", "Forestry", "フォレストリー", "Fusaichi Pegasus", "フサイチペガサス", "Marquetry", "マーケトリー", "Monsun", "モンズン"}
EXT_ANC = {"Affirmed": {"Affirmed", "アファームド"}, "Chief's Crown": {"Chief's Crown", "チーフズクラウン"},
           "Damascus": {"Damascus", "ダマスカス"}, "Silver Hawk": {"Silver Hawk", "シルヴァーホーク"}}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def rot(a, b):
    dd = a - b
    return "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main(pedpath=None):
    ped = {}
    if pedpath and Path(pedpath).exists():
        for hid, names in json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"].items():
            s = set(n for n in names if n)
            ped[hid] = {k for k, v in EXT_ANC.items() if s & v}
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, su, dist, pay in c.execute("select race_id,date,surface,distance,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, su=su, dist=dist or 1600, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, age, l3, sire, ds in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.age,r.last3f,h.sire,h.damsire from results r left join horses h using(horse_id) "
            "where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, age=age or 9, l3=l3, sire=sire, ds=ds))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = defaultdict(list)  # hid -> [(su, dist, rot, fin, pop, l3rank)]
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        l3s = sorted(x["l3"] for x in rows[rid] if x["l3"])
        for x in rows[rid]:
            x["l3r"] = (l3s.index(x["l3"]) + 1) if x["l3"] else 99
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h[0] == su]
            K = []
            pb = pband(x["pop"])
            sp = x["sire"] in EXT_SIRES; dp = x["ds"] in EXT_DS; ap = ped.get(x["hid"], set())
            ext_blood = sp or dp or bool(ap)
            r1 = rot(R["dist"], H[-1][1]) if H else None
            if H:
                p_ = H[-1]
                if p_[2]:
                    good_rank = p_[3] <= 5 and p_[3] < p_[4]
                    kind = ("本の好走（人気より上の5着以内＋上がり3位以内）" if good_rank and p_[5] <= 3 else "人気より上の5着以内・上がり4位以下" if good_rank
                            else "上がり3位以内・着順は人気以下" if p_[5] <= 3 else "その他")
                    K.append(("①前走ローテ×前走の内容→今回", f"{su}・前走{p_[2]}で{kind}→今回{r1}", pb))
                    # ③苦手ローテでの善戦（延長得意血統でない馬の延長）
                    if p_[2] == "延長" and good_rank and not ext_blood:
                        K.append(("③苦手ローテ（延長得意血統以外の延長）で人気より上の5着以内→次走", f"{su}・今回{r1}", pb))
                    if p_[2] == "短縮" and good_rank and ext_blood:
                        K.append(("③苦手ローテ（延長得意血統の短縮）で人気より上の5着以内→次走", f"{su}・今回{r1}", pb))
                # ②その馬の短縮型・延長型
                cnt = {"短縮": [0, 0], "延長": [0, 0]}
                for h in H:
                    if h[2] in cnt:
                        cnt[h[2]][0] += 1; cnt[h[2]][1] += h[3] <= 5 and h[3] < h[4] and h[5] <= 3
                sk = cnt["短縮"][0] and cnt["短縮"][1] * 3 >= cnt["短縮"][0]
                ek = cnt["延長"][0] and cnt["延長"][1] * 3 >= cnt["延長"][0]
                if cnt["短縮"][0] or cnt["延長"][0]:
                    t = "短縮も延長も好走あり" if sk and ek else "短縮型（短縮で3回に1回以上好走）" if sk else "延長型（延長で3回に1回以上好走）" if ek else "どちらも好走なし"
                    K.append(("②その馬のローテ型（本の好走基準）×今回", f"{su}・{t}→今回{r1}", pb))
            # ④延長得意の血統リスト
            if r1 in ("延長", "短縮"):
                ag = "2-3歳" if x["age"] <= 3 else "4歳以上"
                if sp:
                    K.append(("④父が本の延長得意リスト", f"{su}・{r1}・{ag}", "全体"))
                if dp:
                    K.append(("④母父が本の延長得意リスト", f"{su}・{r1}・{ag}", "全体"))
                for a in sorted(ap):
                    K.append((f"④5代に{a}", f"{su}・{r1}", "全体"))
                if not ext_blood:
                    K.append(("④延長得意の血なし（比較用）", f"{su}・{r1}・{ag}", "全体"))
                if r1 == "延長" and ext_blood:
                    K.append(("④延長得意血統×延長×人気帯", f"{su}", pb))
            for k in K:
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0); a[5] += x["l3r"] <= 3
            # ⑤全種牡馬スキャン用
            if r1 and x["sire"]:
                a = agg[("⑤", x["sire"], su, r1)][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0); a[5] += x["l3r"] <= 3
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h[0] == su]
            hist[x["hid"]].append((su, R["dist"], rot(R["dist"], H[-1][1]) if H else None, x["fin"], x["pop"], x["l3r"]))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""

    L = ["# 双馬 第1章（p43-51）苦手ローテでの善戦・好走の定義・延長得意血統の検証（自動生成 tools/souma_ability.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。前走は DB 内の同じ芝ダの前走。",
         "- 本の好走＝人気より上の着順で5着以内、かつ上がり3位以内。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。上3F率＝上がり3位以内の割合。", "",
         "| 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 | 上3F率 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(x for x in agg if x[0] != "⑤"):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {mark(ae)}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[5]/x[0]*100:.0f}" for x in A) + "% |")
    # ⑤ 全種牡馬: 2021-24 の延長A/E と 短縮A/E の差で選び、2025-26 で同じ向きか
    L += ["", "## ⑤本のリストに頼らない全種牡馬スキャン（延長 − 短縮 の A/E 差。2021-24 で各100走以上・差0.15以上を選び、2025-26 で確認）", "",
          "| 種牡馬 | 芝ダ | 本のリスト | 延長A/E 21-24→25-26 | 短縮A/E 21-24→25-26 | 25-26延長走数 | 同じ向き |", "|---|---|---|---|---|---|---|"]
    same = tot = 0
    out = {}
    sires = {(k[1], k[2]) for k in agg if k[0] == "⑤"}
    for s, su in sorted(sires):
        e, sh = agg[("⑤", s, su, "延長")], agg[("⑤", s, su, "短縮")]
        def ae(A, idx):
            n = sum(A[i][1] for i in idx); x = sum(A[i][2] for i in idx); m = sum(A[i][0] for i in idx)
            return (n / x if x else None), m
        e1, en1 = ae(e, (0, 1)); s1, sn1 = ae(sh, (0, 1)); e2, en2 = ae(e, (2,)); s2, sn2 = ae(sh, (2,))
        if en1 < 100 or sn1 < 100 or e1 is None or s1 is None or abs(e1 - s1) < 0.15 or en2 < 30 or sn2 < 30:
            continue
        ok = (e2 - s2) * (e1 - s1) > 0; tot += 1; same += ok
        out[f"{s}|{su}"] = dict(ext=[round(e1, 2), round(e2, 2)], short=[round(s1, 2), round(s2, 2)], same=ok)
        L.append(f"| {s} | {su} | {'○' if s in EXT_SIRES else ''} | {e1:.2f}→{e2:.2f} | {s1:.2f}→{s2:.2f} | {en2} | {'○' if ok else '×'} |")
    L.append(f"\n同じ向き: {same}/{tot}")
    (ROOT / "docs" / "analysis" / "souma_ability.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "souma_ext_sires.json").write_text(json.dumps({"_meta": "tools/souma_ability.py ⑤ 延長と短縮のA/E（2021-24, 2025-26）", "sires": out},
                                                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
