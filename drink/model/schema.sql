-- SQLite 表结构。负责人：D（数据结构）。
-- 这是建议版本，D 可以调整，只要 Repository 的行为不变、契约测试通过。

CREATE TABLE IF NOT EXISTS materials (
    id              TEXT PRIMARY KEY,
    name            TEXT    NOT NULL,
    unit            TEXT    NOT NULL,
    capacity        INTEGER NOT NULL CHECK (capacity > 0),
    warn_threshold  INTEGER NOT NULL CHECK (warn_threshold >= 0),
    sort_order      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS menu_items (
    id              TEXT PRIMARY KEY,
    name            TEXT    NOT NULL,
    kind            TEXT    NOT NULL CHECK (kind IN ('BASE', 'ADDON')),
    price_fen       INTEGER NOT NULL CHECK (price_fen >= 0),
    description     TEXT    NOT NULL DEFAULT '',
    color           TEXT    NOT NULL DEFAULT '#cda56c',
    consumption     TEXT    NOT NULL,              -- JSON：{"black_tea": 200, "milk": 150}
    hot_allowed     INTEGER NOT NULL DEFAULT 1,
    iced_allowed    INTEGER NOT NULL DEFAULT 1,
    sort_order      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stock (
    material_id     TEXT PRIMARY KEY REFERENCES materials(id),
    quantity        INTEGER NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    machine_id      TEXT    NOT NULL,
    recipe          TEXT    NOT NULL,              -- JSON：Recipe
    lines           TEXT    NOT NULL,              -- JSON：[OrderLine]
    total_fen       INTEGER NOT NULL,
    status          TEXT    NOT NULL,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    expires_at      INTEGER NOT NULL,
    payment         TEXT,                          -- JSON：PaymentInfo，可为空
    failure_reason  TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_machine_created ON orders(machine_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

CREATE TABLE IF NOT EXISTS restocks (
    record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id     TEXT    NOT NULL REFERENCES materials(id),
    quantity        INTEGER NOT NULL,
    operator        TEXT    NOT NULL,
    created_at      INTEGER NOT NULL
);
