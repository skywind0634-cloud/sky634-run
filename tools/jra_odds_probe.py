"""JRA の結果ページから「オッズ」ページ（最終オッズ）への辿り方を調べる（調査用, 2026-10-17）.
直近（10/12 東京10R）と古いレース（2021年1月・2024年1月）で、オッズページと券種タブ（ワイド・3連複など）が取れるか確かめ、HTML を probe/ に保存する。"""
import re, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from keiba.scraper import jra  # noqa: E402

out = Path("probe"); out.mkdir(exist_ok=True)


def allinks(html):
    return jra.ACTION_RE.findall(html) + jra.HREF_RE.findall(html)


def probe(label, day_pred, ym):
    months = jra.month_cnames()
    days = [d for d in jra.day_lists_in_month(ym, months) if day_pred(d)]
    print(label, "days", [d[1][:30] for d in days[:3]], flush=True)
    if not days:
        return
    races = jra.races_in_day(days[0])
    rc = races[-3]  # 10R 付近
    html = jra.post(*rc)
    (out / f"{label}_result.html").write_text(html, encoding="utf-8")
    ls = allinks(html)
    print(label, "result", rc[1], "paths", Counter(p for p, _ in ls), flush=True)
    odds = [(p, c) for p, c in ls if "accessO" in p]
    print(label, "odds links", odds[:10], flush=True)
    for i, (p, c) in enumerate(odds[:1]):
        try:
            h = jra.post(p, c, use_cache=False)
        except Exception as e:  # noqa: BLE001
            print(label, "odds fetch failed", c, e, flush=True)
            continue
        (out / f"{label}_odds_{i}.html").write_text(h, encoding="utf-8")
        tabs = [(pp, cc) for pp, cc in allinks(h) if "accessO" in pp]
        print(label, "odds page tabs", tabs[:20], flush=True)
        seen = set()
        for pp, cc in tabs:
            pre = cc[:7]
            if pre in seen:
                continue
            seen.add(pre)
            try:
                hh = jra.post(pp, cc, use_cache=False)
                (out / f"{label}_tab_{pre}.html").write_text(hh, encoding="utf-8")
                t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", hh))
                i0 = t.find("オッズ")
                print(label, "tab", pre, cc, len(hh), t[i0:i0 + 300], flush=True)
            except Exception as e:  # noqa: BLE001
                print(label, "tab failed", cc, e, flush=True)


probe("recent", lambda d: (jra.day_date_from_cname(d[1]) or "") == "2026-10-12", "202610")
probe("y2024", lambda d: (jra.day_date_from_cname(d[1]) or "").startswith("2024-01"), "202401")
probe("y2021", lambda d: (jra.day_date_from_cname(d[1]) or "").startswith("2021-01"), "202101")
