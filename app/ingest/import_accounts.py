import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import json

ALLOWED_CATEGORIES = {"government", "independent", "unknown"}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def parse_boolish(value, default: bool = True) -> bool:
    """
    Parse common "boolean-ish" CSV values.

    Why:
    - Your `accounts.csv` uses `true/false`, but earlier code only accepted "1".
    - For a monitoring tool, it's safer to interpret intent rather than silently
      disabling everything.

    Accepts (case-insensitive): 1/0, true/false, yes/no, y/n, on/off.
    """
    if value is None:
        return default
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    # Tip: if you want *strict* CSV validation later, raise here instead.
    return default

def insert_post(conn: sqlite3.Connection, post: dict) -> bool:
    """
    Returns True if inserted, False if duplicate.
    Requires: platform, post_id, url, category, retrieved_at, raw_json.
    """
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO posts (
            id, platform, post_id, url, account_id,
            author_handle, author_display_name,
            category, text, created_at, retrieved_at,
            language, media_json, metrics_json,
            reply_to_post_id, quoted_post_id,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post["id"], post["platform"], post["post_id"], post["url"], post.get("account_id"),
        post.get("author_handle"), post.get("author_display_name"),
        post["category"], post.get("text"),
        post.get("created_at"), post.get("retrieved_at") or now_iso(),
        post.get("language"),
        json.dumps(post.get("media", []), ensure_ascii=False),
        json.dumps(post.get("metrics", {}), ensure_ascii=False),
        post.get("reply_to_post_id"), post.get("quoted_post_id"),
        json.dumps(post.get("raw_json", {}), ensure_ascii=False)
    ))
    return cur.rowcount == 1


def run(db_path="icenews_social.db", accounts_csv="app/data/accounts.csv"):
    db_path = Path(db_path)
    accounts_csv = Path(accounts_csv)

    if not accounts_csv.exists():
        raise FileNotFoundError(accounts_csv)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    created = 0
    updated = 0

    with accounts_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            platform = (row.get("platform") or "").strip().lower()
            handle = (row.get("handle") or "").strip().lstrip("@")
            display_name = (row.get("display_name") or "").strip()
            category = (row.get("category") or "unknown").strip().lower()
            role = (row.get("role") or "").strip()
            is_enabled = 1 if parse_boolish(row.get("is_enabled"), default=True) else 0
            verification_url = (row.get("verification_url") or "").strip()
            notes = (row.get("notes") or "").strip()

            if not platform or not handle:
                continue
            if category not in ALLOWED_CATEGORIES:
                category = "unknown"

            ts = now_iso()

            # Upsert by unique (platform, lower(handle))
            cur.execute("""
                SELECT account_id FROM accounts WHERE platform=? AND lower(handle)=lower(?)
            """, (platform, handle))
            existing = cur.fetchone()

            if existing:
                cur.execute("""
                    UPDATE accounts
                    SET display_name=?, category=?, role=?, is_enabled=?, verification_url=?, notes=?, updated_at=?
                    WHERE account_id=?
                """, (display_name, category, role, is_enabled, verification_url, notes, ts, existing[0]))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO accounts (platform, handle, display_name, category, role, is_enabled,
                                          verification_url, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (platform, handle, display_name, category, role, is_enabled,
                      verification_url, notes, ts, ts))
                created += 1

    conn.commit()
    conn.close()
    print(f"Accounts imported. created={created}, updated={updated}")

if __name__ == "__main__":
    run()
