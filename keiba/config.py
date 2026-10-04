import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
DB_PATH = Path(os.environ["KEIBA_DB"]) if os.environ.get("KEIBA_DB") else DATA_DIR / "keiba.db"
CARDS_DIR = ROOT / "cards"
PREDICTIONS_DIR = ROOT / "predictions"

# netkeiba の競馬場コード
COURSE_CODES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
COURSE_BY_NAME = {v: k for k, v in COURSE_CODES.items()}

# 対象レース: 全競馬場の第7レース以降。未勝利戦・障害は対象外（取り込み・予想とも）
MIN_RACE_NO = 7
EXCLUDED_GRADES = {"未勝利"}


def is_target_race(race_no: int | None, grade: str | None = None, surface: str | None = None,
                   name: str | None = None) -> bool:
    if race_no is not None and race_no < MIN_RACE_NO:
        return False
    if grade in EXCLUDED_GRADES or (name and "未勝利" in name):
        return False
    if surface == "障" or (name and "障害" in name):
        return False
    return True


# 予想ルール
MAX_RACES_PER_WEEK = 5
MAX_TICKETS_PER_RACE = 10

# スクレイピング時のアクセス間隔(秒)。相手サーバーに負荷をかけないこと。
REQUEST_INTERVAL = 1.5
USER_AGENT = "Mozilla/5.0 (compatible; sky634-keiba-research/1.0)"


def distance_band(distance: int) -> str:
    if distance <= 1400:
        return "sprint"
    if distance <= 1700:
        return "mile"
    if distance <= 2200:
        return "middle"
    return "long"


def going_group(going: str | None) -> str:
    """良 / 稍重 / 重 / 不良 → 'good' | 'soft'."""
    if not going or going == "良":
        return "good"
    return "soft"


def write_atomic(path, text: str) -> None:
    """一時ファイルに書いてから置き換える（別の処理が読んでいる途中に壊れた JSON を読ませない）."""
    import os
    from pathlib import Path
    path = Path(path)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
