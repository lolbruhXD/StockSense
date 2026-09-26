"""SQLite setup and small conversion helpers shared by the API and domain layer."""

import os
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path


DB_PATH = Path(os.environ.get("STOCKSENSE_DB", "data/stocksense.sqlite3"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    UNIQUE(warehouse_id, code)
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    uom TEXT NOT NULL,
    unit_cost_cents INTEGER NOT NULL DEFAULT 0 CHECK(unit_cost_cents >= 0),
    reorder_milli INTEGER NOT NULL DEFAULT 0 CHECK(reorder_milli >= 0),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stock_levels (
    product_id INTEGER NOT NULL REFERENCES products(id),
    location_id INTEGER NOT NULL REFERENCES locations(id),
    quantity_milli INTEGER NOT NULL DEFAULT 0 CHECK(quantity_milli >= 0),
    PRIMARY KEY(product_id, location_id)
);
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK(type IN ('receipt','delivery','transfer','adjustment')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','waiting','ready','done','canceled')),
    from_location_id INTEGER REFERENCES locations(id),
    to_location_id INTEGER REFERENCES locations(id),
    partner TEXT NOT NULL DEFAULT '',
    scheduled_date TEXT NOT NULL DEFAULT '',
    responsible_id INTEGER REFERENCES users(id),
    picked INTEGER NOT NULL DEFAULT 0,
    packed INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS operation_lines (
    id INTEGER PRIMARY KEY,
    operation_id INTEGER NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity_milli INTEGER NOT NULL CHECK(quantity_milli >= 0),
    UNIQUE(operation_id, product_id)
);
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY,
    operation_id INTEGER NOT NULL REFERENCES operations(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    location_id INTEGER NOT NULL REFERENCES locations(id),
    delta_milli INTEGER NOT NULL,
    balance_milli INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_operations_type_status ON operations(type, status);
CREATE INDEX IF NOT EXISTS idx_movements_product_date ON movements(product_id, id DESC);
"""


def connect(path=None):
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def initialize(path=None):
    db = connect(path)
    try:
        db.executescript(SCHEMA)
    finally:
        db.close()


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
        raise ValueError("Quantity must be positive" if not allow_zero else "Quantity cannot be negative")
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
    if not scaled.is_finite() or scaled != scaled.to_integral_value() or scaled < 0 or scaled > 9_000_000_000_000:
        raise ValueError("Unit cost must be a nonnegative amount with two decimal places")
    return int(scaled)
