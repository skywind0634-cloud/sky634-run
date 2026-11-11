"""はてなブログの過去記事を月別アーカイブから少しずつ取得する（GitHub Actions 上で実行）.

新しい月 → 過去へ。取得済みの記事URL・完了した月を状態ファイルに記録し、次回は続きから。
本文は sources ブランチ（非公開の作業用）に保存し、血統見解の要点を expert_notes.json に登録するための読み込み用にだけ使う。
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
INTERVAL = 2.0


def get(url):
    time.sleep(INTERVAL)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.encoding = r.apparent_encoding or r.encoding
    return r.status_code, r.text


def month_entries(base, y, m):
    urls, page = [], 1
    while True:
        st, html = get(f"{base}/archive/{y}/{m:02d}" + (f"?page={page}" if page > 1 else ""))
        if st != 200:
            break
        soup = BeautifulSoup(html, "lxml")
        found = [urljoin(base, a["href"]).split("#")[0] for a in soup.select("a[href*='/entry/']")]
        new = [u for u in dict.fromkeys(found) if u not in urls]
        urls += new
        nxt = soup.select_one("a[rel='next'], .pager-next a")
        if not new or not nxt:
            break
        page += 1
    return urls


def entry_text(html):
    soup = BeautifulSoup(html, "lxml")
    title = (soup.select_one(".entry-title") or soup.title or soup).get_text(" ", strip=True)
    date = soup.select_one("time")
    body = soup.select_one(".entry-content") or soup.select_one("article") or soup.body
    for t in body(["script", "style"]):
        t.decompose()
    txt = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True))
    return title, (date.get("datetime") if date else ""), txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://nas-quillo.hatenablog.com")
    ap.add_argument("--out", default="sources/blog-mochida")
    ap.add_argument("--budget-min", type=float, default=25)
    ap.add_argument("--oldest-year", type=int, default=2005)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sp = out / "_state.json"
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"months_done": [], "entries": {}, "empty_streak": 0}
    deadline = time.time() + a.budget_min * 60
    today = dt.date.today()
    y, m = today.year, today.month
    saved = 0
    while y >= a.oldest_year and time.time() < deadline:
        key = f"{y}-{m:02d}"
        cur_month = (y, m) == (today.year, today.month)
        if key not in state["months_done"] or cur_month:
            urls = month_entries(a.base, y, m)
            state["empty_streak"] = 0 if urls else state.get("empty_streak", 0) + 1
            complete = True
            for u in urls:
                if u in state["entries"]:
                    continue
                if time.time() > deadline:
                    complete = False
                    break
                st, html = get(u)
                if st != 200:
                    continue
                title, date, txt = entry_text(html)
                fn = out / key / (hashlib.sha1(u.encode()).hexdigest()[:12] + ".txt")
                fn.parent.mkdir(parents=True, exist_ok=True)
                fn.write_text(f"URL: {u}\nTITLE: {title}\nDATE: {date}\n\n{txt[:30000]}", encoding="utf-8")
                state["entries"][u] = str(fn)
                saved += 1
            if complete and not cur_month:
                state["months_done"].append(key)
            print(key, len(urls), "entries", flush=True)
            if state["empty_streak"] >= 24:   # 2年分記事が無ければ、それ以前は無いとみなす
                print("no more archive")
                break
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"saved {saved}, total {len(state['entries'])}, months done {len(state['months_done'])}")


if __name__ == "__main__":
    main()
