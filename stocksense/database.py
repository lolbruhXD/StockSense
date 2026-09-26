"""SQLite storage for the local StockSense server."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

DB_PATH = Path(os.environ.get("STOCKSENSE_DB", "data/stocksense.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(id, organization_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS invitations (
    token_hash TEXT PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    email TEXT NOT NULL COLLATE NOCASE,
    invited_by INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    FOREIGN KEY (invited_by, organization_id) REFERENCES users(id, organization_id)
);
CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    UNIQUE(organization_id, name),
    UNIQUE(organization_id, code),
    UNIQUE(id, organization_id)
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    warehouse_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    UNIQUE(organization_id, warehouse_id, code),
    UNIQUE(id, organization_id),
    FOREIGN KEY (warehouse_id, organization_id) REFERENCES warehouses(id, organization_id)
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL,
    UNIQUE(organization_id, name),
    UNIQUE(id, organization_id)
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    sku TEXT NOT NULL COLLATE NOCASE,
    name TEXT NOT NULL,
    category_id INTEGER,
    uom TEXT NOT NULL,
    unit_cost_cents INTEGER NOT NULL DEFAULT 0 CHECK(unit_cost_cents >= 0),
    reorder_milli INTEGER NOT NULL DEFAULT 0 CHECK(reorder_milli >= 0),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(organization_id, sku),
    UNIQUE(id, organization_id),
    FOREIGN KEY (category_id, organization_id) REFERENCES categories(id, organization_id)
);
CREATE TABLE IF NOT EXISTS stock_levels (
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    product_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    quantity_milli INTEGER NOT NULL DEFAULT 0 CHECK(quantity_milli >= 0),
    PRIMARY KEY(organization_id, product_id, location_id),
    FOREIGN KEY (product_id, organization_id) REFERENCES products(id, organization_id),
    FOREIGN KEY (location_id, organization_id) REFERENCES locations(id, organization_id)
);
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    reference TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('receipt','delivery','transfer','adjustment')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','waiting','ready','done','canceled')),
    from_location_id INTEGER,
    to_location_id INTEGER,
    partner TEXT NOT NULL DEFAULT '',
    scheduled_date TEXT NOT NULL DEFAULT '',
    responsible_id INTEGER,
    picked INTEGER NOT NULL DEFAULT 0,
    packed INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(organization_id, reference),
    UNIQUE(id, organization_id),
    FOREIGN KEY (from_location_id, organization_id) REFERENCES locations(id, organization_id),
    FOREIGN KEY (to_location_id, organization_id) REFERENCES locations(id, organization_id),
    FOREIGN KEY (responsible_id, organization_id) REFERENCES users(id, organization_id)
);
CREATE TABLE IF NOT EXISTS operation_lines (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    operation_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity_milli INTEGER NOT NULL CHECK(quantity_milli >= 0),
    UNIQUE(organization_id, operation_id, product_id),
    FOREIGN KEY (operation_id, organization_id) REFERENCES operations(id, organization_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id, organization_id) REFERENCES products(id, organization_id)
);
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    operation_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    delta_milli INTEGER NOT NULL,
    balance_milli INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (operation_id, organization_id) REFERENCES operations(id, organization_id),
    FOREIGN KEY (product_id, organization_id) REFERENCES products(id, organization_id),
    FOREIGN KEY (location_id, organization_id) REFERENCES locations(id, organization_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_invitations_company ON invitations(organization_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_operations_type_status ON operations(organization_id, type, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_operations_company_id ON operations(organization_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_operations_pending_type ON operations(organization_id, type)
    WHERE status NOT IN ('done','canceled');
CREATE INDEX IF NOT EXISTS idx_movements_product_date ON movements(organization_id, product_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_movements_company_id ON movements(organization_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_stock_levels_location ON stock_levels(organization_id, location_id, product_id);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(organization_id, name, id);
"""

TABLES = (
    "users", "sessions", "password_resets", "warehouses", "locations",
    "categories", "products", "stock_levels", "operations", "operation_lines",
    "movements",
)
TENANT_TABLES = set(TABLES) - {"sessions", "password_resets"}


class Connection(sqlite3.Connection):
    organization_id = None


def connect(path=None):
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=10, isolation_level=None, factory=Connection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    return db


def initialize(path=None):
    db = connect(path)
    try:
        db.execute("PRAGMA journal_mode = WAL")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        old_database = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if version not in (0, 2):
            raise RuntimeError(f"Unsupported database version: {version}")
        if version == 0 and old_database:
            migrate_legacy(db)
        else:
            db.executescript(SCHEMA)
            db.execute("PRAGMA user_version = 2")
        db.execute(
            "DELETE FROM sessions WHERE expires_at<=?",
            (datetime.now(timezone.utc).isoformat(),),
        )
    finally:
        db.close()


def migrate_legacy(db):
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        script = ["BEGIN IMMEDIATE;"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
            script.append(f'DROP INDEX IF EXISTS "{row["name"]}";')
        for table in TABLES:
            script.append(f"ALTER TABLE {table} RENAME TO legacy_{table};")
        script.append(SCHEMA)
        script.append("INSERT INTO organizations(id,name) VALUES (1,'StockSense workspace');")
        for table in TABLES:
            columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]
            names = values = ",".join(columns)
            if table in TENANT_TABLES:
                names += ",organization_id"
                values += ",1"
            script.append(f"INSERT INTO {table}({names}) SELECT {values} FROM legacy_{table};")
        for table in reversed(TABLES):
            script.append(f"DROP TABLE legacy_{table};")
        script.append("PRAGMA user_version = 2;")
        script.append("COMMIT;")
        db.executescript("\n".join(script))
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys = ON")
    problems = list(db.execute("PRAGMA foreign_key_check"))
    if problems:
        raise RuntimeError("Database migration left invalid references")


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()


def milli(value, *, allow_zero=False):
    try:
        number = Decimal(str(value))
        scaled = number * 1000
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid quantity") from None
    if not scaled.is_finite() or scaled != scaled.to_integral_value():
        raise ValueError("Quantities support up to three decimal places")
    if scaled < 0 or (scaled == 0 and not allow_zero):
        raise ValueError(
            "Quantity must be positive"
            if not allow_zero
            else "Quantity cannot be negative"
        )
    if scaled > 9_000_000_000_000:
        raise ValueError("Quantity is too large")
    return int(scaled)


def quantity(value):
    return value / 1000


def money_cents(value):
    try:
        scaled = Decimal(str(value)) * 100
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid unit cost") from None
    if (
        not scaled.is_finite()
        or scaled != scaled.to_integral_value()
        or scaled < 0
        or scaled > 9_000_000_000_000
    ):
        raise ValueError(
            "Unit cost must be a nonnegative amount with two decimal places"
        )
    return int(scaled)
