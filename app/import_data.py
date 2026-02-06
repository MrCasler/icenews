"""
Import accounts, posts, and post_likes into the app database.
Runnable on Render as: python -m app.import_data path/to/export.sql
(or cat export.sql | python -m app.import_data)
Never touches premium_users.
"""
import sys
from pathlib import Path

from app.db import get_connection


ACCOUNTS_CREATE = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    handle TEXT NOT NULL,
    display_name TEXT NOT NULL,
    category TEXT CHECK (category IN ('government', 'independent','unknown', 'other')),
    role TEXT,
    is_enabled BOOLEAN NOT NULL DEFAULT 1,
    verification_url TEXT,
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
POSTS_CREATE = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL UNIQUE,
    tagged_account_handle TEXT,
    tagged_hashtags TEXT,
    language TEXT,
    author_handle TEXT NOT NULL,
    author_display_name TEXT NOT NULL,
    category TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retrieved_at DATETIME,
    media_json TEXT,
    metrics_json TEXT,
    raw_json TEXT,
    account_id INTEGER,
    reply_to_post_id TEXT,
    quoted_post_id TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts (account_id) ON DELETE CASCADE
)
"""
POST_LIKES_CREATE = """
CREATE TABLE IF NOT EXISTS post_likes (
    post_id TEXT PRIMARY KEY,
    like_count INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def run_import(sql: str) -> str:
    """Run the import; returns a short status message. Raises on error."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DROP TABLE IF EXISTS post_likes")
        cur.execute("DROP TABLE IF EXISTS posts")
        cur.execute("DROP TABLE IF EXISTS accounts")
        conn.commit()

        is_full = "PRAGMA" in sql.upper() or "CREATE TABLE" in sql.upper()
        if is_full:
            cur.executescript(sql)
        else:
            cur.execute(ACCOUNTS_CREATE)
            cur.execute(POSTS_CREATE)
            cur.execute(POST_LIKES_CREATE)
            conn.commit()
            cur.executescript(sql)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM accounts")
        n_accounts = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM posts")
        n_posts = cur.fetchone()[0]
        try:
            cur.execute("SELECT COUNT(*) FROM post_likes")
            n_likes = cur.fetchone()[0]
        except Exception:
            n_likes = 0
        return f"Done: {n_accounts} accounts, {n_posts} posts, {n_likes} like rows. Premium users unchanged."
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) > 1:
        sql_path = Path(sys.argv[1])
        if not sql_path.exists():
            print(f"Error: file not found: {sql_path}", file=sys.stderr)
            sys.exit(1)
        sql = sql_path.read_text()
    else:
        sql = sys.stdin.read()

    sql = sql.strip()
    if not sql:
        print("Error: no SQL provided (file or stdin).", file=sys.stderr)
        sys.exit(1)

    try:
        msg = run_import(sql)
        print(msg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
