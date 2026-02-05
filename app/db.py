"""Database utilities for ICENews web app."""
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Database path configuration
# For Render: Use project root (where app/ directory is located)
# For local development: Same approach
# This works because Render deploys the code and runs from the project root
if os.getenv("RENDER"):
    # Render native Python: Use current working directory which is the project root
    # Alternative: Could use /tmp but that's ephemeral
    # Best bet: Use the directory where the app code lives
    DB_PATH = Path(__file__).resolve().parent.parent / "icenews_social.db"
    print(f"[DB CONFIG] Render mode - DB path: {DB_PATH}", file=sys.stderr, flush=True)
else:
    # Local development
    DB_PATH = Path(__file__).resolve().parent.parent / "icenews_social.db"

# Ensure parent directory exists (create if needed)
# This must happen BEFORE any connection attempts
if not DB_PATH.parent.exists():
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"[DB CONFIG] Created directory: {DB_PATH.parent}", file=sys.stderr, flush=True)
    except (PermissionError, OSError) as e:
        # If we can't create the directory, log it but let the connection fail with a clear error
        print(f"[DB CONFIG] WARNING: Could not create database directory {DB_PATH.parent}: {e}", file=sys.stderr, flush=True)

def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    """
    Clamp an integer into [minimum, maximum].

    Why this exists:
    - Even if the API layer validates inputs, this provides defense-in-depth
      if the DB functions are called from a scheduler, CLI, or future code path.
    - It also prevents accidental "oops" calls like get_posts(limit=1_000_000).
    """
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def get_connection():
    """Return a connection to the SQLite database."""
    # #region agent log
    import json, time
    try:
        with open('/Users/casler/Desktop/casler biz/personal projects/icenews/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"location":"db.py:get_connection:entry","message":"Attempting DB connection","data":{"db_path":str(DB_PATH),"path_exists":DB_PATH.exists() if hasattr(DB_PATH, 'exists') else False},"timestamp":int(time.time()*1000),"sessionId":"debug-session","hypothesisId":"H1,H3"}) + '\n')
    except: pass
    # #endregion
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # #region agent log
    try:
        with open('/Users/casler/Desktop/casler biz/personal projects/icenews/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"location":"db.py:get_connection:success","message":"DB connection successful","data":{"connected":True},"timestamp":int(time.time()*1000),"sessionId":"debug-session","hypothesisId":"H3"}) + '\n')
    except: pass
    # #endregion
    
    return conn


def init_db() -> None:
    """
    Initialize/upgrade the DB schema needed by the web app.
    
    Creates all required tables if they don't exist.
    Safe to run multiple times (uses CREATE TABLE IF NOT EXISTS).
    """
    # #region agent log
    import json, time, os
    try:
        with open('/Users/casler/Desktop/casler biz/personal projects/icenews/.cursor/debug.log', 'a') as f:
            f.write(json.dumps({"location":"db.py:init_db:entry","message":"Starting DB init","data":{"db_path":str(DB_PATH),"is_render":bool(os.getenv("RENDER")),"parent_exists":DB_PATH.parent.exists() if hasattr(DB_PATH.parent, 'exists') else False},"timestamp":int(time.time()*1000),"sessionId":"debug-session","hypothesisId":"H1,H5"}) + '\n')
    except: pass
    # #endregion
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Create accounts table
    cur.execute(
        """
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
        );
        """
    )
    
    # Create posts table
    cur.execute(
        """
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
        );
        """
    )
    
    # Create post_likes table (for global like counts)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS post_likes (
            post_id TEXT PRIMARY KEY,
            like_count INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    
    # Create premium_users table (for paywall access)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS premium_users (
            email TEXT PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            subscription_tier TEXT DEFAULT 'premium',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            notes TEXT
        );
        """
    )
    
    conn.commit()
    conn.close()


def get_posts(
    limit: int = 50,
    offset: int = 0,
    category: Optional[str] = None,
    account_id: Optional[int] = None,
    platform: str = "x",
):
    """Fetch posts with optional filters. Returns list of dicts."""
    # Hard bounds (mirror the API). If you later add roles, you can widen these
    # for admins only — but keep *some* cap to prevent misuse.
    limit = _clamp_int(int(limit), minimum=1, maximum=100)
    offset = _clamp_int(int(offset), minimum=0, maximum=10_000)

    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT p.id, p.platform, p.post_id, p.url, p.tagged_account_handle, p.tagged_hashtags,
               p.language, p.author_handle, p.author_display_name, p.category, p.text,
               p.created_at, p.retrieved_at, p.media_json, p.metrics_json, p.account_id,
               COALESCE(l.like_count, 0) AS like_count
        FROM posts p
        LEFT JOIN post_likes l ON l.post_id = p.post_id
        WHERE p.platform = ?
    """
    params: list = [platform]
    if category:
        query += " AND p.category = ?"
        params.append(category)
    if account_id is not None:
        query += " AND p.account_id = ?"
        params.append(account_id)
    query += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_post_by_post_id(post_id: str):
    """Fetch a single post by platform post_id. Returns dict or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.platform, p.post_id, p.url, p.tagged_account_handle, p.tagged_hashtags,
               p.language, p.author_handle, p.author_display_name, p.category, p.text,
               p.created_at, p.retrieved_at, p.media_json, p.metrics_json, p.raw_json, p.account_id,
               COALESCE(l.like_count, 0) AS like_count
        FROM posts p
        LEFT JOIN post_likes l ON l.post_id = p.post_id
        WHERE p.post_id = ?
    """,
        (post_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def like_post(post_id: str) -> int:
    """Increment and return the global like count for a post_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO post_likes (post_id, like_count, updated_at)
        VALUES (?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(post_id) DO UPDATE SET
            like_count = like_count + 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (post_id,),
    )
    conn.commit()
    cur.execute("SELECT like_count FROM post_likes WHERE post_id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def unlike_post(post_id: str) -> int:
    """Decrement (floored at 0) and return the global like count for a post_id."""
    conn = get_connection()
    cur = conn.cursor()
    # Ensure row exists so UPDATE always has a target.
    cur.execute(
        """
        INSERT INTO post_likes (post_id, like_count, updated_at)
        VALUES (?, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(post_id) DO NOTHING
        """,
        (post_id,),
    )
    cur.execute(
        """
        UPDATE post_likes
        SET like_count = CASE WHEN like_count > 0 THEN like_count - 1 ELSE 0 END,
            updated_at = CURRENT_TIMESTAMP
        WHERE post_id = ?
        """,
        (post_id,),
    )
    conn.commit()
    cur.execute("SELECT like_count FROM post_likes WHERE post_id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_accounts(platform: Optional[str] = None, enabled_only: bool = True):
    """Fetch accounts. Returns list of dicts."""
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT account_id, platform, handle, display_name, category, role, is_enabled
        FROM accounts
        WHERE 1=1
    """
    params: list = []
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    if enabled_only:
        query += " AND is_enabled = 1"
    query += " ORDER BY category, handle"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_post_count(category: Optional[str] = None, account_id: Optional[int] = None):
    """Return total post count with optional filters."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT COUNT(*) FROM posts WHERE platform = 'x'"
    params: list = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if account_id is not None:
        query += " AND account_id = ?"
        params.append(account_id)
    cur.execute(query, params)
    n = cur.fetchone()[0]
    conn.close()
    return n


def is_premium_user(email: str) -> bool:
    """Check if a user has active premium access."""
    if not email:
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT is_active, expires_at 
        FROM premium_users 
        WHERE email = ?
        """,
        (email.lower().strip(),)
    )
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return False
    
    is_active = bool(row[0])
    expires_at = row[1]
    
    # Check if active
    if not is_active:
        return False
    
    # Check expiration (if set)
    if expires_at:
        from datetime import datetime
        try:
            expiry = datetime.fromisoformat(expires_at)
            if datetime.now() > expiry:
                return False
        except (ValueError, TypeError):
            pass  # No expiry or invalid format, treat as active
    
    return True


def add_premium_user(email: str, subscription_tier: str = "premium", expires_at: Optional[str] = None) -> bool:
    """Add a user to premium access list."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO premium_users (email, is_active, subscription_tier, expires_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                is_active = 1,
                subscription_tier = excluded.subscription_tier,
                expires_at = excluded.expires_at
            """,
            (email.lower().strip(), subscription_tier, expires_at)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False
