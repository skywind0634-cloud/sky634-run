"""レース別シートに出る材料（★血統穴・走る条件・妙味条件・牝系・専門家・本の検証・種牡馬クセ など）ごとの成績（2026-10-25, ユーザー指示）.
本番と同じ evaluate_race → digest.text → tools/race_sheet.py の行の形で、過去1年（2025-10〜2026-09, 学習・集計はその前のデータだけ）の各レースの材料を作り直し、
材料ごとに 3着内率・A/E・単複回収率と、二桁人気の5着以内（A/E）を出す。
出力: data/cache/tag_rows.json, docs/analysis/tag_backtest.md
使い方: python3 tools/tag_backtest.py [並列数]
"""
import io, json, os, re, shutil, sqlite3, sys, tempfile
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_connect = sqlite3.connect
sqlite3.connect = lambda *a, **k: _connect(*a, **{**k, "timeout": 300})  # 並列の書き込み待ち（db.connect の DELETE で database is locked になるため）
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
START, END = "2025-10-01", "2026-09-30"
LINE = re.compile(r"^\s+(\d+) (\S+?)（(\d+)人気・[\d.]+倍）(?: ★買う:\S+)?｜(.*)$")


def run(args):
    start, end, before = args
    from keiba import analysis, db, digest, report
    from keiba.model import evaluate_race
    from keiba.validate import race_cards, _learn_before
    import race_sheet
    conn = db.connect()
    st = analysis.build_stats(conn, before=before)
    _learn_before(conn, before)
    out = []
    for card, fin, pay in race_cards(conn, start, end):
        if not all(e.get("popularity") for e in card["entries"]) or not all(e.get("_odds") for e in card["entries"]):
            continue
        for e in card["entries"]:
            e["odds"] = e["_odds"]
        try:
            ev = evaluate_race(card, st, conn, n_sims=0)
            txt = digest.text(card, ev, report.race_title(card))
        except Exception:  # noqa: BLE001
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(txt); p = f.name
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                race_sheet.main(p)
        finally:
            os.unlink(p)
        tags = {}
        for l in buf.getvalue().splitlines():
            m = LINE.match(l)
            if m:
                tags[int(m.group(1))] = [t for t in m.group(4).split("・") if t]
        fk = {a: y for a, y in pay.get("複勝", [])}; tk = {a: y for a, y in pay.get("単勝", [])}
        for h in ev:
            out.append(dict(date=card["date"], rid=card["race_id"], num=h.number, pop=h.pop_rank, odds=h.odds, fin=fin.get(h.number),
                            n=len(ev), tags=tags.get(h.number, []), tan=tk.get(str(h.number), 0), fuku=fk.get(str(h.number), 0)))
    return out


def collect(workers):
    import datetime as dt
    from multiprocessing import Pool
    from keiba import db, value as V
    conn = db.connect()
    bak = V.COND_PATH.with_suffix(".bak")
    if V.COND_PATH.exists() and not bak.exists():
        shutil.copy(V.COND_PATH, bak)
    try:
        V.build_cond([r for r in V.load(conn) if r["date"] < START])
        d0, d1 = dt.date.fromisoformat(START), dt.date.fromisoformat(END)
        chunks, d = [], d0
        while d <= d1:
            e = min(d + dt.timedelta(days=13), d1)
            chunks.append((d.isoformat(), e.isoformat(), START)); d = e + dt.timedelta(days=1)
        with Pool(workers) as pool:
            parts = pool.map(run, chunks, chunksize=1)
    finally:
        if bak.exists():
            shutil.move(bak, V.COND_PATH)
    rows = [r for p in parts for r in p]
    json.dump(rows, open(ROOT / "data" / "cache" / "tag_rows.json", "w"), ensure_ascii=False)
    return rows


def base_tag(t):
    return re.sub(r"[◎○×▽▼]+$", "", t).replace("過信禁物(消しではない)", "過信禁物")


def report_(rows):
    rows = [r for r in rows if r["fin"] and r["pop"]]
    b3, b5 = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        p = min(r["pop"], 16)
        b3[p][0] += 1; b3[p][1] += r["fin"] <= 3; b5[p][0] += 1; b5[p][1] += r["fin"] <= 5
    e3 = {k: v[1] / v[0] for k, v in b3.items()}; e5 = {k: v[1] / v[0] for k, v in b5.items()}
    agg = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0, 0, 0.0, 0, 0, [0, 0]]))
    def band(p):
        return "1-3番人気" if p <= 3 else "4-9番人気" if p <= 9 else "10番人気以下"
    for r in rows:
        half = 0 if r["date"] < "2026-04-01" else 1
        ts = set()
        for t in r["tags"]:
            b = base_tag(t)
            ts.add(b)
            if b != t:
                ts.add(t)  # 記号つき（本の検証○ など）も別に数える
        for t in ts | {"（全馬）"}:
            for bb in (band(r["pop"]), "全体"):
                a = agg[t][bb]
                p = min(r["pop"], 16)
                a[0] += 1; a[1] += r["fin"] <= 3; a[2] += e3[p]; a[3] += r["fin"] <= 5; a[4] += e5[p]
                a[5] += r["tan"]; a[6] += r["fuku"]; a[7][half] += r["fin"] <= 3
    L = ["# レース別シートの材料ごとの成績（tools/tag_backtest.py）", "",
         f"本番と同じ予想を過去1年（{START}〜{END}）で作り直した。A/E＝実際÷人気からの見込み。二桁人気の5着内A/Eは「来なくても近くまで来ているか」。",
         "判定: 3着内A/E・複勝回収・二桁人気の5着内A/E のどれも 0.95（95%）未満なら「省く候補」。どれかが1.0以上なら残す。", "",
         "| 材料 | 人気帯 | 頭数 | 3着内率 | 3着内A/E | 5着内A/E | 単勝回収 | 複勝回収 | 3着内（前半/後半） |", "|---|---|---|---|---|---|---|---|---|"]
    verdict = []
    for t in sorted(agg, key=lambda t: -agg[t]["全体"][0]):
        for bb in ("全体", "1-3番人気", "4-9番人気", "10番人気以下"):
            a = agg[t].get(bb)
            if not a or a[0] < 30:
                continue
            L.append(f"| {t} | {bb} | {a[0]} | {a[1] / a[0]:.1%} | {a[1] / a[2]:.2f} | {a[3] / a[4]:.2f} | {a[5] / a[0]:.0f}% | {a[6] / a[0]:.0f}% | {a[7][0]}/{a[7][1]} |")
        a, lo = agg[t]["全体"], agg[t].get("10番人気以下")
        if t == "（全馬）" or a[0] < 50:
            continue
        ae3, ae5l, fr = a[1] / a[2], (lo[3] / lo[4] if lo and lo[0] >= 30 else None), a[6] / a[0]
        keep = ae3 >= 1.0 or fr >= 100 or (ae5l is not None and ae5l >= 1.0)
        drop = ae3 < 0.95 and fr < 95 and (ae5l is None or ae5l < 0.95)
        verdict.append((t, a[0], ae3, fr, ae5l, "残す" if keep else "省く候補" if drop else "保留"))
    L += ["", "## 判定（全体）", "", "| 材料 | 頭数 | 3着内A/E | 複勝回収 | 二桁人気の5着内A/E | 判定 |", "|---|---|---|---|---|---|"]
    for t, n, ae3, fr, ae5l, v in sorted(verdict, key=lambda x: (x[5], -x[2])):
        L.append(f"| {t} | {n} | {ae3:.2f} | {fr:.0f}% | {'-' if ae5l is None else f'{ae5l:.2f}'} | **{v}** |")
    (ROOT / "docs" / "analysis" / "tag_backtest.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[-len(verdict) - 3:]))


if __name__ == "__main__":
    w = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    p = ROOT / "data" / "cache" / "tag_rows.json"
    rows = json.load(open(p)) if p.exists() and "--reuse" in sys.argv else collect(w)
    report_(rows)
