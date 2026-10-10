"""SQLite による血統・レース結果データベース."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS races (
    race_id      TEXT PRIMARY KEY,   -- netkeiba 形式 YYYY CC KK DD RR
    date         TEXT NOT NULL,      -- YYYY-MM-DD
    course       TEXT NOT NULL,      -- 東京 / 中山 ...
    race_no      INTEGER,
    name         TEXT,
    grade        TEXT,               -- G1/G2/G3/L/OP/3勝/2勝/1勝/未勝利/新馬
    surface      TEXT,               -- 芝 / ダ / 障
    distance     INTEGER,
    direction    TEXT,               -- 右 / 左 / 直
    weather      TEXT,
    going        TEXT,               -- 良 / 稍重 / 重 / 不良
    n_runners    INTEGER,
    laps         TEXT,               -- JSON 配列 (200m ごと秒)
    first3f      REAL,
    last3f       REAL,
    pace_type    TEXT,               -- 瞬発 / 持続 / 消耗 / 平均
    payouts      TEXT                -- JSON {券種: [[組番, 払戻], ...]}
);

CREATE TABLE IF NOT EXISTS results (
    race_id      TEXT NOT NULL,
    horse_id     TEXT NOT NULL,
    finish       INTEGER,            -- 着順 (中止/除外は NULL)
    gate         INTEGER,
    number       INTEGER,
    sex          TEXT,
    age          INTEGER,
    weight_carried REAL,
    jockey       TEXT,
    trainer      TEXT,
    time_sec     REAL,
    margin       TEXT,
    passing      TEXT,               -- 通過順 "3-3-2-1"
    last3f       REAL,
    odds         REAL,
    popularity   INTEGER,
    body_weight  INTEGER,
    body_weight_diff INTEGER,
    PRIMARY KEY (race_id, horse_id)
);

CREATE TABLE IF NOT EXISTS horses (
    horse_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    sex          TEXT,
    birth_year   INTEGER,
    sire         TEXT,
    dam          TEXT,
    damsire      TEXT,
    sire_line    TEXT,
    damsire_line TEXT,
    family       TEXT,               -- 主要牝系名(該当時)
    pedigree     TEXT                -- JSON {位置: 馬名} 5代 (S, D, SS, SD, DS, DD, SSS ...)
);

CREATE TABLE IF NOT EXISTS entries (   -- 今週の出馬表
    race_id      TEXT NOT NULL,
    horse_id     TEXT,
    horse_name   TEXT NOT NULL,
    gate         INTEGER,
    number       INTEGER,
    sex          TEXT,
    age          INTEGER,
    weight_carried REAL,
    jockey       TEXT,
    trainer      TEXT,
    odds         REAL,
    popularity   INTEGER,
    PRIMARY KEY (race_id, horse_name)
);

CREATE TABLE IF NOT EXISTS fetched_dates (  -- 取り込み完了した開催日（途中再開用）
    date         TEXT PRIMARY KEY,
    n_races      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_results_horse ON results(horse_id);
CREATE INDEX IF NOT EXISTS idx_races_date ON races(date);
CREATE INDEX IF NOT EXISTS idx_horses_sire ON horses(sire);
CREATE INDEX IF NOT EXISTS idx_horses_dam ON horses(dam);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # 対象外レース（第6レース以前・未勝利戦・障害）は保持しない（過去に取り込んだ分も削除）
    cond = ("race_no < 7 OR grade = '未勝利' OR name LIKE '%未勝利%' OR surface = '障' OR name LIKE '%障害%'")
    conn.execute(f"DELETE FROM results WHERE race_id IN (SELECT race_id FROM races WHERE {cond})")
    conn.execute(f"DELETE FROM races WHERE {cond}")
    conn.commit()
    return conn


def _upsert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = list(row)
    placeholders = ",".join("?" for _ in cols)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
        [json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for v in row.values()],
    )


def upsert_race(conn, race: dict) -> None:
    _upsert(conn, "races", race)


def upsert_result(conn, result: dict) -> None:
    _upsert(conn, "results", result)


def upsert_horse(conn, horse: dict) -> None:
    _upsert(conn, "horses", horse)


def upsert_entry(conn, entry: dict) -> None:
    _upsert(conn, "entries", entry)


def has_race(conn, race_id: str) -> bool:
    return conn.execute("SELECT 1 FROM races WHERE race_id=?", (race_id,)).fetchone() is not None


def has_horse(conn, horse_id: str) -> bool:
    return conn.execute("SELECT 1 FROM horses WHERE horse_id=?", (horse_id,)).fetchone() is not None


def date_done(conn, date: str) -> bool:
    return conn.execute("SELECT 1 FROM fetched_dates WHERE date=?", (date,)).fetchone() is not None


def mark_date_done(conn, date: str, n_races: int) -> None:
    conn.execute("INSERT OR REPLACE INTO fetched_dates (date, n_races) VALUES (?, ?)", (date, n_races))
    conn.commit()


def merge_into(conn, src_path) -> dict:
    """別の DB ファイル(並列取り込みの分割分)の内容を取り込む。既存の行は保持."""
    conn.execute("ATTACH DATABASE ? AS src", (str(src_path),))
    counts = {}
    for t in ("races", "results", "horses", "fetched_dates"):
        before = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        conn.execute(f"INSERT OR IGNORE INTO {t} SELECT * FROM src.{t}")
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] - before
    conn.commit()
    conn.execute("DETACH DATABASE src")
    return counts
