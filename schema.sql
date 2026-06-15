-- Scout 候选人池：贯穿召回 -> 精排 -> 触达全程，每层结果回写。
CREATE TABLE IF NOT EXISTS candidates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,            -- 'github'（v1 只有这一个源）
    source_id    TEXT NOT NULL,            -- github login，做去重用
    name         TEXT,
    email        TEXT,
    location     TEXT,
    bio          TEXT,
    company      TEXT,
    followers    INTEGER,
    public_repos INTEGER,
    languages    TEXT,                     -- JSON：该候选人贡献的主要语言
    signals      TEXT,                     -- JSON：召回时记下的命中信号（仓库名/stars 等）
    html_url     TEXT,
    query_tag    TEXT,                     -- 哪次画像查询召回的，便于复盘
    -- 精排回写字段
    score        INTEGER,                  -- 0-100，NULL = 尚未精排
    verdict      TEXT,                     -- 值得联系 / 观望 / 跳过
    evidence     TEXT,                     -- JSON 数组
    red_flags    TEXT,                     -- JSON 数组
    outreach_hook TEXT,                    -- 可直接用的开场白
    -- 触达状态
    status       TEXT DEFAULT 'new',       -- new / contacted / replied / rejected
    created_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
