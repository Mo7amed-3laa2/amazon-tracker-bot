import sqlite3
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "tracker.db"))


@contextmanager
def get_connection():
    """Yield a connection that is committed on success and always closed.

    sqlite3's own context manager commits or rolls back but never closes, so
    `with sqlite3.connect(...)` leaks a handle on every call — which adds up
    fast in a long-running bot. timeout=30 sets busy_timeout so the bot and the
    scheduler wait for each other instead of raising "database is locked".
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        # WAL lets the scheduler read while the bot writes instead of the two
        # blocking each other. It is a persistent property of the file, so this
        # only has to be set once, but re-running it is harmless.
        conn.execute("PRAGMA journal_mode=WAL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                name TEXT,
                last_price REAL,
                previous_price REAL,
                image_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                alert_threshold REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                UNIQUE(user_id, product_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
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

        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_products ON user_products(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_product_price_history ON price_history(product_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_authorized_users_status ON authorized_users(status)")

        try:
            conn.execute("ALTER TABLE products ADD COLUMN previous_price REAL")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE products ADD COLUMN image_url TEXT")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        logger.info("[database] Database initialized successfully")


def add_product(url: str, name: str, price: float, image_url: str | None = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO products (url, name, last_price, previous_price, image_url) VALUES (?, ?, ?, ?, ?)",
            (url, name, price, price, image_url),
        )
        product_id = cursor.lastrowid or conn.execute(
            "SELECT id FROM products WHERE url = ?", (url,)
        ).fetchone()[0]

        # Reuse this connection — opening a second one here would wait on the
        # write lock this one already holds and deadlock until it times out.
        _insert_price_history(conn, product_id, price)
        return product_id


def add_user_product(user_id: int, product_id: int, alert_threshold: float | None = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_products (user_id, product_id, alert_threshold) VALUES (?, ?, ?)",
            (user_id, product_id, alert_threshold),
        )
        conn.commit()


def remove_user_product(user_id: int, product_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM user_products WHERE user_id = ? AND product_id = ?", (user_id, product_id))

        product_used = conn.execute(
            "SELECT COUNT(*) FROM user_products WHERE product_id = ?", (product_id,)
        ).fetchone()[0]

        if product_used == 0:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.execute("DELETE FROM price_history WHERE product_id = ?", (product_id,))

        conn.commit()


def get_all_products():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, url, name, last_price, previous_price, image_url, added_at FROM products ORDER BY added_at DESC"
        ).fetchall()
    return [tuple(row) for row in rows]


def get_user_products(user_id: int):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT p.id, p.url, p.name, p.last_price, p.previous_price, p.image_url, p.added_at, up.alert_threshold
            FROM products p
            JOIN user_products up ON p.id = up.product_id
            WHERE up.user_id = ?
            ORDER BY p.added_at DESC
        """, (user_id,)).fetchall()
    return [tuple(row) for row in rows]


def update_price(url: str, new_price: float):
    with get_connection() as conn:
        product = conn.execute("SELECT id FROM products WHERE url = ?", (url,)).fetchone()
        if product:
            conn.execute(
                "UPDATE products SET previous_price = last_price, last_price = ? WHERE url = ?",
                (new_price, url),
            )
            # Same connection, same reason as add_product — see _insert_price_history.
            _insert_price_history(conn, product[0], new_price)


def _insert_price_history(conn, product_id: int, price: float):
    """Append a price point using a caller-supplied connection.

    Callers that already hold a write transaction MUST use this rather than
    add_price_to_history, which opens its own connection and would deadlock
    against the lock the caller is holding.
    """
    conn.execute(
        "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
        (product_id, price),
    )


def add_price_to_history(product_id: int, price: float):
    with get_connection() as conn:
        _insert_price_history(conn, product_id, price)


def get_price_history(product_id: int, limit: int = 30):
    with get_connection() as conn:
        # Tie-break on id: recorded_at only has second granularity, so two points
        # logged in the same second would otherwise come back in arbitrary order.
        rows = conn.execute(
            "SELECT price, recorded_at FROM price_history WHERE product_id = ? "
            "ORDER BY recorded_at DESC, id DESC LIMIT ?",
            (product_id, limit),
        ).fetchall()
    return [tuple(row) for row in rows]


def remove_product(product_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM user_products WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM price_history WHERE product_id = ?", (product_id,))
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()


def get_product_by_id(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, url, name, last_price, previous_price, image_url, added_at FROM products WHERE id = ?",
            (product_id,),
        ).fetchone()
    return tuple(row) if row else None


def get_product_by_url(url: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, url, name, last_price, previous_price, image_url, added_at FROM products WHERE url = ?",
            (url,),
        ).fetchone()
    return tuple(row) if row else None


def is_user_authorized(user_id: int) -> bool:
    """Check if user is authorized."""
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
    return row and row[0] if row else False


def add_authorized_user(user_id: int, username: str | None = None, is_admin_flag: bool = False):
    """Add or reactivate authorized user."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM authorized_users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE authorized_users SET status = 'active', username = ?, is_admin = ? WHERE user_id = ?",
                (username, is_admin_flag, user_id)
            )
        else:
            conn.execute(
                "INSERT INTO authorized_users (user_id, username, is_admin, language, status) VALUES (?, ?, ?, 'en', 'active')",
                (user_id, username, is_admin_flag)
            )
        conn.commit()
        logger.info(f"[database] User {user_id} ({username}) authorized with admin={is_admin_flag}")


def remove_authorized_user(user_id: int):
    """Disable user."""
    with get_connection() as conn:
        conn.execute("UPDATE authorized_users SET status = 'disabled' WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_products WHERE user_id = ?", (user_id,))
        conn.commit()
        logger.info(f"[database] User {user_id} disabled")


def get_authorized_users():
    """Get all authorized users."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id, username, is_admin, authorized_at FROM authorized_users WHERE status = 'active' ORDER BY authorized_at DESC"
        ).fetchall()
    return [tuple(row) for row in rows]


def get_user_language(user_id: int) -> str:
    """Get user's language preference."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT language FROM authorized_users WHERE user_id = ? AND status = 'active'",
            (user_id,)
        ).fetchone()
    return row[0] if row else "en"


def set_user_language(user_id: int, language: str):
    """Save user's language preference."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM authorized_users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE authorized_users SET language = ? WHERE user_id = ?",
                (language, user_id)
            )
        else:
            conn.execute(
                "INSERT INTO authorized_users (user_id, language, status) VALUES (?, ?, 'active')",
                (user_id, language)
            )
        conn.commit()
        logger.info(f"[database] User {user_id} language set to {language}")


def get_all_authorized_users_for_notification():
    """Get all active users with their language for notifications."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id, language FROM authorized_users WHERE status = 'active'"
        ).fetchall()
    return [tuple(row) for row in rows]


def get_user_for_product_notification(product_id: int):
    """Get all users tracking this product with their language."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT au.user_id, au.language
            FROM authorized_users au
            JOIN user_products up ON au.user_id = up.user_id
            WHERE up.product_id = ? AND au.status = 'active'
        """, (product_id,)).fetchall()
    return [tuple(row) for row in rows]
