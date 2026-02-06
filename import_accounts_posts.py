#!/usr/bin/env python3
"""
Import accounts, posts, and post_likes (like counts) into the app database. Safe to run locally or in Render shell.
Never touches premium_users.

Usage:
  python import_accounts_posts.py path/to/export.sql
  cat export.sql | python import_accounts_posts.py

Uses the same database as the web app (see app/db.py). On Render, run from project root in a shell.
"""
import sys
from pathlib import Path

# Run from project root so app is importable
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

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


def main():
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

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Drop order: post_likes, posts, accounts (same group; premium_users never touched)
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
        print(f"Done: {n_accounts} accounts, {n_posts} posts, {n_likes} like rows. Premium users unchanged.")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
