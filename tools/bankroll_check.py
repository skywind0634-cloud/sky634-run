"""◎厳格（本命枠）を毎週買い続けたとき、資金がいくら要るか（2026-10-24, ユーザー「1年持つ資金がいるだろ」）.
過去1年（data/cache/strategy_backtest.json・実払戻）で、1点100円のときの最大の落ち込み（ドローダウン）・最長連敗・
週ごとの収支（プラスの週の割合・最悪の週）を出す。10点に絞った形（単勝＋ワイド1〜3人気＋馬連1人気＋3連複 軸-1〜2人気-モデル上位）も比べる。
使い方: python3 tools/bankroll_check.py
"""
import datetime as dt, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.strategy import payout  # noqa: E402

races = json.load(open(ROOT / "data" / "cache" / "strategy_backtest.json"))


def pkg(r, trim):
    fav = {h["pop"]: h["num"] for h in r["horses"]}
    out = []
    for a in [h for h in r["horses"] if h["pop"] >= 4 and h["seg"]]:
        n = a["num"]
        top = [h["num"] for h in sorted((h for h in r["horses"] if h["num"] != n), key=lambda h: -h["p"])[:5]]
        w = [("ワイド", tuple(sorted((n, fav[p])))) for p in range(1, 6) if p in fav and fav[p] != n]
        u = [("馬連", tuple(sorted((n, fav[p])))) for p in range(1, 4) if p in fav and fav[p] != n]
        t = [("三連複", tuple(sorted((n, b, c)))) for b in [fav[p] for p in (1, 2) if p in fav and fav[p] != n] for c in top if c not in (n, b)]
        t = list(dict.fromkeys(t))
        out += [("単勝", (n,))] + (w[:3] + u[:1] + t[:5] if trim else w + u + t)
        if trim:
            break
    return list(dict.fromkeys(out))


def week(d):
    x = dt.date.fromisoformat(d)
    return (x - dt.timedelta(days=(x.weekday() - 5) % 7)).isoformat()


def run(trim):
    bal = peak = 0; mdd = 0; streak = mx = 0; wk = defaultdict(int); n = cost = back = 0
    for r in sorted(races, key=lambda r: r["date"]):
        T = pkg(r, trim)
        if not T:
            continue
        c = 100 * len(T); b = sum(payout(k, h, r["pay"]) for k, h in T)
        n += 1; cost += c; back += b; bal += b - c; wk[week(r["date"])] += b - c
        peak = max(peak, bal); mdd = max(mdd, peak - bal)
        streak = 0 if b > c else streak + 1; mx = max(mx, streak)
    ws = list(wk.values())
    # 週ごとの累計の最悪（連続した負け週の合計）
    run_ = worst = 0
    for v in ws:
        run_ = min(0, run_ + v); worst = min(worst, run_)
    return dict(races=n, pts=cost / 100 / max(n, 1), roi=back / cost, bal=bal, mdd=mdd, lose_streak=mx, weeks=len(ws),
                plus_weeks=sum(v > 0 for v in ws), worst_week=min(ws), worst_run=worst)


def main():
    out = ["# 本命枠（◎厳格）を1年買い続けたときの資金（1点100円）", "",
           "収支マイナスのレースが続いた最長（最長連敗）は「払戻が投資を下回ったレース」で数える。", "",
           "| 形 | レース数 | 1レース点数 | 回収率 | 1年の収支 | 最大の落ち込み | 最長連敗 | プラスの週 | 最悪の週 | 負け週が続いた最悪 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, trim in (("全部（約19点）", False), ("10点に絞る", True)):
        s = run(trim)
        out.append(f"| {name} | {s['races']} | {s['pts']:.1f} | {s['roi']:.0%} | {s['bal']:+,}円 | {s['mdd']:,}円 | {s['lose_streak']} | "
                   f"{s['plus_weeks']}/{s['weeks']} | {s['worst_week']:+,}円 | {s['worst_run']:+,}円 |")
    (ROOT / "docs" / "analysis" / "bankroll_check.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
