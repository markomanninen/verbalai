CREATE TABLE IF NOT EXISTS data (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    value TEXT,
    key_group TEXT,
    updated TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (key, key_group)
);

CREATE TABLE IF NOT EXISTS discussions (
    id INTEGER PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    title TEXT,
    starttime TEXT DEFAULT CURRENT_TIMESTAMP,
    endtime TEXT,
    featured INTEGER default 0,
    cost REAL default 0.0
);

CREATE TABLE IF NOT EXISTS dialogue_units (
    id INTEGER PRIMARY KEY,
    prompt TEXT,
    response TEXT,
    intent TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    discussion_id TEXT,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id)
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS dialogue_unit_topics (
    dialogue_unit_id INTEGER,
    topic_id INTEGER,
    FOREIGN KEY (dialogue_unit_id) REFERENCES dialogue_units(id),
    FOREIGN KEY (topic_id) REFERENCES topics(id),
    PRIMARY KEY (dialogue_unit_id, topic_id)
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT,
    score REAL,
    discussion_id INTEGER,
    FOREIGN KEY (discussion_id) REFERENCES discussions(id)
);

CREATE TABLE IF NOT EXISTS sentiment_scores (
    dialogue_unit_id INTEGER,
    positive_score REAL,
    negative_score REAL,
    FOREIGN KEY (dialogue_unit_id) REFERENCES dialogue_units(id),
    PRIMARY KEY (dialogue_unit_id)
);
