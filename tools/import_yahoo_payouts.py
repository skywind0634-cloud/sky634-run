"""Yahoo の結果ページ（fetch-pages で保存）から払戻を読み、data/keiba.db の races.payouts に入れる.
使い方: python3 tools/import_yahoo_payouts.py <pages_dir>（urls.txt と 01.html… がある）"""
import json, re, sqlite3, sys
from pathlib import Path

KINDS = ["単勝", "複勝", "枠連", "馬連", "ワイド", "馬単", "3連複", "3連単"]


def parse(html: str) -> dict:
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    i = t.find("単勝 ", t.find("払戻"))
    if i < 0:
        return {}
    t = t[i:i + 3000]
    out = {}
    pos = [(t.find(k + " "), k) for k in KINDS]
    pos = sorted((p, k) for p, k in pos if p >= 0)
    for j, (p, k) in enumerate(pos):
        seg = t[p + len(k): pos[j + 1][0] if j + 1 < len(pos) else len(t)]
        out[k] = [[c, int(y.replace(",", ""))] for c, y in re.findall(r"(\d+(?:-\d+)*) ([\d,]+)円", seg)]
    return out


def main(d):
    d = Path(d)
    urls = (d / "urls.txt").read_text().split()
    c = sqlite3.connect(Path(__file__).resolve().parents[1] / "data" / "keiba.db")
    n = 0
    for i, u in enumerate(urls, 1):
        rid = "20" + u.rstrip("/").rsplit("/", 1)[1]
        p = parse((d / f"{i:02d}.html").read_text(encoding="utf-8"))
        if p and c.execute("select 1 from races where race_id=?", (rid,)).fetchone():
            c.execute("update races set payouts=? where race_id=?", (json.dumps(p, ensure_ascii=False), rid)); n += 1
    c.commit(); print("payouts", n)


if __name__ == "__main__":
    main(sys.argv[1])
