"""血統に関する動画（亀谷敬正・望田潤・坂上明大・水上学 など）の字幕／音声書き起こしの取得（GitHub Actions 上で実行）.

data/sources.json の "videos"（YouTube 検索語・チャンネル/再生リストURL）から動画を列挙し、
1. 字幕（投稿者字幕 → 自動字幕, 日本語）があればそれをテキスト化
2. 無ければ音声をダウンロードして faster-whisper で書き起こし（1回の実行で --whisper 本まで・長さ上限あり）
sources/videos/<動画ID>.txt に保存する（非公開の作業用ブランチ `sources`）。取得済みの動画はスキップ。
保存したテキストは、血統見解の要点と出典URLを data/knowledge/expert_notes.json に登録するための読み込み用で、転載はしない。
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path("sources/videos")


def ytdlp(*args, check=False):
    return subprocess.run([sys.executable, "-m", "yt_dlp", "--no-warnings", "--ignore-errors", *args],
                          capture_output=True, text=True, check=check)


def list_videos(target: str, n: int) -> list[dict]:
    src = target if target.startswith("http") else f"ytsearch{n}:{target}"
    r = ytdlp("--flat-playlist", "--playlist-end", str(n), "-J", src)
    try:
        data = json.loads(r.stdout or "{}")
    except ValueError:
        print("list failed:", target, r.stderr[-500:])
        return []
    out = []
    for e in data.get("entries") or []:
        if e and e.get("id"):
            out.append({"id": e["id"], "title": e.get("title") or "", "channel": e.get("channel") or e.get("uploader") or "",
                        "duration": e.get("duration") or 0})
    return out


def vtt_to_text(path: Path) -> str:
    lines, prev = [], None
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or ln.isdigit():
            continue
        if ln != prev:
            lines.append(ln)
        prev = ln
    return "\n".join(lines)


def subtitles(vid: str, tmp: Path) -> tuple[str | None, str]:
    r = ytdlp("--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "ja.*,ja", "--sub-format", "vtt",
          "-o", str(tmp / "%(id)s.%(ext)s"), f"https://www.youtube.com/watch?v={vid}")
    subs = sorted(tmp.glob(f"{vid}*.vtt"), key=lambda p: len(p.name))
    if not subs:
        err = (r.stderr or "").strip().splitlines()
        return None, "yt-dlp: " + (err[-1][:160] if err else "字幕なし")
    return vtt_to_text(subs[0]), "字幕（投稿者 or 自動）"


def transcript_api(vid: str) -> tuple[str | None, str]:
    """youtube-transcript-api（字幕エンドポイント）での取得."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        tr = api.fetch(vid, languages=["ja"])
        return "\n".join(sn.text for sn in tr), "字幕(transcript-api)"
    except Exception as e:  # noqa: BLE001
        return None, f"transcript-api: {type(e).__name__}"


INVIDIOUS = ["https://inv.nadeko.net", "https://yewtu.be", "https://invidious.nerdvpn.de", "https://id.420129.xyz"]


def invidious(vid: str) -> tuple[str | None, str]:
    """公開 Invidious インスタンスの字幕 API（YouTube がランナーを弾く場合の代替）."""
    import requests
    errs = []
    for base in INVIDIOUS:
        try:
            r = requests.get(f"{base}/api/v1/captions/{vid}", timeout=20)
            caps = r.json().get("captions", []) if r.ok else []
            ja = [c for c in caps if (c.get("language_code") or c.get("languageCode") or "").startswith("ja")]
            if not ja:
                errs.append(f"{base}:{r.status_code}/no-ja")
                continue
            v = requests.get(base + ja[0]["url"], timeout=20)
            if v.ok and "-->" in v.text:
                p = Path(tempfile.mkstemp(suffix=".vtt")[1])
                p.write_text(v.text, encoding="utf-8")
                return vtt_to_text(p), f"字幕(invidious {base})"
            errs.append(f"{base}:{v.status_code}")
        except Exception as e:  # noqa: BLE001
            errs.append(f"{base}:{type(e).__name__}")
    return None, "; ".join(errs)


def whisper(vid: str, tmp: Path, model) -> str | None:
    ytdlp("-f", "bestaudio[ext=m4a]/bestaudio", "-o", str(tmp / f"{vid}.%(ext)s"), f"https://www.youtube.com/watch?v={vid}")
    au = next(iter(tmp.glob(f"{vid}.*")), None)
    if not au:
        return None
    segs, _ = model.transcribe(str(au), language="ja", vad_filter=True)
    return "\n".join(s.text.strip() for s in segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-query", type=int, default=15)
    ap.add_argument("--whisper", type=int, default=4, help="字幕の無い動画を書き起こす最大本数")
    ap.add_argument("--max-minutes", type=int, default=40)
    ap.add_argument("--existing", default="existing/sources/videos")
    a = ap.parse_args()
    cfg = json.loads(Path("data/sources.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in Path(a.existing).glob("*.txt")} if Path(a.existing).exists() else set()
    model, wleft, index = None, a.whisper, []
    for q in cfg.get("videos", []):
        target, kw = q["query"], q.get("title_keywords", [])
        for v in list_videos(target, a.per_query):
            if v["id"] in have or (kw and not any(k in v["title"] for k in kw)):
                continue
            have.add(v["id"])
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                text, method = subtitles(v["id"], tmp)
                errs = []
                if not text:
                    errs.append(method or "yt-dlp: 字幕なし/取得拒否")
                    text, method = transcript_api(v["id"])
                if not text:
                    errs.append(method)
                    text, method = invidious(v["id"])
                if not text:
                    errs.append(method)
                if not text and wleft > 0 and 0 < v["duration"] <= a.max_minutes * 60:
                    if model is None:
                        from faster_whisper import WhisperModel
                        model = WhisperModel("small", device="cpu", compute_type="int8")
                    text, method = whisper(v["id"], tmp, model), "音声書き起こし(whisper small)"
                    wleft -= 1
            if not text:
                index.append({**v, "status": "no_text", "errors": errs})
                continue
            url = f"https://www.youtube.com/watch?v={v['id']}"
            (OUT / f"{v['id']}.txt").write_text(
                f"title: {v['title']}\nchannel: {v['channel']}\nurl: {url}\nmethod: {method}\nquery: {target}\n\n{text}\n",
                encoding="utf-8")
            index.append({**v, "status": "ok", "method": method, "chars": len(text)})
            print("ok", v["id"], method, v["title"][:60])
    (OUT / "_index_latest.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {sum(1 for x in index if x['status'] == 'ok')} / tried {len(index)}")


if __name__ == "__main__":
    main()
