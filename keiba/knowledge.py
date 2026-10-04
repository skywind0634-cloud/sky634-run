"""血統ナレッジ(data/knowledge/*.json)の読み込みと、系統・適性ベクトルの解決."""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache

from .config import KNOWLEDGE_DIR

AXES = ["turf", "dirt", "sprint", "mile", "middle", "long",
        "heavy", "kire", "jizoku", "power", "early", "growth"]
ZERO = {a: 0.0 for a in AXES}

# 血統表の祖先名から系統を推定するための『系統の祖』キーワード
LINE_FOUNDERS = {
    "ディープインパクト": "ディープインパクト系",
    "ステイゴールド": "ステイゴールド系",
    "ハーツクライ": "ハーツクライ系",
    "ダイワメジャー": "ダイワメジャー系",
    "ブラックタイド": "ブラックタイド系",
    "ゴールドアリュール": "ゴールドアリュール系",
    "フジキセキ": "フジキセキ系",
    "マンハッタンカフェ": "マンハッタンカフェ系",
    "ネオユニヴァース": "ネオユニヴァース系",
    "アグネスタキオン": "アグネスタキオン系",
    "スペシャルウィーク": "スペシャルウィーク系",
    "サンデーサイレンス": "サンデーサイレンス系",
    "キングカメハメハ": "キングカメハメハ系",
    "Kingmambo": "キングマンボ系",
    "シンボリクリスエス": "シンボリクリスエス系",
    "スクリーンヒーロー": "スクリーンヒーロー系",
    "グラスワンダー": "グラスワンダー系",
    "ブライアンズタイム": "ブライアンズタイム系",
    "Kris S.": "クリスエス系",
    "Roberto": "ロベルト系",
    "Hennessy": "ヘネシー系",
    "ヘニーヒューズ": "ヘネシー系",
    "Giant's Causeway": "ジャイアンツコーズウェイ系",
    "Tale of the Cat": "テイルオブザキャット系",
    "Scat Daddy": "スキャットダディ系",
    "Forestry": "フォレストリー系",
    "Harlan's Holiday": "ハーランズホリデー系",
    "Harlan": "ハーランズホリデー系",
    "Storm Cat": "ストームキャット系",
    "Forty Niner": "フォーティナイナー系",
    "エンドスウィープ": "フォーティナイナー系",
    "Gone West": "ゴーンウエスト系",
    "Machiavellian": "マキャヴェリアン系",
    "Seeking the Gold": "シーキングザゴールド系",
    "Smart Strike": "スマートストライク系",
    "Unbridled": "ファピアノ系",
    "Fappiano": "ファピアノ系",
    "Mr. Prospector": "ミスタープロスペクター系",
    "A.P. Indy": "エーピーインディ系",
    "Deputy Minister": "デピュティミニスター系",
    "Danehill": "デインヒル系",
    "Dansili": "デインヒル系",
    "War Front": "ウォーフロント系",
    "Green Desert": "グリーンデザート系",
    "Danzig": "ダンチヒ系",
    "Galileo": "ガリレオ系",
    "Sadler's Wells": "サドラーズウェルズ系",
    "Montjeu": "サドラーズウェルズ系",
    "Lyphard": "リファール系",
    "Dancing Brave": "リファール系",
    "Marju": "マルジュ系",
    "サクラバクシンオー": "プリンスリーギフト系",
    "Holy Bull": "ホーリーブル系",
}


def _load(name: str) -> dict:
    with open(KNOWLEDGE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def sire_lines() -> dict:
    return _load("sire_lines.json")["lines"]


@lru_cache(maxsize=None)
def sires() -> dict:
    return _load("sires.json")["sires"]


@lru_cache(maxsize=None)
def nicks() -> list:
    return _load("nicks.json")["nicks"]


@lru_cache(maxsize=None)
def families() -> dict:
    return _load("female_families.json")["families"]


@lru_cache(maxsize=None)
def courses() -> dict:
    return _load("courses.json")


@lru_cache(maxsize=None)
def _country_types() -> dict:
    try:
        return _load("country_types.json")["types"]
    except (OSError, KeyError, ValueError):
        return {}


@lru_cache(maxsize=4096)
def country_type(line: str | None) -> str | None:
    """系統 → 国別タイプ（日本型/米国型/欧州型）。親系統を辿って最初に見つかったもの。不明は None."""
    t = _country_types()
    for ln in line_ancestry(line):
        if ln in t:
            return t[ln]
    return None


def line_ancestry(line: str | None) -> list[str]:
    """系統 → 親系統を辿ったリスト (自身を含む)."""
    out = []
    lines = sire_lines()
    while line and line in lines and line not in out:
        out.append(line)
        line = lines[line].get("parent")
    if line and line not in out:
        out.append(line)
    return out


def resolve_line(name: str | None, pedigree: dict | None = None, prefix: str = "S") -> str:
    """種牡馬名(または血統表の父系祖先)から小系統を決める.

    prefix は血統表上の位置 ('S' = 父, 'DS' = 母父)。父系は prefix+'S'+'S'... と辿る。
    """
    if name:
        s = sires().get(name)
        if s:
            return s["line"]
        if name in LINE_FOUNDERS:
            return LINE_FOUNDERS[name]
    if pedigree:
        pos = prefix
        for _ in range(4):
            pos = pos + "S"
            anc = pedigree.get(pos)
            if not anc:
                break
            if anc in sires():
                return sires()[anc]["line"]
            if anc in LINE_FOUNDERS:
                return LINE_FOUNDERS[anc]
    return "その他"


def line_apt(line: str) -> dict:
    lines = sire_lines()
    for l in line_ancestry(line):
        if l in lines:
            return {**ZERO, **lines[l]["apt"]}
    return dict(ZERO)


_learned_override: dict | None = None   # バックテスト時に「検証期間より前だけで学習した値」を差し込む


@lru_cache(maxsize=None)
def learned() -> dict:
    """実績から学習した適性（keiba/deep.py が生成）. 無ければ空."""
    if _learned_override is not None:
        return _learned_override
    p = KNOWLEDGE_DIR / "learned_sires.json"
    if not p.exists():
        return {"sires": {}, "damsires": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


LEARN_K = 150.0   # 学習値の信頼度: 出走数 n のとき重み n/(n+K)


def sire_apt(name: str | None, line: str | None = None, role: str = "sires") -> dict:
    """種牡馬の適性ベクトル = 系統既定値 + 個別上書き(事前知識) を、実績からの学習値と出走数に応じて合成."""
    s = sires().get(name or "", {})
    base = line_apt(s.get("line") or line or "その他")
    base.update(s.get("apt", {}))
    lv = learned().get(role, {}).get(name or "")
    if lv:
        for a, v in lv["apt"].items():
            n = lv.get("n_axis", {}).get(a, lv["n"])
            w = n / (n + LEARN_K)
            base[a] = (1 - w) * base.get(a, 0.0) + w * v
    return base


def nick_prior(sire: str | None, sire_line: str | None,
               damsire: str | None, damsire_line: str | None) -> tuple[float, list[str]]:
    """ニックス事前評価. 最も具体的に一致した組み合わせの rating を返す."""
    s_lines = set(line_ancestry(sire_line))
    d_lines = set(line_ancestry(damsire_line))
    best = None
    best_spec = -1
    for n in nicks():
        spec = 0
        if "sire" in n:
            if n["sire"] != sire:
                continue
            spec += 2
        elif "sire_line" in n:
            if n["sire_line"] not in s_lines:
                continue
            spec += 1
        if "damsire" in n:
            if n["damsire"] != damsire:
                continue
            spec += 2
        elif "damsire_line" in n:
            if n["damsire_line"] not in d_lines:
                continue
            spec += 1
        if spec > best_spec:
            best, best_spec = n, spec
    if not best:
        return 0.0, []
    why = best.get("why", "")
    ex = best.get("examples", [])
    note = f"{why}" + (f"（例: {'・'.join(ex)}）" if ex else "")
    return float(best["rating"]), [note] if note else []


def detect_family(pedigree: dict | None, dam: str | None = None) -> tuple[str | None, float]:
    """母系(D, DD, DDD, ...)に主要牝系の基礎牝馬がいれば (牝系名, ボーナス)."""
    names = []
    if dam:
        names.append(dam)
    if pedigree:
        pos = "D"
        for _ in range(5):
            if pedigree.get(pos):
                names.append(pedigree[pos])
            pos += "D"
        # 3〜5代母は data/tail_female.json（5代血統表から補完）からも
        try:
            from . import tailfemale
            deep = tailfemale.load().get(pedigree.get("DD") or "")
        except Exception:   # noqa: BLE001
            deep = None
        names += [n for n in (deep or []) if n]
    for fam, info in families().items():
        keys = set(info["key_mares"]) | {fam}
        if any(n in keys for n in names):
            return fam, float(info["bonus"])
    return None, 0.0


def detect_crosses(pedigree: dict | None) -> list[tuple[str, str]]:
    """5代以内のインブリード(クロス)を検出. [(祖先名, '4×3'), ...]"""
    if not pedigree:
        return []
    gens: dict[str, list[int]] = {}
    for pos, name in pedigree.items():
        if not name:
            continue
        gens.setdefault(name, []).append(len(pos))
    dup = {n for n, gs in gens.items() if len(gs) >= 2}

    def derived(pos: str) -> bool:  # 上位のクロス祖先の血統表内に含まれるだけの位置か
        return any(pedigree.get(pos[:k]) in dup for k in range(1, len(pos)))

    out = []
    for name, gs in gens.items():
        if name not in dup:
            continue
        if all(derived(p) for p, n in pedigree.items() if n == name):
            continue
        # 表記は『父側の世代×母側の世代』
        s = sorted(len(pos) for pos, n in pedigree.items() if n == name and pos[0] == "S")
        d = sorted(len(pos) for pos, n in pedigree.items() if n == name and pos[0] == "D")
        out.append((name, "×".join(str(x) for x in s + d)))
    out.sort(key=lambda t: sum(int(x) for x in t[1].split("×")))
    return out


def pedigree_line_mix(pedigree: dict | None) -> Counter:
    """血統表中の系統構成(祖先を系統に分類した出現数). 血量の偏りの把握用."""
    c: Counter = Counter()
    if not pedigree:
        return c
    for name in pedigree.values():
        if name in LINE_FOUNDERS:
            c[LINE_FOUNDERS[name]] += 1
    return c


def line_esi(line: str | None) -> float:
    """系統の産駒の平均テン指数(事前値). 親系統を辿って最初に見つかった値."""
    lines = sire_lines()
    for l in line_ancestry(line):
        if l in lines and "esi" in lines[l]:
            return float(lines[l]["esi"])
    return 0.5


def course_style_prior(course: str | None, surface: str | None) -> dict:
    c = courses()["courses"].get(course or "", {})
    return c.get("turf" if surface == "芝" else "dirt", {}).get("style_prior", {})


# ---------------------------------------------------------------- コース形態
# 内回り/外回り（JRA公式の距離別コース。両方ある距離は多い方）
_LAYOUT = {
    ("京都", "芝"): {1200: "内", 1400: "外", 1600: "外", 1800: "外", 2000: "内", 2200: "外", 2400: "外", 3000: "外", 3200: "外"},
    ("阪神", "芝"): {1200: "内", 1400: "内", 1600: "外", 1800: "外", 2000: "内", 2200: "内", 2400: "外", 2600: "外", 3000: "内", 3200: "外"},
    ("新潟", "芝"): {1000: "直", 1200: "内", 1400: "内", 1600: "外", 1800: "外", 2000: "外", 2200: "内", 2400: "内"},
    ("中山", "芝"): {1200: "外", 1600: "外", 1800: "内", 2000: "内", 2200: "外", 2500: "内", 3600: "内"},
}
_INNER_STRAIGHT = {"京都": 328.4, "阪神": 356.5, "新潟": 358.7}
SLOPE = {"中山": "急坂", "阪神": "急坂", "中京": "急坂", "東京": "坂", "福島": "小坂", "函館": "小坂",
         "京都": "平坦", "新潟": "平坦", "小倉": "平坦", "札幌": "平坦"}


@lru_cache(maxsize=None)
def course_attrs(course: str | None, surface: str | None, distance: int | None) -> dict:
    """競馬場×芝ダ×距離 → 回り・直線の長さ・坂・コーナー(大回り/小回り)."""
    c = courses()["courses"].get(course or "", {})
    sd = c.get("turf" if surface == "芝" else "dirt", {})
    layout = _LAYOUT.get((course, surface), {}).get(distance or 0, "")
    straight = sd.get("straight") or 0
    if layout == "内" and course in _INNER_STRAIGHT:
        straight = _INNER_STRAIGHT[course]
    if layout == "直":
        straight = 1000
    cat = "長" if straight >= 450 else ("中" if straight >= 350 else "短")
    big = course in ("東京", "中京") or (course in ("京都", "阪神", "新潟") and layout in ("外", "直")) \
        or (surface == "ダ" and course in ("東京", "中京"))
    return {"direction": "直" if layout == "直" else c.get("direction"), "straight": straight, "straight_cat": cat,
            "slope": "坂" if SLOPE.get(course or "") in ("急坂", "坂") else "平坦",
            "turn": "大回り" if big else "小回り", "layout": layout}
