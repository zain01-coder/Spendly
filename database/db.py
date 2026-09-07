import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "expense_tracker.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    today = date.today()
    y, m = today.year, today.month

    sample_expenses = [
        (12.50, "Food", f"{y:04d}-{m:02d}-02", "Lunch at cafe"),
        (45.00, "Transport", f"{y:04d}-{m:02d}-04", "Monthly bus pass"),
        (120.00, "Bills", f"{y:04d}-{m:02d}-05", "Electricity bill"),
        (30.00, "Health", f"{y:04d}-{m:02d}-08", "Pharmacy - vitamins"),
        (15.75, "Entertainment", f"{y:04d}-{m:02d}-10", "Movie ticket"),
        (60.00, "Shopping", f"{y:04d}-{m:02d}-14", "New shoes"),
        (8.25, "Other", f"{y:04d}-{m:02d}-18", "Miscellaneous"),
        (22.00, "Food", f"{y:04d}-{m:02d}-21", "Groceries"),
    ]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [(user_id, amt, cat, dt, desc) for amt, cat, dt, desc in sample_expenses],
    )
    conn.commit()
    conn.close()
