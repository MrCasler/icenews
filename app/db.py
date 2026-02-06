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


def _ensure_post_likes_has_dislike_count_on_conn(conn: sqlite3.Connection) -> None:
    """Ensure post_likes.dislike_count exists on this connection. Run before any query that uses l.dislike_count."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='post_likes'")
    if cur.fetchone() is None:
        return
    cur.execute("PRAGMA table_info(post_likes)")
    columns = [row[1] for row in cur.fetchall()]
    if "dislike_count" not in columns:
        cur.execute("ALTER TABLE post_likes ADD COLUMN dislike_count INTEGER NOT NULL DEFAULT 0")
        conn.commit()


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
    
    # Create post_likes table (for global like counts and dislikes)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS post_likes (
            post_id TEXT PRIMARY KEY,
            like_count INTEGER NOT NULL DEFAULT 0,
            dislike_count INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    # Migration: add dislike_count to existing DBs that don't have it (e.g. Render DB created before this column)
    cur.execute("PRAGMA table_info(post_likes)")
    columns = [row[1] for row in cur.fetchall()]
    if "dislike_count" not in columns:
        cur.execute("ALTER TABLE post_likes ADD COLUMN dislike_count INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    
    # Create premium_users table (for paywall access - legacy, kept for compatibility)
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
    
    # Create users table (main user management with Stripe integration)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            nickname TEXT,
            is_premium BOOLEAN DEFAULT 0,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            premium_expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME
        );
        """
    )
    
    # Create magic_links table (for passwordless authentication)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS magic_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at DATETIME NOT NULL,
            used BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    
    # Create downloads table (public gallery of all downloads)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id TEXT,
            source_url TEXT NOT NULL,
            platform TEXT,
            title TEXT,
            file_path TEXT,
            thumbnail_url TEXT,
            is_user_submitted BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    
    # V2: Create user_posts table (community-submitted posts)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            media_urls TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_approved BOOLEAN DEFAULT 1,
            like_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    
    # V2: Create twitter_connections table (OAuth connections)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS twitter_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            twitter_id TEXT NOT NULL,
            twitter_handle TEXT,
            twitter_avatar TEXT,
            access_token TEXT,
            refresh_token TEXT,
            connected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    
    # V2: Add avatar_url and bio columns to users if they don't exist
    try:
        cur.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    except:
        pass  # Column already exists
    
    try:
        cur.execute("ALTER TABLE users ADD COLUMN bio TEXT")
    except:
        pass  # Column already exists
    
    try:
        cur.execute("ALTER TABLE downloads ADD COLUMN description TEXT")
    except:
        pass  # Column already exists
    
    try:
        cur.execute("ALTER TABLE downloads ADD COLUMN related_links TEXT")
    except:
        pass  # Column already exists
    
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
    limit = _clamp_int(int(limit), minimum=1, maximum=100)
    offset = _clamp_int(int(offset), minimum=0, maximum=10_000)
    conn = get_connection()
    _ensure_post_likes_has_dislike_count_on_conn(conn)
    cur = conn.cursor()
    query = """
        SELECT p.id, p.platform, p.post_id, p.url, p.tagged_account_handle, p.tagged_hashtags,
               p.language, p.author_handle, p.author_display_name, p.category, p.text,
               p.created_at, p.retrieved_at, p.media_json, p.metrics_json, p.account_id,
               COALESCE(l.like_count, 0) AS like_count,
               COALESCE(l.dislike_count, 0) AS dislike_count
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
    _ensure_post_likes_has_dislike_count_on_conn(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.platform, p.post_id, p.url, p.tagged_account_handle, p.tagged_hashtags,
               p.language, p.author_handle, p.author_display_name, p.category, p.text,
               p.created_at, p.retrieved_at, p.media_json, p.metrics_json, p.raw_json, p.account_id,
               COALESCE(l.like_count, 0) AS like_count,
               COALESCE(l.dislike_count, 0) AS dislike_count
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


def dislike_post(post_id: str) -> int:
    """Increment and return the dislike count for a post_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO post_likes (post_id, like_count, dislike_count, updated_at)
        VALUES (?, 0, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(post_id) DO UPDATE SET
            dislike_count = dislike_count + 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (post_id,),
    )
    conn.commit()
    cur.execute("SELECT dislike_count FROM post_likes WHERE post_id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def undislike_post(post_id: str) -> int:
    """Decrement (floored at 0) and return the dislike count for a post_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO post_likes (post_id, like_count, dislike_count, updated_at)
        VALUES (?, 0, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(post_id) DO NOTHING
        """,
        (post_id,),
    )
    cur.execute(
        """
        UPDATE post_likes
        SET dislike_count = CASE WHEN dislike_count > 0 THEN dislike_count - 1 ELSE 0 END,
            updated_at = CURRENT_TIMESTAMP
        WHERE post_id = ?
        """,
        (post_id,),
    )
    conn.commit()
    cur.execute("SELECT dislike_count FROM post_likes WHERE post_id = ?", (post_id,))
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


# ============================================================================
# User Management Functions (new auth system)
# ============================================================================

def create_or_get_user(email: str) -> Optional[dict]:
    """Create a new user or get existing user by email. Returns user dict."""
    email = email.lower().strip()
    conn = get_connection()
    cur = conn.cursor()
    
    # Try to get existing user
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    
    if row:
        conn.close()
        return dict(row)
    
    # Create new user
    try:
        cur.execute(
            "INSERT INTO users (email, created_at) VALUES (?, CURRENT_TIMESTAMP)",
            (email,)
        )
        conn.commit()
        user_id = cur.lastrowid
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        conn.close()
        return None


def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email. Returns user dict or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Get user by ID. Returns user dict or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_premium_status(
    email: str,
    is_premium: bool,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    premium_expires_at: Optional[str] = None
) -> bool:
    """Update user's premium status and Stripe info."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE users SET
                is_premium = ?,
                stripe_customer_id = COALESCE(?, stripe_customer_id),
                stripe_subscription_id = COALESCE(?, stripe_subscription_id),
                premium_expires_at = ?
            WHERE email = ?
            """,
            (is_premium, stripe_customer_id, stripe_subscription_id, premium_expires_at, email.lower().strip())
        )
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception:
        conn.close()
        return False


def update_user_nickname(user_id: int, nickname: str) -> bool:
    """Update user's nickname."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET nickname = ? WHERE id = ?",
            (nickname.strip()[:50], user_id)  # Limit nickname to 50 chars
        )
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception:
        conn.close()
        return False


def update_user_last_login(user_id: int) -> bool:
    """Update user's last login timestamp."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,)
        )
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception:
        conn.close()
        return False


# ============================================================================
# Magic Link Functions
# ============================================================================

def save_magic_link(email: str, token: str, expires_at: str) -> bool:
    """Save a magic link token for email verification."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Invalidate any existing unused tokens for this email
        cur.execute(
            "UPDATE magic_links SET used = 1 WHERE email = ? AND used = 0",
            (email.lower().strip(),)
        )
        # Insert new token
        cur.execute(
            """
            INSERT INTO magic_links (email, token, expires_at, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (email.lower().strip(), token, expires_at)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def get_magic_link(token: str) -> Optional[dict]:
    """Get magic link by token. Returns dict or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM magic_links WHERE token = ?",
        (token,)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def mark_magic_link_used(token: str) -> bool:
    """Mark a magic link as used."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE magic_links SET used = 1 WHERE token = ?",
            (token,)
        )
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception:
        conn.close()
        return False


# ============================================================================
# Downloads Functions (public gallery)
# ============================================================================

def save_download(
    user_id: int,
    source_url: str,
    platform: Optional[str] = None,
    post_id: Optional[str] = None,
    title: Optional[str] = None,
    file_path: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    is_user_submitted: bool = False,
    description: Optional[str] = None,
    related_links: Optional[str] = None,
) -> Optional[int]:
    """Save a download record. Returns download ID or None."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO downloads (user_id, source_url, platform, post_id, title, file_path, thumbnail_url, is_user_submitted, description, related_links, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, source_url or "", platform, post_id, title, file_path, thumbnail_url, is_user_submitted, description, related_links)
        )
        conn.commit()
        download_id = cur.lastrowid
        conn.close()
        return download_id
    except Exception:
        conn.close()
        return None


def get_user_by_twitter_id(twitter_id: str):
    """Get user by X/Twitter ID. Returns user dict or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.* FROM users u
        JOIN twitter_connections tc ON u.id = tc.user_id
        WHERE tc.twitter_id = ?
        """,
        (twitter_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def save_twitter_connection(
    user_id: int,
    twitter_id: str,
    twitter_handle: str,
    twitter_avatar: Optional[str] = None,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
):
    """Save or update X/Twitter connection for user."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO twitter_connections
            (user_id, twitter_id, twitter_handle, twitter_avatar, access_token, refresh_token)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                twitter_id = excluded.twitter_id,
                twitter_handle = excluded.twitter_handle,
                twitter_avatar = excluded.twitter_avatar,
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token
            """,
            (user_id, twitter_id, twitter_handle, twitter_avatar, access_token, refresh_token),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def get_download_by_id(download_id: int):
    """Get a single download by id. Returns dict or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT d.*, u.nickname, u.email FROM downloads d JOIN users u ON d.user_id = u.id WHERE d.id = ?",
        (download_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_downloads(limit: int = 50, offset: int = 0, platform: Optional[str] = None) -> list:
    """Get all downloads for public gallery. Returns list of dicts with user info."""
    limit = _clamp_int(int(limit), minimum=1, maximum=100)
    offset = _clamp_int(int(offset), minimum=0, maximum=10_000)
    
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
        SELECT d.*, u.nickname, u.email
        FROM downloads d
        JOIN users u ON d.user_id = u.id
        WHERE 1=1
    """
    params: list = []
    
    if platform:
        query += " AND d.platform = ?"
        params.append(platform)
    
    query += " ORDER BY d.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_downloads(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """Get downloads for a specific user. Returns list of dicts."""
    limit = _clamp_int(int(limit), minimum=1, maximum=100)
    offset = _clamp_int(int(offset), minimum=0, maximum=10_000)
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM downloads
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_download_count(platform: Optional[str] = None) -> int:
    """Get total download count for pagination."""
    conn = get_connection()
    cur = conn.cursor()
    
    if platform:
        cur.execute("SELECT COUNT(*) FROM downloads WHERE platform = ?", (platform,))
    else:
        cur.execute("SELECT COUNT(*) FROM downloads")
    
    count = cur.fetchone()[0]
    conn.close()
    return count


# ============================================================================
# V2: User Posts Functions (Community Posts)
# ============================================================================

def create_user_post(user_id: int, content: str, media_urls: Optional[str] = None) -> Optional[int]:
    """Create a new user-submitted post. Returns post ID or None."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO user_posts (user_id, content, media_urls, created_at, is_approved, like_count)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 1, 0)
            """,
            (user_id, content.strip()[:2000], media_urls)  # Limit content to 2000 chars
        )
        conn.commit()
        post_id = cur.lastrowid
        conn.close()
        return post_id
    except Exception:
        conn.close()
        return None


def get_user_posts_by_user(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """Get posts created by a specific user. Returns list of dicts."""
    limit = _clamp_int(int(limit), minimum=1, maximum=100)
    offset = _clamp_int(int(offset), minimum=0, maximum=10_000)
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT up.*, u.nickname, u.email, u.avatar_url
        FROM user_posts up
        JOIN users u ON up.user_id = u.id
        WHERE up.user_id = ?
        ORDER BY up.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_community_posts(limit: int = 50, offset: int = 0) -> list:
    """Get all approved community posts. Returns list of dicts with user info."""
    limit = _clamp_int(int(limit), minimum=1, maximum=100)
    offset = _clamp_int(int(offset), minimum=0, maximum=10_000)
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT up.*, u.nickname, u.email, u.avatar_url
        FROM user_posts up
        JOIN users u ON up.user_id = u.id
        WHERE up.is_approved = 1
        ORDER BY up.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_community_post_count() -> int:
    """Get total count of approved community posts."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_posts WHERE is_approved = 1")
    count = cur.fetchone()[0]
    conn.close()
    return count


def delete_user_post(post_id: int, user_id: int) -> bool:
    """Delete a user's own post. Returns True if deleted."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM user_posts WHERE id = ? AND user_id = ?",
            (post_id, user_id)
        )
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted
    except Exception:
        conn.close()
        return False


def like_user_post(post_id: int) -> int:
    """Increment like count for a user post. Returns new count."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE user_posts SET like_count = like_count + 1 WHERE id = ?",
        (post_id,)
    )
    conn.commit()
    cur.execute("SELECT like_count FROM user_posts WHERE id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def unlike_user_post(post_id: int) -> int:
    """Decrement like count for a user post (floored at 0). Returns new count."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE user_posts SET like_count = CASE WHEN like_count > 0 THEN like_count - 1 ELSE 0 END WHERE id = ?",
        (post_id,)
    )
    conn.commit()
    cur.execute("SELECT like_count FROM user_posts WHERE id = ?", (post_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


# ============================================================================
# V2: User Profile Functions
# ============================================================================

def update_user_profile(user_id: int, nickname: Optional[str] = None, bio: Optional[str] = None, avatar_url: Optional[str] = None) -> bool:
    """Update user profile fields. Returns True if updated."""
    conn = get_connection()
    cur = conn.cursor()
    
    updates = []
    params = []
    
    if nickname is not None:
        updates.append("nickname = ?")
        params.append(nickname.strip()[:50] if nickname else None)
    
    if bio is not None:
        updates.append("bio = ?")
        params.append(bio.strip()[:500] if bio else None)  # Limit bio to 500 chars
    
    if avatar_url is not None:
        updates.append("avatar_url = ?")
        params.append(avatar_url.strip()[:500] if avatar_url else None)
    
    if not updates:
        conn.close()
        return False
    
    params.append(user_id)
    
    try:
        cur.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception:
        conn.close()
        return False


def get_user_stats(user_id: int) -> dict:
    """Get user statistics for profile page."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Count user's posts
    cur.execute("SELECT COUNT(*) FROM user_posts WHERE user_id = ?", (user_id,))
    post_count = cur.fetchone()[0]
    
    # Count user's downloads
    cur.execute("SELECT COUNT(*) FROM downloads WHERE user_id = ?", (user_id,))
    download_count = cur.fetchone()[0]
    
    # Get total likes received on user's posts
    cur.execute("SELECT COALESCE(SUM(like_count), 0) FROM user_posts WHERE user_id = ?", (user_id,))
    total_likes = cur.fetchone()[0]
    
    conn.close()
    
    return {
        "post_count": post_count,
        "download_count": download_count,
        "total_likes": total_likes,
    }
