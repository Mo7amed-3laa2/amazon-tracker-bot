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
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                name TEXT,
                last_price REAL,
                previous_price REAL,
                image_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                is_admin BOOLEAN DEFAULT FALSE,
                language TEXT DEFAULT 'en',
                authorized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)

        try:
            conn.execute("ALTER TABLE products ADD COLUMN previous_price REAL")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE products ADD COLUMN user_id INTEGER DEFAULT 0")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN status TEXT DEFAULT 'active'")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN language TEXT DEFAULT 'en'")
        except Exception:
            pass

        conn.commit()


def add_product(user_id: int, url: str, name: str, price: float, image_url: str | None = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO products (user_id, url, name, last_price, previous_price, image_url) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, url, name, price, price, image_url),
        )
        conn.commit()


def get_user_products(user_id: int):
    """Get all products tracked by a specific user."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, url, name, last_price, previous_price, image_url, added_at FROM products WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
    return rows


def get_all_products():
    """Get all unique products across all users (for price checking)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT url, name, last_price, previous_price, image_url FROM products ORDER BY added_at DESC"
        ).fetchall()
    return rows


def update_price(url: str, new_price: float):
    """Update price for all users tracking this URL."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET previous_price = last_price, last_price = ? WHERE url = ?",
            (new_price, url),
        )
        conn.commit()


def get_product_by_url(url: str):
    """Get price info for a specific URL (first user's tracking)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_price, previous_price FROM products WHERE url = ? LIMIT 1",
            (url,)
        ).fetchone()
    return row


def remove_product(product_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()


def get_product_by_id(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, user_id, url, name, last_price, previous_price, image_url, added_at FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
    return row


def get_users_tracking_url(url: str):
    """Get all users tracking a specific URL."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_id, language FROM products p JOIN authorized_users u ON p.user_id = u.user_id WHERE p.url = ? AND u.status = 'active'",
            (url,)
        ).fetchall()
    return rows


# Authorized Users Functions

def is_user_authorized(user_id: int) -> bool:
    """Check if user is authorized and active."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM authorized_users WHERE user_id = ? AND status = 'active'",
            (user_id,)
        ).fetchone()
    return row is not None


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_admin FROM authorized_users WHERE user_id = ? AND status = 'active'",
            (user_id,)
        ).fetchone()
    return row and row[0]


def add_authorized_user(user_id: int, username: str | None = None, is_admin_flag: bool = False):
    """Add a new authorized user."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO authorized_users (user_id, username, is_admin, status) VALUES (?, ?, ?, 'active')",
            (user_id, username, is_admin_flag)
        )
        conn.commit()


def remove_authorized_user(user_id: int):
    """Disable a user (mark as disabled, not deleted)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE authorized_users SET status = 'disabled' WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()


def get_authorized_users():
    """Get all authorized active users."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id, username, is_admin, authorized_at FROM authorized_users WHERE status = 'active' ORDER BY authorized_at DESC"
        ).fetchall()
    return rows


def get_user_info(user_id: int):
    """Get info about a specific authorized user."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id, username, is_admin, status, authorized_at FROM authorized_users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    return row


def get_user_language(user_id: int) -> str:
    """Get user's preferred language (default 'en')."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT language FROM authorized_users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    return row[0] if row else "en"


def set_user_language(user_id: int, language: str):
    """Set user's preferred language."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE authorized_users SET language = ? WHERE user_id = ?",
            (language, user_id)
        )
        conn.commit()


def get_all_authorized_users_for_notification():
    """Get all authorized active users with their language preference."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id, language FROM authorized_users WHERE status = 'active' ORDER BY authorized_at DESC"
        ).fetchall()
    return rows
