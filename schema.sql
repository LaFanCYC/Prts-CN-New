PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    student_no TEXT NOT NULL UNIQUE,
    grade TEXT NOT NULL,
    class_name TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'admin')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),
    credit_score INTEGER NOT NULL DEFAULT 100 CHECK (credit_score BETWEEN 0 AND 120),
    credit_recovered_on TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    condition_level TEXT NOT NULL,
    transfer_mode TEXT NOT NULL CHECK (transfer_mode IN ('borrow', 'exchange', 'gift', 'free_help', 'skill_exchange')),
    description TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    image_name TEXT,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'in_use', 'in_service', 'completed', 'withdrawn')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL REFERENCES resources(id),
    applicant_id INTEGER NOT NULL REFERENCES users(id),
    note TEXT NOT NULL DEFAULT '',
    rejection_reason TEXT NOT NULL DEFAULT '',
    expected_return_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'borrowed', 'return_pending', 'returned', 'rejected', 'completed', 'in_service', 'completion_pending', 'withdrawn')),
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    action_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS one_pending_application
ON applications(resource_id, applicant_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS applications_resource_status
ON applications(resource_id, status);

CREATE TABLE IF NOT EXISTS lost_found (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('lost', 'found')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    location TEXT NOT NULL,
    keywords TEXT NOT NULL,
    image_name TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'withdrawn')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lost_id INTEGER NOT NULL REFERENCES lost_found(id),
    found_id INTEGER NOT NULL REFERENCES lost_found(id),
    score REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lost_id, found_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    message TEXT NOT NULL,
    target_url TEXT NOT NULL,
    dedupe_key TEXT UNIQUE,
    is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS resources_search ON resources(status, category, transfer_mode);
CREATE INDEX IF NOT EXISTS lost_found_search ON lost_found(kind, status, created_at);
CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id, is_read, created_at);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL REFERENCES users(id),
    section TEXT NOT NULL CHECK (section IN ('resource', 'lost_found', 'study', 'campus', 'feedback')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    image_name TEXT,
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'pending', 'withdrawn')),
    moderation_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS post_tags (
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL REFERENCES users(id),
    target_type TEXT NOT NULL CHECK (target_type IN ('post', 'resource', 'lost_found')),
    target_id INTEGER NOT NULL,
    parent_id INTEGER REFERENCES comments(id),
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'withdrawn')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    target_type TEXT NOT NULL CHECK (target_type IN ('post', 'resource', 'lost_found')),
    target_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('like', 'favorite')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, target_type, target_id, kind)
);

CREATE TABLE IF NOT EXISTS user_follows (
    follower_id INTEGER NOT NULL REFERENCES users(id),
    followed_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (follower_id != followed_id),
    PRIMARY KEY (follower_id, followed_id)
);

CREATE TABLE IF NOT EXISTS tag_follows (
    user_id INTEGER NOT NULL REFERENCES users(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, tag_id)
);

CREATE TABLE IF NOT EXISTS reposts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL REFERENCES users(id),
    post_id INTEGER NOT NULL REFERENCES posts(id),
    comment TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'withdrawn')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (author_id, post_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id INTEGER NOT NULL REFERENCES users(id),
    target_type TEXT NOT NULL CHECK (target_type IN ('post', 'resource', 'lost_found', 'comment')),
    target_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'rejected')),
    resolution TEXT NOT NULL DEFAULT '',
    moderator_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_report
ON reports(reporter_id, target_type, target_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS moderation_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    severity TEXT NOT NULL CHECK (severity IN ('reject', 'review')),
    note TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS account_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('mute', 'temp_ban')),
    reason TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS behavior_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('view_post', 'view_section', 'like', 'favorite', 'comment', 'repost')),
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    event_date TEXT NOT NULL DEFAULT (DATE('now')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, event_type, target_type, target_id, event_date)
);

CREATE TABLE IF NOT EXISTS backup_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('daily', 'weekly', 'manual')),
    size_bytes INTEGER NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    api_endpoint TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    max_results INTEGER NOT NULL DEFAULT 10 CHECK (max_results BETWEEN 1 AND 10),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS credit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL CHECK (balance_after BETWEEN 0 AND 120),
    event_type TEXT NOT NULL,
    reference_type TEXT NOT NULL DEFAULT '',
    reference_id INTEGER,
    reason TEXT NOT NULL,
    actor_id INTEGER REFERENCES users(id),
    event_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS credit_appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE REFERENCES credit_events(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'upheld', 'rejected')),
    admin_comment TEXT NOT NULL DEFAULT '',
    handled_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at TEXT
);

CREATE INDEX IF NOT EXISTS posts_feed ON posts(status, section, created_at);
CREATE INDEX IF NOT EXISTS comments_target ON comments(target_type, target_id, status, created_at);
CREATE INDEX IF NOT EXISTS reactions_target ON content_reactions(target_type, target_id, kind);
CREATE INDEX IF NOT EXISTS reposts_post ON reposts(post_id, status, created_at);
CREATE INDEX IF NOT EXISTS reports_queue ON reports(status, created_at);
CREATE INDEX IF NOT EXISTS restrictions_user ON account_restrictions(user_id, is_active, ends_at);
CREATE INDEX IF NOT EXISTS audit_recent ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS behavior_user ON behavior_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS credit_events_user ON credit_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS credit_appeals_status ON credit_appeals(status, created_at);
