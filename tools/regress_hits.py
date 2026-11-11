"""当たる形を消さないための確認（2026-11-08 ユーザー「当たるものを外れる方向に変えるな」）.
data/regress/results_<日付>.json（day-results の結果）と cards/<日付>/ のカードで今のコードの買い目カードを作り直し、
「前に取れていた券」（MUST）がまだ買い目に入っているかを確かめる。材料・買い方を変えたら必ず実行し、NG が出たら変更を入れない.
使い方: python3 tools/regress_hits.py"""
import io, json, re, sys, tempfile, contextlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
# (日付, race_id, 券) — 取れていた（取れるべき）券
MUST = [("2026-11-08", "202605050211", "3連複 6-12-15"), ("2026-11-08", "202605050211", "ワイド 6-12"), ("2026-11-08", "202605050211", "ワイド 6-15"),
        ("2026-11-08", "202605050211", "ワイド 12-15"),
        # 11/8 本線の単勝（少額枠30点の上限で外れていた。★特推しを単勝1点にしたので入る）
        ("2026-11-08", "202603030207", "単勝 15"), ("2026-11-08", "202603030212", "単勝 16")]


def main():
    from keiba import db, analysis, digest, report
    from keiba.model import evaluate_race
    import race_sheet
    conn = db.connect(); st = analysis.build_stats(conn)
    ng = 0
    for d, rid, tk in MUST:
        card = json.load(open(ROOT / "cards" / d / f"{rid}.json"))
        ev = evaluate_race(card, st, conn, n_sims=0)
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8"); f.write(digest.text(card, ev, report.race_title(card))); f.close()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            race_sheet.main(f.name)
        o = buf.getvalue()
        buy = o[:o.find("【参考")] if "【参考" in o else o
        ok = re.search(rf"(?<![\d-]){re.escape(tk)}(?![\d-])", buy) is not None
        ng += not ok
        print(f"{'OK' if ok else 'NG'} {d} {rid} {tk}")
    print("全部OK" if not ng else f"NG {ng}件: 前に取れていた券が【今日買うもの】から消えている。変更を入れない")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
