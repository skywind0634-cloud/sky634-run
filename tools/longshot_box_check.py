"""人気薄のフラグ馬同士のボックス（2026-11-08 アルゼンチン共和国杯 6→15→12（17・14・11番人気、フラグ点+5・+6・+8）を
「相手は1〜3番人気」の買い方ですべて取り逃がした反省・ユーザー「こういうのを取らないとだめなんだよ」）.
data/cache/flag_backtest_rows_items.json（5年分・馬ごとの材料）と DB の単勝オッズ・払戻で、
「単勝 X倍以上でフラグ点 T以上の馬が K頭以上いるレースで、その馬たち（フラグ点の上位5頭まで）のワイドボックス・3連複ボックス」を
2021-23 / 2024 / 2025-01〜26-09 / 実戦2026-10〜 で比べる。フラグ点は今の flag_marks と同じく flag_weights.json の excluded を数えない。
使い方: python3 tools/longshot_box_check.py → docs/analysis/longshot_box_check.md"""
import itertools, json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOD, BAD = ("○", "◎"), ("×", "▽", "▼")


def load():
    ex = set(json.load(open(ROOT / "data" / "knowledge" / "flag_weights.json")).get("excluded", []))
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows_items.json"))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = defaultdict(list)
    for r in rows:
        sc = 0
        for name, mk in r.get("flags") or []:
            if f"{name}|{mk}" in ex:
                continue
            sc += 1 if mk in GOOD else -1 if mk in BAD else 0
        races[r["rid"]].append((r["pop"], r["fin"], sc, r["date"]))
    out = []
    for rid, hs in races.items():
        res = {p: (num, odds) for num, p, odds in c.execute("select number,popularity,odds from results where race_id=?", (rid,)) if p}
        pay = c.execute("select payouts,grade from races where race_id=?", (rid,)).fetchone()
        if not res or not pay or not pay[0]:
            continue
        pj = json.loads(pay[0])
        horses = []
        for p, fin, sc, d in hs:
            if p in res and fin:
                horses.append(dict(num=res[p][0], pop=p, odds=res[p][1] or 0, fin=fin, sc=sc))
        out.append(dict(rid=rid, date=hs[0][3], grade=pay[1], n=len(horses), horses=horses,
                        wide={k: v for k, v in pj.get("ワイド", [])}, trio={k: v for k, v in pj.get("3連複", [])}))
    return out


def period(d):
    return "2021-23" if d < "2024" else "2024" if d < "2025" else "2025-26/9" if d < "2026-10" else "実戦10月〜"


def key(nums):
    return "-".join(map(str, sorted(nums)))


def run(races, T, X, K, top=5):
    agg = defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0, 0])  # races, wbet, wret, tbet, tret, hit_any, hit_trio, top3_in_box(>=2)
    for r in races:
        cand = sorted((h for h in r["horses"] if h["sc"] >= T and h["odds"] >= X), key=lambda h: (-h["sc"], h["odds"]))[:top]
        if len(cand) < K:
            continue
        nums = [h["num"] for h in cand]
        ws = [key(p) for p in itertools.combinations(nums, 2)]
        ts = [key(p) for p in itertools.combinations(nums, 3)]
        wr = sum(r["wide"].get(k, 0) for k in ws); tr = sum(r["trio"].get(k, 0) for k in ts)
        for pk in (period(r["date"]), "全体"):
            a = agg[pk]
            a[0] += 1; a[1] += 100 * len(ws); a[2] += wr; a[3] += 100 * len(ts); a[4] += tr; a[5] += (wr + tr) > 0; a[6] += tr > 0
    return agg


PER = ("2021-23", "2024", "2025-26/9", "実戦10月〜")


def main():
    races = load()
    L = ["# 人気薄のフラグ馬同士のボックス（tools/longshot_box_check.py, 2026-11-08）", "",
         "11/8 アルゼンチン共和国杯 6→15→12（17・14・11番人気、フラグ点+5・+6・+8）を、相手を1〜3番人気に限る買い方で全部取り逃がした反省。",
         "条件: 単勝X倍以上でフラグ点T以上の馬がK頭以上 → フラグ点の上位5頭まででワイドボックス＋3連複ボックス（1点100円）。",
         "フラグは2021-26で選んだもの（学習2021-24・確認2025-26）なので、2025-26/9 と 実戦10月〜 を重く見る。", "",
         "| T（フラグ点） | X（単勝） | K（頭数） | 期間 | レース数 | ワイド回収 | 3連複回収 | 合計回収 | 1点でも的中 | 3連複的中 | 1日あたりのレース |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    days = defaultdict(set)
    for r in races:
        days[period(r["date"])].add(r["date"])
    best = []
    for T in (4, 5, 6):
        for X in (10, 15, 20, 30):
            for K in (3, 4):
                agg = run(races, T, X, K)
                rec = []
                for pk in PER + ("全体",):
                    a = agg.get(pk)
                    if not a or not a[0]:
                        L.append(f"| +{T} | {X}倍 | {K} | {pk} | 0 | - | - | - | - | - | - |"); rec.append(None); continue
                    tot = (a[2] + a[4]) / max(a[1] + a[3], 1)
                    nd = len(days[pk]) if pk in days else sum(len(v) for v in days.values())
                    L.append(f"| +{T} | {X}倍 | {K} | {pk} | {a[0]} | {a[2] / max(a[1], 1):.0%} | {a[4] / max(a[3], 1):.0%} | {tot:.0%} | "
                             f"{a[5] / a[0]:.0%} | {a[6] / a[0]:.1%} | {a[0] / max(nd, 1):.2f} |")
                    rec.append(tot)
                best.append(((T, X, K), rec, agg))
    L += ["", "## 期間ごとの合計回収（ワイド＋3連複）", "", "| 条件 | 2021-23 | 2024 | 2025-26/9 | 実戦10月〜 | レース数（全体） | 全期間100%超 |", "|---|---|---|---|---|---|---|"]
    for (T, X, K), rec, agg in best:
        ok = all(v is not None and v >= 1.0 for v in rec[:3])
        L.append(f"| +{T}・{X}倍以上・{K}頭以上 | " + " | ".join("-" if v is None else f"{v:.0%}" for v in rec[:4])
                 + f" | {agg['全体'][0] if '全体' in agg else 0} | {'○' if ok else ''} |")
    (ROOT / "docs" / "analysis" / "longshot_box_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[L.index("## 期間ごとの合計回収（ワイド＋3連複）"):]))


if __name__ == "__main__":
    main()
