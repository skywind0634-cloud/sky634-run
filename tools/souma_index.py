"""双馬毅『1頭の種牡馬のクセ』索引（p13-18）の検証（2026-10-15）.
リスト: 延長得意（父/母父/血）, 短縮得意（父）, 芝替わり得意（父/母父）, ダート替わり得意（父/母父）。
各馬の距離変更（前走から±200m以上, 同じ芝ダ）と芝ダ替わりを判定し、リストの馬の A/E と回収率を、
(a)リスト全体 (b)名前ごと（各期間15走以上）で集計。比較として「リストの馬の同距離」も出す。
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。
使い方: python3 tools/souma_index.py <ped5_full.json> → docs/analysis/souma_index.md, data/knowledge/souma_index.json
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT_SIRE = ["アイルハヴアナザー", "ウォーエンブレム", "エンパイアメーカー", "オレハマッテルゼ", "キャプテンスティーヴ", "キンシャサノキセキ", "ゴールドシップ",
            "コンデュイット", "スズカマンボ", "チーフベアハート", "チチカステナンゴ", "ディープスカイ", "デュランダル", "ドリームジャーニー", "ネオユニヴァース",
            "ノヴェリスト", "ハーツクライ", "ハービンジャー", "フォーティナイナーズサン", "ホワイトマズル", "マリエンバード", "メイショウサムソン", "ヨハネスブルグ",
            "ワークフォース", "ジャスタウェイ"]
EXT_DS = ["アサティス", "エルコンドルパサー", "オジジアン", "クロコルージュ", "コマンダーインチーフ", "スキャターザゴールド", "ホワイトマズル", "ミシル",
          "メジロマックイーン", "エルコレドール", "El Corredor", "フォレストリー", "Forestry", "フサイチペガサス", "Fusaichi Pegasus", "マーケトリー", "Marquetry",
          "モンズン", "Monsun", "ディープスカイ"]
EXT_BLOOD = {"Affirmed": {"Affirmed", "アファームド"}, "Chief's Crown": {"Chief's Crown", "チーフズクラウン"}, "Damascus": {"Damascus", "ダマスカス"},
             "Silver Hawk": {"Silver Hawk", "シルヴァーホーク"}}
SHORT_SIRE = ["ヴィクトワールピサ", "オルフェーヴル", "カジノドライヴ", "サウスヴィグラス", "ダイワメジャー", "パイロ", "プリサイスエンド", "ヘニーヒューズ",
              "ブラックタイド", "ロージズインメイ", "タイキシャトル"]
TURF_SW = {"sire": ["タイキシャトル"], "sire_line": ["デインヒル系", "プリンスリーギフト系"],
           "ds": ["アンバーシャダイ", "タイキシャトル", "タマモクロス", "ダンシングブレーヴ", "Caerleon", "カーリアン"],
           "dsl": ["デインヒル系", "プリンスリーギフト系"], "blood": {"Cozzene", "コジーン", "Fairy King", "フェアリーキング", "Habitat", "ハビタット",
                                                            "Partholon", "パーソロン", "Tourbillon", "トゥルビヨン"}}
DIRT_SW = {"sire": ["ゴールドアリュール", "スマートファルコン", "タートルボウル", "カネヒキリ"],
           "sire_line": ["デピュティミニスター系", "エーピーインディ系", "フォーティナイナー系", "ヘネシー系", "テイルオブザキャット系", "フォレストリー系", "ハーランズホリデー系"],
           "ds": ["アジュディケーティング", "アフリート", "ディアブロ"], "dsl": ["デピュティミニスター系", "エーピーインディ系", "フォーティナイナー系"],
           "blood": {"Brian's Time", "ブライアンズタイム", "Wild Rush", "ワイルドラッシュ", "Saint Ballado", "セントバラード", "Capote", "カポーティ",
                     "Crafty Prospector", "クラフティプロスペクター"}}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: (r[1], r[2], r[3] or 1600, json.loads(r[4]) if r[4] else {}) for r in
             c.execute("select race_id,date,surface,distance,payouts from races where surface in ('芝','ダ')")}
    base = defaultdict(lambda: [0, 0]); rows = []
    for rid, hid, fin, pop, num, sire, sl, ds, dsl in c.execute(
            """select r.race_id, r.horse_id, r.finish, r.popularity, r.number, h.sire, h.sire_line, h.damsire, h.damsire_line
               from results r join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        if rid in races:
            p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
            rows.append((races[rid][0], rid, hid, fin, p, num, sire, sl, ds, dsl))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    rows.sort()
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); last = {}

    def add(k, pr, fin, p, fk, tk):
        x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk

    for date, rid, hid, fin, p, num, sire, sl, ds, dsl in rows:
        _, su, dist, pay = races[rid]
        prev = last.get(hid); last[hid] = (su, dist)
        if not prev:
            continue
        names = set(n for n in (H.get(hid) or []) if n)
        fk = {a: y for a, y in pay.get("複勝", [])}.get(str(num), 0); tk = {a: y for a, y in pay.get("単勝", [])}.get(str(num), 0)
        pr = per(date)
        same = prev[0] == su
        ch = None
        if same:
            ch = "延長" if dist >= prev[1] + 200 else "短縮" if dist <= prev[1] - 200 else "同距離"
        # 延長得意
        tags = []
        if sire in EXT_SIRE:
            tags.append(("延長得意（父）", sire))
        if ds in EXT_DS:
            tags.append(("延長得意（母父）", ds))
        for nm, s in EXT_BLOOD.items():
            if names & s:
                tags.append(("延長得意（血）", nm))
        if ch:
            for grp, nm in tags:
                add((grp, "全体", su, ch), pr, fin, p, fk, tk); add((grp, nm, su, ch), pr, fin, p, fk, tk)
            if sire in SHORT_SIRE:
                add(("短縮得意（父）", "全体", su, ch), pr, fin, p, fk, tk); add(("短縮得意（父）", sire, su, ch), pr, fin, p, fk, tk)
        # 芝替わり/ダート替わり
        for label, L, tgt in (("芝替わり得意", TURF_SW, "芝"), ("ダート替わり得意", DIRT_SW, "ダ")):
            if su != tgt:
                continue
            hit = []
            if sire in L["sire"] or sl in L["sire_line"]:
                hit.append(f"父{sire if sire in L['sire'] else sl}")
            if ds in L["ds"] or dsl in L["dsl"]:
                hit.append(f"母父{ds if ds in L['ds'] else dsl}")
            if names & L["blood"]:
                hit.append("血")
            if hit:
                cond = "替わり" if not same else "前走も同じ"
                add((label, "全体", tgt, cond), pr, fin, p, fk, tk)
                for h in hit:
                    add((label, h, tgt, cond), pr, fin, p, fk, tk)
    out = []
    Lines = ["# 双馬毅『1頭の種牡馬のクセ』索引（p13-18）の検証（自動生成 tools/souma_index.py）", "",
             "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。距離変更は同じ芝ダで前走から±200m以上。",
             "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。名前ごとは各期間15走以上。", "",
             "| リスト | 名前 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg, key=lambda k: (k[0], k[1] != "全体", k[1], k[2], k[3])):
        A = agg[k]
        if min(x[0] for x in A) < 15:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        Lines.append(f"| {k[0]} | {k[1]} | {m}{k[2]}・{k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                     + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
        if m and k[1] != "全体":
            out.append({"list": k[0], "name": k[1], "surface": k[2], "cond": k[3], "mark": m, "ae": [round(v, 2) for v in ae], "n": [x[0] for x in A]})
    (ROOT / "docs" / "analysis" / "souma_index.md").write_text("\n".join(Lines) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "souma_index.json").write_text(json.dumps({"_meta": "tools/souma_index.py", "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(Lines))


if __name__ == "__main__":
    main(sys.argv[1])
