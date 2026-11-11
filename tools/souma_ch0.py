"""双馬毅『1頭の種牡馬のクセ』序章（p4-12）の検証（2026-10-15）.
1) タイキシャトル（父/母父/5代）: 距離短縮 / 延長 / 同距離、ダートの外枠（6-8枠）/内枠（1-3枠）
2) デインヒル（5代/母父デインヒル系）: ダ→芝替わり、うち前走ダートで1.0秒以上負け（惨敗）
3) トゥルビヨン系（5代にパーソロン/トゥルビヨン、または母系にメジロ・シンボリの名）: ダ→芝替わり
A/E＝3着内の実数÷人気から見込む数（単勝回収も）。発見2021-23 / 確認2024 / テスト2025-26。データは各日7R以降（未勝利除く）。
使い方: python3 tools/souma_ch0.py <ped5_full.json> → docs/analysis/souma_ch0.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DANE_L = {"デインヒル系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    P = json.loads(Path(path).read_text(encoding="utf-8")); pos = P["pos"]; H = P["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, su, dist, pay in c.execute("select race_id,date,surface,distance,payouts from races where surface in ('芝','ダ')"):
        races[rid] = (date, su, dist or 1600, json.loads(pay) if pay else {})
    base = defaultdict(lambda: [0, 0]); rows = []
    for rid, hid, fin, pop, num, gate, t, sire, ds, dsl in c.execute(
            """select r.race_id, r.horse_id, r.finish, r.popularity, r.number, r.gate, r.time_sec, h.sire, h.damsire, h.damsire_line
               from results r join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        if rid in races:
            p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
            rows.append((races[rid][0], rid, hid, fin, p, num, gate, t, sire, ds, dsl))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    rows.sort()
    win = {}
    for date, rid, hid, fin, p, num, gate, t, *_ in rows:
        if fin == 1 and t:
            win[rid] = t
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)]); last = {}
    for date, rid, hid, fin, p, num, gate, t, sire, ds, dsl in rows:
        _, su, dist, pay = races[rid]
        prev = last.get(hid)
        last[hid] = (su, dist, (t - win[rid]) if (t and rid in win) else None)
        anc = dict(zip(pos, H.get(hid) or []))
        names = set(v for v in anc.values() if v)
        dam_names = [v for k, v in anc.items() if v and k.startswith("D")]
        K = []
        taiki = "父" if sire == "タイキシャトル" else "母父" if ds == "タイキシャトル" else "5代" if "タイキシャトル" in names else None
        if taiki and prev:
            ch = "距離短縮" if dist <= prev[1] - 200 else "距離延長" if dist >= prev[1] + 200 else "同距離"
            K.append(("タイキシャトル（父・母父・5代）", f"{su}・{ch}"))
            if su == "ダ" and gate:
                K.append(("タイキシャトル（父・母父・5代）", "ダ・" + ("外枠6-8" if gate >= 6 else "内枠1-3" if gate <= 3 else "中枠4-5")))
                if dist <= prev[1] - 200 and gate >= 6:
                    K.append(("タイキシャトル（父・母父・5代）", "ダ・短縮×外枠"))
        dane = dsl in DANE_L or bool(names & {"Danehill", "デインヒル"})
        tour = bool(names & {"Partholon", "パーソロン", "Tourbillon", "トゥルビヨン"}) or any(("メジロ" in v or "シンボリ" in v) for v in dam_names)
        if prev and su == "芝":
            sw = prev[0] == "ダ"
            big = sw and prev[2] is not None and prev[2] >= 1.0
            for nm, on in (("デインヒルの血", dane), ("トゥルビヨン系・メジロ/シンボリ牝系", tour)):
                if on:
                    K.append((nm, "芝・前走ダート（芝替わり）" if sw else "芝・前走も芝"))
                    if big:
                        K.append((nm, "芝・前走ダートで1.0秒以上負け"))
        fk = {cc: y for cc, y in pay.get("複勝", [])}.get(str(num), 0); tk = {cc: y for cc, y in pay.get("単勝", [])}.get(str(num), 0)
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk; x[4] += tk
    L = ["# 双馬毅『1頭の種牡馬のクセ』序章（p4-12）の検証（自動生成 tools/souma_ch0.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 20:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ch0.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
