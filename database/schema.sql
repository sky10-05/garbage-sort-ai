PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS prefecture (
    prefecture_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefecture_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS municipality (
    municipality_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prefecture_id INTEGER NOT NULL,
    municipality_name TEXT NOT NULL,
    FOREIGN KEY (prefecture_id) REFERENCES prefecture(prefecture_id),
    UNIQUE (prefecture_id, municipality_name)
);

CREATE TABLE IF NOT EXISTS garbage_master (
    garbage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    garbage_name TEXT NOT NULL,
    yolo_label TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS garbage_type (
    garbage_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS garbage_rule (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality_id INTEGER NOT NULL,
    garbage_id INTEGER NOT NULL,
    garbage_type_id INTEGER NOT NULL,
    guide_text TEXT NOT NULL,
    note TEXT,
    need_question INTEGER NOT NULL DEFAULT 0 CHECK (need_question IN (0, 1)),
    FOREIGN KEY (municipality_id) REFERENCES municipality(municipality_id),
    FOREIGN KEY (garbage_id) REFERENCES garbage_master(garbage_id),
    FOREIGN KEY (garbage_type_id) REFERENCES garbage_type(garbage_type_id),
    UNIQUE (municipality_id, garbage_id)
);

CREATE TABLE IF NOT EXISTS question_type (
    question_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS question_answer (
    answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    question_type_id INTEGER NOT NULL,
    question_order INTEGER NOT NULL CHECK (question_order BETWEEN 1 AND 2),
    answer_value TEXT NOT NULL,
    result_garbage_type_id INTEGER,
    result_guide_text TEXT NOT NULL,
    next_question_type_id INTEGER,
    FOREIGN KEY (rule_id) REFERENCES garbage_rule(rule_id),
    FOREIGN KEY (question_type_id) REFERENCES question_type(question_type_id),
    FOREIGN KEY (result_garbage_type_id) REFERENCES garbage_type(garbage_type_id),
    FOREIGN KEY (next_question_type_id) REFERENCES question_type(question_type_id),
    UNIQUE (rule_id, question_type_id, answer_value)
);

CREATE TABLE IF NOT EXISTS info_question_type (
    info_question_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_text TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS info_answer (
    info_answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    info_question_type_id INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    FOREIGN KEY (rule_id) REFERENCES garbage_rule(rule_id),
    FOREIGN KEY (info_question_type_id) REFERENCES info_question_type(info_question_type_id),
    UNIQUE (rule_id, info_question_type_id)
);

CREATE TABLE IF NOT EXISTS history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    municipality_id INTEGER NOT NULL,
    detected_garbage_id INTEGER,
    detected_label TEXT NOT NULL,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    rule_id INTEGER,
    result_garbage_type_id INTEGER,
    result_guide_text TEXT,
    image_save_consent INTEGER NOT NULL DEFAULT 0 CHECK (image_save_consent IN (0, 1)),
    image_saved INTEGER NOT NULL DEFAULT 0 CHECK (image_saved IN (0, 1)),
    image_path TEXT,
    result_status TEXT NOT NULL CHECK (result_status IN ('success', 'low_confidence', 'unknown', 'no_rule', 'candidate_selected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (municipality_id) REFERENCES municipality(municipality_id),
    FOREIGN KEY (detected_garbage_id) REFERENCES garbage_master(garbage_id),
    FOREIGN KEY (rule_id) REFERENCES garbage_rule(rule_id),
    FOREIGN KEY (result_garbage_type_id) REFERENCES garbage_type(garbage_type_id),
    CHECK (
        (image_save_consent = 0 AND image_saved = 0 AND image_path IS NULL)
        OR (image_save_consent = 1 AND image_saved = 0 AND image_path IS NULL)
        OR (image_save_consent = 1 AND image_saved = 1 AND image_path IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS history_question_answer (
    history_question_answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL,
    question_order INTEGER NOT NULL CHECK (question_order BETWEEN 1 AND 2),
    question_text TEXT NOT NULL,
    answer_value TEXT NOT NULL,
    FOREIGN KEY (history_id) REFERENCES history(history_id),
    UNIQUE (history_id, question_order)
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER,
    municipality_id INTEGER,
    input_garbage_name TEXT,
    comment TEXT,
    image_path TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'reviewed', 'added_to_dataset', 'closed')),
    admin_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (history_id) REFERENCES history(history_id),
    FOREIGN KEY (municipality_id) REFERENCES municipality(municipality_id)
);

CREATE INDEX IF NOT EXISTS idx_municipality_prefecture ON municipality(prefecture_id);
CREATE INDEX IF NOT EXISTS idx_garbage_rule_municipality ON garbage_rule(municipality_id);
CREATE INDEX IF NOT EXISTS idx_garbage_rule_garbage ON garbage_rule(garbage_id);
CREATE INDEX IF NOT EXISTS idx_question_answer_rule ON question_answer(rule_id);
CREATE INDEX IF NOT EXISTS idx_info_answer_rule ON info_answer(rule_id);
CREATE INDEX IF NOT EXISTS idx_history_municipality ON history(municipality_id);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
