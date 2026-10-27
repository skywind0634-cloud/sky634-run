"""血統コラム（望田潤氏のブログ・坂上明大氏の重賞血統査定など）の本文から、「血（祖先・種牡馬）× 条件」の主張を拾う（2026-10-27）.

ユーザー指摘「★の数より血統の特徴の情報を取れよ。★はレースにより適性が変わる」への対応。
本文は保存せず、文単位で「5代血統表に出てくる祖先名（または種牡馬名）」と「条件の言葉（道悪・大箱・小回り・瞬発・持続…）」が
同じ文に出た回数と出典URLだけを数える。向き（プラス/マイナス）は同じ文の否定語（苦手・不向き 等）で判定。
出力: JSON {"claims": [{entity, cond, dir, n_sent, n_art, urls}]} — tools/trait_check.py が実績で検証する。
使い方: python3 tools/trait_mining.py <ped5_full.json> <出典名> <out.json> <本文ディレクトリ...>
本文ファイルは先頭に "URL: ..." 行を持つテキスト（sources ブランチの形式）。坂上氏の査定は "RACE: 東京 芝 2400 外" 行を付けると、
【傾向】の文・適性★5の馬の段落の血を「そのレースの条件（コース・大箱/小回り・距離帯）でプラス」、適性★3以下の段落の血をマイナスとして数える。
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# 英語表記の祖先をカタカナで書く場合の読み替え（5代血統表では外国馬は英語）
ALIAS = {"ノーザンダンサー": "Northern Dancer", "ミスタープロスペクター": "Mr. Prospector", "ミスプロ": "Mr. Prospector",
         "ヌレイエフ": "Nureyev", "リファール": "Lyphard", "ニジンスキー": "Nijinsky", "サドラーズウェルズ": "Sadler's Wells",
         "ダンジグ": "Danzig", "ストームキャット": "Storm Cat", "ロベルト": "Roberto", "ヘイルトゥリーズン": "Hail to Reason",
         "ナスルーラ": "Nasrullah", "プリンスキロ": "Princequillo", "ボールドルーラー": "Bold Ruler", "ネイティヴダンサー": "Native Dancer",
         "ブラッシンググルーム": "Blushing Groom", "シアトルスルー": "Seattle Slew", "エーピーインディ": "A.P. Indy",
         "ヴァイスリージェント": "Vice Regent", "デピュティミニスター": "Deputy Minister", "ゴーンウェスト": "Gone West",
         "フォーティナイナー": "Forty Niner", "シーキングザゴールド": "Seeking the Gold", "キングマンボ": "Kingmambo",
         "ヘイロー": "Halo", "ハビタット": "Habitat", "ミルリーフ": "Mill Reef", "ネヴァーベンド": "Never Bend", "リボー": "Ribot",
         "グロースターク": "Graustark", "ヒズマジェスティ": "His Majesty", "バックパサー": "Buckpasser", "カロ": "Caro",
         "インリアリティ": "In Reality", "ファピアノ": "Fappiano", "アンブライドルド": "Unbridled", "セクレタリアト": "Secretariat",
         "リヴァーマン": "Riverman", "シャーペンアップ": "Sharpen Up", "ビーマイゲスト": "Be My Guest", "アルザオ": "Alzao",
         "バステッド": "Busted", "ハイトップ": "High Top", "ワイルドリスク": "Wild Risk", "シーバード": "Sea-Bird",
         "レイズアネイティヴ": "Raise a Native", "ターントゥ": "Turn-to", "ダンチヒ": "Danzig", "ストームバード": "Storm Bird",
         "サーゲイロード": "Sir Gaylord", "ハイペリオン": "Hyperion", "トムフール": "Tom Fool", "フェアトライアル": "Fair Trial",
         "グリーンデザート": "Green Desert", "ダンシングブレーヴ": "Dancing Brave", "ラストタイクーン": "Last Tycoon",
         "マキャヴェリアン": "Machiavellian", "エルグランセニョール": "El Gran Senor", "ヘクタープロテクター": "Hector Protector",
         "ミスワキ": "Miswaki", "ウッドマン": "Woodman", "スキャン": "Scan", "トライマイベスト": "Try My Best"}

# 条件の言葉（キーは tools/trait_check.py の条件名）
COND = {
    "道悪": r"道悪|重馬場|不良馬場|稍重|渋っ|渋れ|時計のかかる|時計が掛かる|時計がかかる|タフな馬場|荒れ馬場|力の要る|パワーの要る|パワーが要る",
    "高速馬場": r"高速馬場|高速決着|時計の速い|パンパン|軽い芝|速い時計",
    "大箱": r"大箱|東京|外回り|直線の長い|長い直線|広いコース",
    "小回り": r"小回り|内回り|中山|福島|小倉|函館|札幌|機動力|コーナー4つ|器用",
    "瞬発": r"瞬発|後傾|上がり勝負|スローの|ヨーイドン|キレ|切れ味|切れる",
    "持続": r"持続|前傾|ハイペース|消耗|底力|ロングスパート|タフなペース",
    "短距離": r"スプリント|短距離|1200|1000m|1000",
    "マイル": r"マイル|1600",
    "長距離": r"長距離|スタミナ|2400|2500|3000|3200|ステイヤー|ステイ",
    "ダート": r"ダート|砂",
    "洋芝": r"洋芝",
    "牝馬": r"牝馬|フィリーサイアー|牝駒",
    "晩成": r"晩成|奥手|古馬になって|成長力|年を重ね",
    "早熟": r"早熟|仕上がりの早|2歳戦|早い時期",
}
NEG = r"苦手|不向き|向かない|合わない|ダメ|割引|マイナス|嫌う|弱い|不安|疑問|向いていない|こなせない|厳しい"
SPLIT = re.compile(r"[。！？\n]")


def load_texts(dirs):
    for d in dirs:
        for f in sorted(Path(d).rglob("*.txt")):
            t = f.read_text(encoding="utf-8", errors="ignore")
            m = re.match(r"URL: (\S+)", t)
            url = m.group(1) if m else str(f)
            if "b.hatena.ne.jp" in url:   # はてなブックマークの一覧ページ（本文でない）
                continue
            head, body = (t.split("\n\n", 1) + [""])[:2]
            m = re.search(r"^RACE: (\S+) (\S+) (\d+) ?(\S*)", head, re.M)
            race = race_conds(m.group(1), m.group(2), int(m.group(3)), m.group(4)) if m else None
            # はてなはリンク語の前後で改行されるので、短い行はつなぐ
            body = re.sub(r"\n(?=[^\n]{0,25}\n)", "", body)
            yield url, body, race


def race_conds(co, su, dist, lay):
    """坂上氏の査定の回のレース条件（tools/trait_check.py の条件名）."""
    s = {f"{co}{su}"}
    if co == "東京" or (co in ("新潟", "京都", "阪神") and "外" in lay):
        s.add("大箱")
    elif co in ("中山", "福島", "小倉", "札幌", "函館") or "内" in lay:
        s.add("小回り")
    s.add("短距離" if dist <= 1400 else "マイル" if dist <= 1800 else "長距離" if dist >= 2200 else "中距離")
    if su == "ダ":
        s.add("ダート")
    return s


def race_blocks(body):
    """査定記事の段落 → (文, 向き)。【傾向】の文と、適性★5の馬の段落は＋、適性★3以下の馬の段落は−（そのレースの条件に対して）."""
    para = []
    for l in body.split("\n"):
        if l.startswith("【傾向】"):
            yield l[4:], "+"
            continue
        m = re.match(r"適性評価[:：]\s*(★+)", l)
        if m:
            k = len(m.group(1))
            for x in para:
                if k == 5:
                    yield x, "+"
                elif k <= 3:
                    yield x, "-"
            para = []
        elif not re.match(r"(能力|素質)評価", l):
            para.append(l)


def main(pf, src, out, *dirs):
    """out に前回の出力があれば、記事ごとの『血×条件』（by_article）を引き継ぎ、今回読んだ記事だけ置き換えて数え直す."""
    P = json.loads(Path(pf).read_text(encoding="utf-8"))
    cnt = Counter()
    for a in P["horses"].values():
        cnt.update(set(x for x in a if x))
    vocab = {n for n, v in cnt.items() if v >= 150 and len(n) >= 3}
    names = sorted(vocab | set(ALIAS), key=len, reverse=True)
    ent_re = re.compile("|".join(re.escape(n) for n in names))
    cond_re = {k: re.compile(v) for k, v in COND.items()}
    neg_re = re.compile(NEG)
    by_art = {}
    if Path(out).exists():
        try:
            by_art = json.loads(Path(out).read_text(encoding="utf-8")).get("by_article", {})
        except ValueError:
            pass
    for url, body, race in load_texts(dirs):
        mine = Counter()
        if race:
            for x, d in race_blocks(body):
                for e in {ALIAS.get(m, m) for m in ent_re.findall(x)}:
                    for c in race:
                        mine[(e, c, d)] += 1
        for s in SPLIT.split(body):
            if len(s) < 8:
                continue
            ents = {ALIAS.get(m, m) for m in ent_re.findall(s)}
            if not ents:
                continue
            conds = [k for k, r in cond_re.items() if r.search(s)]
            if not conds:
                continue
            d = "-" if neg_re.search(s) else "+"
            sire_ctx = "産駒" in s
            for e in ents:
                for c in conds:
                    for key in ((e, c, d),) + (((f"父={e}", c, d),) if sire_ctx else ()):
                        mine[key] += 1
        by_art[url] = [[*k, v] for k, v in mine.items()]
    agg = defaultdict(lambda: [0, set()])
    for url, ks in by_art.items():
        for e, c, d, v in ks:
            a = agg[(e, c, d)]; a[0] += v; a[1].add(url)
    n_art = len(by_art)
    claims = [{"entity": e, "cond": c, "dir": d, "n_sent": v[0], "n_art": len(v[1]), "urls": sorted(v[1])[:5]}
              for (e, c, d), v in agg.items()]
    claims.sort(key=lambda x: -x["n_art"])
    Path(out).write_text(json.dumps({"_meta": {"source": src, "articles": n_art, "tool": "tools/trait_mining.py",
                                               "note": "本文は保存せず、文中の『血×条件』の共起回数と出典URLのみ"},
                                     "claims": claims, "by_article": by_art}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(src, n_art, "本,", len(claims), "件の『血×条件』")


if __name__ == "__main__":
    main(*sys.argv[1:])
