"""指定した URL のページ本文だけを取得して sources/adhoc/<タグ>/ に保存する（リンクは辿らない. GitHub Actions 上で実行）.
JavaScript 描画のページはヘッドレスブラウザで描画し直す（fetch_sources.fetch_text）."""
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_sources as FS  # noqa: E402


def main(tag: str, urls_file: str):
    out = Path("sources/adhoc") / tag
    out.mkdir(parents=True, exist_ok=True)
    urls = [u.strip() for u in Path(urls_file).read_text(encoding="utf-8").splitlines() if u.strip() and not u.startswith("#")]
    index = []
    for u in urls:
        time.sleep(2.0)
        try:
            st, html, title, txt = FS.fetch_text(u)
        except Exception as e:  # noqa: BLE001
            index.append({"url": u, "error": str(e)})
            print("ERR", u, e, flush=True)
            continue
        fn = out / (hashlib.sha1(u.encode()).hexdigest()[:12] + ".txt")
        fn.write_text(f"URL: {u}\nTITLE: {title}\nSTATUS: {st}\n\n{txt[:60000]}", encoding="utf-8")
        index.append({"url": u, "title": title, "status": st, "file": str(fn), "chars": len(txt)})
        print(st, len(txt), title[:70], flush=True)
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
