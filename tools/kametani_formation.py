"""亀谷敬正『血統ビーム一発レッスン vol.2』の 3連複フォーメーション＋均等払い戻しの資金配分を、こちらのフラグ馬で再現する（2026-11-08 ユーザー提供）.
1列目＝本命（ここではフラグ点の上位の人気薄）、2列目＝1〜4番人気、3列目＝5番人気以下（1列目以外）。
資金配分: 各組の「推定オッズ」に反比例して賭け、どれが当たっても払戻がそろうようにする（スマート出馬表の「仮払戻額均等配分」）。
過去の全組み合わせの3連複オッズはDBに無いので、推定オッズ＝0.775 ÷（単勝オッズから出した勝率で Harville 式の3着内の組の確率）とし、
当たった組は実際の配当で払い戻す。1レース1万円（100円単位に丸め、最低100円）と均等買い（1点100円）を比べる。
使い方: python3 tools/kametani_formation.py [ROWS_SFX]  → docs/analysis/kametani_formation.md"""
import itertools, json, os, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import flag_ticket_search as F  # noqa: E402

TAKE = 0.775
_TRIO = None


def real_trio(rid):
    """JRA の最終オッズ（sky634-run の odds ブランチ → data/cache/odds/<YYYYMM>.json.gz）の3連複。無ければ None."""
    global _TRIO
    if _TRIO is None:
        import gzip
        _TRIO = {}
        for f in sorted((ROOT / "data" / "cache" / "odds").glob("*.json.gz")):
            try:
                for k, v in json.load(gzip.open(f)).items():
                    if v.get("trio"):
                        _TRIO[k] = v["trio"]
            except (OSError, ValueError):
                pass
    return _TRIO.get(rid)


def harville_trio(p, a, b, c):
    tot = 0.0
    for x, y, z in itertools.permutations((a, b, c)):
        px = p[x]; py = p[y] / max(1 - px, 1e-9); pz = p[z] / max(1 - p[x] - p[y], 1e-9)
        tot += px * py * pz
    return tot


def run(races, T, X, budget=10000, filt=None):
    agg = defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # races, eq_bet, eq_ret, alloc_bet, alloc_ret, hit
    for r in races:
        hs = [h for h in r["horses"] if h["odds"] and h["odds"] > 0]
        if len(hs) < 8:
            continue
        cand = sorted((h for h in hs if h["sc"] >= T and h["odds"] >= X), key=lambda h: (-h["sc"], h["odds"]))
        if not cand:
            continue
        top4 = sorted(hs, key=lambda h: h["pop"])[:4]
        if filt and not filt(r, top4):
            continue
        ax = cand[0]
        if ax in top4:
            continue
        inv = {h["num"]: 1 / h["odds"] for h in hs}; s = sum(inv.values()); p = {k: v / s for k, v in inv.items()}
        rest = [h["num"] for h in hs if h["num"] != ax["num"] and h not in top4]
        combos = [tuple(sorted((ax["num"], t["num"], o))) for t in top4 for o in rest]
        est = {cb: TAKE / max(harville_trio(p, *cb), 1e-9) for cb in combos}
        rt = real_trio(r["rid"]) if os.environ.get("REAL") == "1" else None
        if os.environ.get("REAL") == "1":
            if not rt:
                continue
            est = {cb: rt.get(F.K(cb)) for cb in combos}
            if any(v is None or v <= 0 for v in est.values()):
                est = {cb: (v if v and v > 0 else 99999.0) for cb, v in est.items()}  # 取消など
        w = {cb: 1 / est[cb] for cb in combos}; ws = sum(w.values())
        stake = {cb: max(100, round(budget * w[cb] / ws / 100) * 100) for cb in combos}
        pay3 = r["pay"]["3連複"]
        hitk = next((cb for cb in combos if F.K(cb) in pay3), None)
        eq_ret = pay3.get(F.K(hitk), 0) if hitk else 0
        al_ret = pay3.get(F.K(hitk), 0) * stake[hitk] // 100 if hitk else 0
        for k in (F.period(r["date"]), "全体"):
            a = agg[k]
            a[0] += 1; a[1] += 100 * len(combos); a[2] += eq_ret; a[3] += sum(stake.values()); a[4] += al_ret; a[5] += hitk is not None
    return agg


def main():
    races = F.load()
    L = ["# 亀谷式 3連複フォーメーション＋均等払い戻し（tools/kametani_formation.py, 2026-11-08）", "",
         "1列目＝フラグ点の上位（単勝X倍以上・フラグ点T以上の1頭）、2列目＝1〜4番人気、3列目＝5番人気以下。均等買い（1点100円）と、推定オッズに反比例した資金配分（1レース1万円）を比べる。",
         f"フラグの行: flag_backtest_rows{os.environ.get('ROWS_SFX', '_items')}.json", "",
         "| T | X | 絞り込み | 期間 | レース | 的中率 | 均等買いの回収 | 資金配分の回収 |", "|---|---|---|---|---|---|---|---|"]
    filters = {"なし": None,
               "1〜4番人気のフラグ点合計≤0（人気馬が飛びそう）": lambda r, t4: sum(h["sc"] for h in t4) <= 0,
               "1番人気2.5倍以上": lambda r, t4: min(h["odds"] for h in t4) >= 2.5}
    for T in (3, 4, 5, 6):
        for X in (5, 10):
            for fn, f in filters.items():
                agg = run(races, T, X, filt=f)
                for k in F.PER + ("全体",):
                    a = agg.get(k)
                    if not a or not a[0]:
                        continue
                    L.append(f"| +{T} | {X}倍 | {fn} | {k} | {a[0]} | {a[5] / a[0]:.0%} | {a[2] / a[1]:.0%} | {a[4] / a[3]:.0%} |")
    (ROOT / "docs" / "analysis" / f"kametani_formation{os.environ.get('ROWS_SFX', '')}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__" and (len(sys.argv) < 2 or sys.argv[1] != "ten"):
    main()


# ---- chapter3: テンT（前半の速さの順位）フォーメーション ----
def early_rank_time(races):
    """テンT（実際のタイム版, 2026-11-08 ユーザー「タイムも結果欄にある」）: 過去の各走の テン3F ≒ そのレースの前半3F（ラップ）
    − 同じコース・芝ダ・距離の前半3Fの平均（速い流れほどマイナス）＋ 0.12秒 ×（1角の位置−1）。近3走の平均でレース内順位（小さいほど速い）."""
    import sqlite3
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    std = {}
    for co, su, d, f3 in c.execute("select course,surface,distance,avg(first3f) from races where first3f is not null group by 1,2,3"):
        std[(co, su, d)] = f3
    rows = c.execute("""select r.date, x.race_id, x.horse_id, x.number, x.passing, r.course, r.surface, r.distance, r.first3f
        from results x join races r on r.race_id=x.race_id order by r.date""").fetchall()
    hist = defaultdict(list); avg = {}
    for d, rid, hid, num, pas, co, su, dist, f3 in rows:
        pr = hist[hid][-3:]
        avg[(rid, num)] = sum(pr) / len(pr) if pr else None
        try:
            pos = int(str(pas).split("-")[0])
            if f3 and std.get((co, su, dist)):
                hist[hid].append(f3 - std[(co, su, dist)] + 0.12 * (pos - 1))
        except (ValueError, TypeError):
            pass
    out = {}
    for r in races:
        v = sorted((avg.get((r["rid"], h["num"])), h["num"]) for h in r["horses"] if avg.get((r["rid"], h["num"])) is not None)
        out[r["rid"]] = {num: i + 1 for i, (a, num) in enumerate(v)}
    return out


def early_rank(races):
    if os.environ.get("TEN") == "time":
        return early_rank_time(races)
    """各レース・各馬の「近3走の1角の位置（前からの割合）の平均」→ レース内の順位（小さいほど前に行く＝テンTの代わり）."""
    import sqlite3
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    rows = c.execute("""select r.date, x.race_id, x.horse_id, x.number, x.passing,
        (select count(*) from results y where y.race_id=x.race_id) from results x join races r on r.race_id=x.race_id order by r.date""").fetchall()
    hist = defaultdict(list); avg = {}
    for d, rid, hid, num, pas, n in rows:
        pr = hist[hid][-3:]
        avg[(rid, num)] = sum(pr) / len(pr) if pr else None
        try:
            hist[hid].append(int(str(pas).split("-")[0]) / max(n, 1))
        except (ValueError, TypeError):
            pass
    out = {}
    for r in races:
        v = [(avg.get((r["rid"], h["num"])), h["num"]) for h in r["horses"]]
        v = sorted((a, num) for a, num in v if a is not None)
        out[r["rid"]] = {num: i + 1 for i, (a, num) in enumerate(v)}
    return out


def run_ten(races, ranks, T, X, budget=10000, n2=3, n3=9):
    agg = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    for r in races:
        hs = [h for h in r["horses"] if h["odds"] and h["odds"] > 0]
        rk = ranks.get(r["rid"], {})
        if len(hs) < 8 or len(rk) < 0.7 * len(hs):
            continue
        cand = sorted((h for h in hs if h["sc"] >= T and h["odds"] >= X), key=lambda h: (-h["sc"], h["odds"]))
        if not cand:
            continue
        ax = cand[0]["num"]
        order = [num for num, k in sorted(rk.items(), key=lambda x: x[1]) if num != ax]
        col2, col3 = order[:n2], order[:n3]
        combos = sorted({tuple(sorted((ax, a, b))) for a in col2 for b in col3 if a != b})
        if not combos:
            continue
        inv = {h["num"]: 1 / h["odds"] for h in hs}; s = sum(inv.values()); p = {k: v / s for k, v in inv.items()}
        est = {cb: TAKE / max(harville_trio(p, *cb), 1e-9) for cb in combos}
        rt = real_trio(r["rid"]) if os.environ.get("REAL") == "1" else None
        if os.environ.get("REAL") == "1":
            if not rt:
                continue
            est = {cb: rt.get(F.K(cb)) for cb in combos}
            if any(v is None or v <= 0 for v in est.values()):
                est = {cb: (v if v and v > 0 else 99999.0) for cb, v in est.items()}  # 取消など
        w = {cb: 1 / est[cb] for cb in combos}; ws = sum(w.values())
        stake = {cb: max(100, round(budget * w[cb] / ws / 100) * 100) for cb in combos}
        pay3 = r["pay"]["3連複"]
        hitk = next((cb for cb in combos if F.K(cb) in pay3), None)
        eq_ret = pay3.get(F.K(hitk), 0) if hitk else 0
        al_ret = pay3.get(F.K(hitk), 0) * stake[hitk] // 100 if hitk else 0
        for k in (F.period(r["date"]), "全体"):
            a = agg[k]
            a[0] += 1; a[1] += 100 * len(combos); a[2] += eq_ret; a[3] += sum(stake.values()); a[4] += al_ret; a[5] += hitk is not None
    return agg


def main_ten():
    races = F.load(); ranks = early_rank(races)
    L = ["", "## chapter3 テンT（近3走の1角の位置の平均でレース内順位）: 1列目＝フラグ点上位1頭、2列目＝テン順位1〜3位、3列目＝1〜9位", "",
         "| T | X | 期間 | レース | 的中率 | 均等買いの回収 | 資金配分の回収 |", "|---|---|---|---|---|---|---|"]
    for T in (3, 4, 5, 6):
        for X in (1, 5, 10):
            agg = run_ten(races, ranks, T, X)
            for k in F.PER + ("全体",):
                a = agg.get(k)
                if a and a[0]:
                    L.append(f"| +{T} | {X}倍 | {k} | {a[0]} | {a[5] / a[0]:.0%} | {a[2] / a[1]:.0%} | {a[4] / a[3]:.0%} |")
    p = ROOT / "docs" / "analysis" / f"kametani_formation{os.environ.get('ROWS_SFX', '')}.md"
    p.write_text((p.read_text(encoding="utf-8") if p.exists() else "") + "\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "ten":
    main_ten()
