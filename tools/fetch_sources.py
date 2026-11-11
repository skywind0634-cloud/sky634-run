"""血統コラム・予想コメント等の本文取得（GitHub Actions 上で実行）.

data/sources.json の seeds（一覧ページ）から、同じサイト内の記事リンク（キーワードで絞り込み）を辿り、
本文テキストを sources/<サイト>/<ハッシュ>.txt に保存する（非公開の作業用ブランチ `sources` にコミット）。
保存した本文は、血統見解の要点を data/knowledge/expert_notes.json に登録するための読み込み用。予想ファイル等には転載しない。
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
OUT = Path("sources")


def get(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
    r.encoding = r.apparent_encoding or r.encoding
    # share.google 等の短縮URL: meta refresh / JS リダイレクトも追う
    m = re.search(r"""(?:http-equiv=["']refresh["'][^>]*url=|location(?:\.href)?\s*=\s*["'])(https?://[^"'>\s]+)""",
                  r.text[:5000], re.I)
    if urlparse(r.url).netloc in ("share.google", "goo.gl") and m:
        r = requests.get(m.group(1), headers={"User-Agent": UA}, timeout=30)
        r.encoding = r.apparent_encoding or r.encoding
    LAST_URL[0] = r.url   # リダイレクト後の実URL（リンク収集の基準にする）
    if "pdf" in r.headers.get("Content-Type", "").lower() or r.url.lower().endswith(".pdf"):
        return r.status_code, pdf_text(r.content, r.url)
    return r.status_code, r.text


LAST_URL = [""]


def pdf_text(data: bytes, url: str) -> str:
    """PDF → 本文テキスト（text_of がそのまま扱えるよう簡単な HTML に包む）."""
    import io
    try:
        from pypdf import PdfReader
        pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
    except Exception as e:  # noqa: BLE001
        pages = [f"(PDF の読み取りに失敗: {e})"]
    body = "\n".join(pages).replace("&", "&amp;").replace("<", "&lt;")
    return f"<html><head><title>PDF {url}</title></head><body><article><pre>{body}</pre></article></body></html>"


_BROWSER = {}


def render(url: str) -> tuple[int, str]:
    """JavaScript で本文を描画するサイト（東スポ競馬・netkeiba スマホ版 等）はヘッドレスブラウザで開く."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0, ""
    if "pw" not in _BROWSER:
        _BROWSER["pw"] = sync_playwright().start()
        _BROWSER["b"] = _BROWSER["pw"].chromium.launch()
    page = _BROWSER["b"].new_page(user_agent=UA)
    try:
        resp = page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1500)
        LAST_URL[0] = page.url
        return (resp.status if resp else 0), page.content()
    except Exception as e:  # noqa: BLE001
        print("render failed", url, e, flush=True)
        return 0, ""
    finally:
        page.close()


def fetch_text(u: str) -> tuple[int, str, str, str]:
    """(status, html, title, text)。本文がほぼ空ならブラウザで描画し直す."""
    st, html = get(u)
    title, txt = text_of(html)
    if len(txt) < 400:
        st2, html2 = render(u)
        if html2:
            t2, x2 = text_of(html2)
            if len(x2) > len(txt):
                st, html, title, txt = st2 or st, html2, t2 or title, x2
    return st, html, title, txt


def text_of(html):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        t.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    main = soup.find("article") or soup.find("main") or soup.body or soup
    txt = re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True))
    return title, txt


def main(max_per_seed=15):
    cfg = json.loads(Path("data/sources.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    index = []
    for seed in cfg["seeds"]:
        url, kw = seed["url"], seed.get("link_keywords", [])
        try:
            st, html, _t, _x = fetch_text(url)
        except Exception as e:  # noqa: BLE001
            index.append({"seed": url, "error": str(e)})
            continue
        base = LAST_URL[0] or url        # share.google 等はリダイレクト先を基準にリンクを辿る
        dom = urlparse(base).netloc
        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            u = urljoin(base, a["href"]).split("#")[0]
            label = a.get_text(" ", strip=True)
            if urlparse(u).netloc != dom or u in (url, base) or u in links:
                continue
            if kw and not any(k in label or k in u for k in kw):
                continue
            links.append(u)
        for u in [url] + links[:max_per_seed]:
            time.sleep(2.0)
            try:
                st, html, title, txt = fetch_text(u)
            except Exception as e:  # noqa: BLE001
                index.append({"url": u, "error": str(e)})
                continue
            fn = OUT / dom / (hashlib.sha1(u.encode()).hexdigest()[:12] + ".txt")
            fn.parent.mkdir(parents=True, exist_ok=True)
            fn.write_text(f"URL: {u}\nTITLE: {title}\nSTATUS: {st}\n\n{txt[:20000]}", encoding="utf-8")
            index.append({"url": u, "title": title, "status": st, "file": str(fn), "chars": len(txt)})
            print(st, len(txt), title[:60], flush=True)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15)
