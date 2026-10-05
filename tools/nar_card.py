"""地方競馬の1レースの出馬表・オッズページを取得して保存する（keiba.go.jp, 2秒間隔・キャッシュ）.
使い方: python tools/nar_card.py <競馬場コード> <YYYY-MM-DD> <レース番号> <出力先>"""
import datetime as dt
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from keiba import nar  # noqa: E402

baba, date, rno, out = sys.argv[1], dt.date.fromisoformat(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
q = f"k_raceDate={nar._d(date)}&k_raceNo={rno}&k_babaCode={baba}"
pages = {"DebaTable": f"{nar.BASE}/TodayRaceInfo/DebaTable?{q}"}
deba = nar.get(pages["DebaTable"])
(out / "DebaTable.html").write_text(deba, encoding="utf-8")
# 出馬表ページからオッズ類のリンクを全部たどる
for href in sorted(set(re.findall(r'href="([^"]*Odds[^"]*)"', deba))):
    url = html.unescape(href)
    if url.startswith("/"):
        url = "https://www.keiba.go.jp" + url
    elif not url.startswith("http"):
        url = nar.BASE + "/" + url.lstrip("./")
    if f"k_raceNo={rno}" not in url:
        continue
    name = re.search(r"/(\w*Odds\w*)\?", url)
    name = name.group(1) if name else "Odds"
    (out / f"{name}.html").write_text(nar.get(url), encoding="utf-8")
    print("saved", name, url)
print("files", sorted(p.name for p in out.iterdir()))
