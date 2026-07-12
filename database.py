import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                name TEXT,
                last_price REAL,
                image_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        try:
            conn.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
        except Exception:
            pass

        conn.commit()


def add_product(url: str, name: str, price: float, image_url: str | None = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO products (url, name, last_price, image_url) VALUES (?, ?, ?, ?)",
            (url, name, price, image_url),
        )
        conn.commit()


def get_all_products():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, url, name, last_price, image_url, added_at FROM products ORDER BY added_at DESC"
        ).fetchall()
    return rows


def update_price(url: str, new_price: float):
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET last_price = ? WHERE url = ?",
            (new_price, url),
        )
        conn.commit()


def remove_product(product_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()


def get_product_by_id(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, url, name, last_price, image_url, added_at FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
    return row
