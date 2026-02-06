#!/usr/bin/env python3
"""
One-time script to add missing columns to the posts table.
Run locally or in Render Shell (uses same DB as app). No web import endpoint.

Usage: python fix_remote_schema.py
"""
import sys
from pathlib import Path

if __name__ == "__main__":
    _root = Path(__file__).resolve().parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from app.db import get_connection

ALTER_SQL = """
ALTER TABLE posts ADD COLUMN reply_to_post_id TEXT;
ALTER TABLE posts ADD COLUMN quoted_post_id TEXT;
"""

def main():
    conn = get_connection()
    cur = conn.cursor()
    try:
        for stmt in ALTER_SQL.strip().split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
        conn.commit()
        print("Schema updated. You can run: python import_accounts_posts.py export.sql")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
