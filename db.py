"""SQLite 候选人池。每层（召回/精排/触达）都读写同一张表，避免重复召回。"""
import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "scout.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def set_db_path(path):
    """切换数据库文件（多岗位隔离用）。"""
    global DB_PATH
    DB_PATH = path
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d)


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    conn = connect()
    conn.executescript(schema)
    conn.commit()
    conn.close()


def upsert_candidate(cand, query_tag):
    """插入候选人；若 github login 已存在则跳过（不覆盖已有精排结果）。
    返回 True 表示新插入，False 表示已存在。"""
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO candidates
               (source, source_id, name, email, location, bio, company,
                followers, public_repos, languages, signals, html_url, query_tag)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cand["source"], cand["source_id"], cand.get("name"),
                cand.get("email"), cand.get("location"), cand.get("bio"),
                cand.get("company"), cand.get("followers"), cand.get("public_repos"),
                json.dumps(cand.get("languages", []), ensure_ascii=False),
                json.dumps(cand.get("signals", {}), ensure_ascii=False),
                cand.get("html_url"), query_tag,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # 已召回过
    finally:
        conn.close()


def get_unscored(limit=None):
    conn = connect()
    sql = "SELECT * FROM candidates WHERE score IS NULL ORDER BY id"
    if limit:
        sql += " LIMIT %d" % int(limit)
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_score(cand_id, result):
    conn = connect()
    conn.execute(
        """UPDATE candidates
           SET score=?, verdict=?, evidence=?, red_flags=?, outreach_hook=?
           WHERE id=?""",
        (
            result.get("score"), result.get("verdict"),
            json.dumps(result.get("evidence", []), ensure_ascii=False),
            json.dumps(result.get("red_flags", []), ensure_ascii=False),
            result.get("outreach_hook"), cand_id,
        ),
    )
    conn.commit()
    conn.close()


def all_scored(min_score=0):
    """已精排且 >= min_score 的候选人，按分数降序——用于导出/报告。"""
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM candidates WHERE score IS NOT NULL AND score >= ? ORDER BY score DESC",
        (min_score,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def top_candidates(limit=20, min_score=0):
    conn = connect()
    rows = conn.execute(
        """SELECT * FROM candidates
           WHERE score IS NOT NULL AND score >= ?
           ORDER BY score DESC LIMIT ?""",
        (min_score, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
