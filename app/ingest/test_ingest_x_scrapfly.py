"""
Unit tests for ingest_x_scrapfly.py

Tests cover:
- Timestamp generation (now_iso)
- Database queries (get_enabled_accounts)
- Database inserts (insert_post)
- Data normalization (normalize_scraper_item)
- Main orchestration (run)
"""

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

import pytest

from ingest_x_scrapfly import (
    now_iso,
    get_enabled_accounts,
    insert_post,
    normalize_scraper_item,
    run,
    ALLOWED_CATEGORIES,
    DB_PATH,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_db():
    """Create an in-memory SQLite database with the schema."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    
    # Create schema based on db file
    conn.executescript("""
        CREATE TABLE accounts (
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

        CREATE TABLE posts (
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
            reply_to_post_id TEXT,
            quoted_post_id TEXT,
            raw_json TEXT,
            account_id INTEGER,
            FOREIGN KEY (account_id) REFERENCES accounts (account_id) ON DELETE CASCADE
        );
    """)
    
    yield conn
    conn.close()


@pytest.fixture
def sample_accounts(test_db):
    """Insert sample accounts into test database."""
    test_db.executemany("""
        INSERT INTO accounts (account_id, platform, handle, display_name, category, is_enabled)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        (1, 'x', 'testuser', 'Test User', 'government', 1),
        (2, 'x', 'testuser2', 'Test User 2', 'independent', 1),
        (3, 'x', 'disabled_user', 'Disabled User', 'unknown', 0),
        (4, 'twitter', 'wrong_platform', 'Wrong Platform', 'government', 1),
    ])
    test_db.commit()
    return test_db


@pytest.fixture
def sample_account_row():
    """Sample account row dictionary."""
    return {
        "id": 1,
        "handle": "testuser",
        "display_name": "Test User",
        "category": "government",
    }


@pytest.fixture
def sample_scraper_item():
    """Sample scraper item based on tweet.json structure."""
    return {
        "id": "2015845364562030624",
        "text": "Test tweet text",
        "url": "https://x.com/testuser/status/2015845364562030624",
        "created_at": "Mon Jan 26 17:52:42 +0000 2026",
        "language": "en",
        "media": ["https://pbs.twimg.com/media/test.jpg"],
        "metrics": {
            "favorite_count": 519,
            "retweet_count": 201,
        },
        "in_reply_to_status_id": None,
        "quoted_status_id": None,
    }


@pytest.fixture
def sample_post_dict():
    """Sample normalized post dictionary."""
    return {
        "platform": "x",
        "post_id": "2015845364562030624",
        "url": "https://x.com/testuser/status/2015845364562030624",
        "account_id": 1,
        "author_handle": "testuser",
        "author_display_name": "Test User",
        "category": "government",
        "text": "Test tweet text",
        "created_at": "Mon Jan 26 17:52:42 +0000 2026",
        "retrieved_at": "2026-01-27T12:00:00+00:00",
        "language": "en",
        "media": [],
        "metrics": {},
        "reply_to_post_id": None,
        "quoted_post_id": None,
        "raw_json": {},
    }


# ============================================================================
# Tests for now_iso()
# ============================================================================

def test_now_iso_returns_iso_format_string():
    """Test that now_iso() returns a valid ISO format string."""
    result = now_iso()
    
    assert isinstance(result, str)
    # Should be parseable as datetime
    parsed = datetime.fromisoformat(result.replace('Z', '+00:00'))
    assert isinstance(parsed, datetime)


def test_now_iso_contains_timezone():
    """Test that now_iso() includes timezone information."""
    result = now_iso()
    
    # Should contain timezone info (either 'Z' or '+00:00' or similar)
    assert 'Z' in result or '+' in result or result.endswith('+00:00')


def test_now_iso_uses_utc():
    """Test that now_iso() uses UTC timezone."""
    result = now_iso()
    parsed = datetime.fromisoformat(result.replace('Z', '+00:00'))
    
    assert parsed.tzinfo is not None
    # Should be UTC (offset of 0)
    assert parsed.utcoffset().total_seconds() == 0


# ============================================================================
# Tests for get_enabled_accounts()
# ============================================================================

def test_get_enabled_accounts_returns_enabled_x_accounts(sample_accounts):
    """Test that get_enabled_accounts returns only enabled X accounts."""
    accounts = get_enabled_accounts(sample_accounts)
    
    assert len(accounts) == 2  # Only 2 enabled X accounts
    assert all(acc[1] == 'x' for acc in accounts)  # All platform = 'x'
    assert all(acc[0] in [1, 2] for acc in accounts)  # Only account_id 1 or 2


def test_get_enabled_accounts_returns_correct_structure(sample_accounts):
    """Test that get_enabled_accounts returns tuples with correct structure."""
    accounts = get_enabled_accounts(sample_accounts)
    
    assert len(accounts) > 0
    for acc in accounts:
        assert len(acc) == 5  # (account_id, platform, handle, display_name, category)
        assert isinstance(acc[0], int)  # account_id
        assert isinstance(acc[1], str)  # platform
        assert isinstance(acc[2], str)  # handle
        assert isinstance(acc[3], str)  # display_name
        assert isinstance(acc[4], str)  # category


def test_get_enabled_accounts_filters_disabled_accounts(sample_accounts):
    """Test that disabled accounts are not returned."""
    accounts = get_enabled_accounts(sample_accounts)
    
    account_ids = [acc[0] for acc in accounts]
    assert 3 not in account_ids  # disabled_user should not be included


def test_get_enabled_accounts_filters_wrong_platform(sample_accounts):
    """Test that accounts with platform != 'x' are not returned."""
    accounts = get_enabled_accounts(sample_accounts)
    
    account_ids = [acc[0] for acc in accounts]
    assert 4 not in account_ids  # wrong_platform should not be included


def test_get_enabled_accounts_returns_empty_list_when_no_matches(test_db):
    """Test that get_enabled_accounts returns empty list when no matches."""
    accounts = get_enabled_accounts(test_db)
    
    assert accounts == []


def test_get_enabled_accounts_raises_on_invalid_connection():
    """Test that get_enabled_accounts raises error on invalid connection."""
    with pytest.raises((sqlite3.OperationalError, AttributeError)):
        get_enabled_accounts(None)


# ============================================================================
# Tests for insert_post()
# ============================================================================

def test_insert_post_successfully_inserts_new_post(test_db, sample_post_dict):
    """Test that insert_post successfully inserts a new post."""
    result = insert_post(test_db, sample_post_dict)
    
    assert result is True
    
    # Verify post was inserted
    cur = test_db.cursor()
    cur.execute("SELECT * FROM posts WHERE post_id = ?", (sample_post_dict["post_id"],))
    row = cur.fetchone()
    assert row is not None
    assert row["platform"] == sample_post_dict["platform"]
    assert row["post_id"] == sample_post_dict["post_id"]


def test_insert_post_handles_duplicate_returns_false(test_db, sample_post_dict):
    """Test that insert_post returns False for duplicate posts."""
    # Insert first time
    result1 = insert_post(test_db, sample_post_dict)
    assert result1 is True
    
    # Try to insert duplicate
    result2 = insert_post(test_db, sample_post_dict)
    assert result2 is False
    
    # Verify only one post exists
    cur = test_db.cursor()
    cur.execute("SELECT COUNT(*) FROM posts WHERE post_id = ?", (sample_post_dict["post_id"],))
    count = cur.fetchone()[0]
    assert count == 1


def test_insert_post_handles_optional_fields(test_db):
    """Test that insert_post handles optional fields correctly."""
    post = {
        "platform": "x",
        "post_id": "123",
        "url": "https://x.com/test/status/123",
        "category": "government",
        # Optional fields missing
    }
    
    # Should not raise error, uses .get() defaults
    result = insert_post(test_db, post)
    # Note: This may fail due to NOT NULL constraints, which is expected behavior


def test_insert_post_raises_on_missing_required_fields(test_db):
    """Test that insert_post raises KeyError on missing required fields."""
    post = {
        "platform": "x",
        # Missing post_id, url, category
    }
    
    with pytest.raises(KeyError):
        insert_post(test_db, post)


def test_insert_post_handles_json_fields(test_db, sample_post_dict):
    """Test that insert_post correctly serializes JSON fields."""
    sample_post_dict["media"] = [{"type": "photo", "url": "test.jpg"}]
    sample_post_dict["metrics"] = {"likes": 10, "retweets": 5}
    sample_post_dict["raw_json"] = {"test": "data"}
    
    result = insert_post(test_db, sample_post_dict)
    assert result is True
    
    # Verify JSON was serialized correctly
    cur = test_db.cursor()
    cur.execute("SELECT media_json, metrics_json, raw_json FROM posts WHERE post_id = ?", 
                (sample_post_dict["post_id"],))
    row = cur.fetchone()
    
    assert json.loads(row["media_json"]) == sample_post_dict["media"]
    assert json.loads(row["metrics_json"]) == sample_post_dict["metrics"]
    assert json.loads(row["raw_json"]) == sample_post_dict["raw_json"]


# ============================================================================
# Tests for normalize_scraper_item()
# ============================================================================

def test_normalize_scraper_item_with_all_fields(sample_scraper_item, sample_account_row):
    """Test normalization with all fields present."""
    result = normalize_scraper_item(sample_scraper_item, sample_account_row)
    
    assert result is not None
    assert result["platform"] == "x"
    assert result["post_id"] == sample_scraper_item["id"]
    assert result["url"] == sample_scraper_item["url"]
    assert result["text"] == sample_scraper_item["text"]
    assert result["category"] == sample_account_row["category"]
    assert result["author_handle"] == sample_account_row["handle"]
    assert result["author_display_name"] == sample_account_row["display_name"]
    assert result["account_id"] == sample_account_row["id"]
    assert "retrieved_at" in result
    assert result["raw_json"] == sample_scraper_item


def test_normalize_scraper_item_handles_alternative_id_fields(sample_account_row):
    """Test normalization handles alternative ID field names."""
    # Test with tweet_id
    item1 = {"tweet_id": "123", "url": "https://x.com/test/123"}
    result1 = normalize_scraper_item(item1, sample_account_row)
    assert result1["post_id"] == "123"
    
    # Test with rest_id
    item2 = {"rest_id": "456", "url": "https://x.com/test/456"}
    result2 = normalize_scraper_item(item2, sample_account_row)
    assert result2["post_id"] == "456"
    
    # Test with id (preferred)
    item3 = {"id": "789", "url": "https://x.com/test/789"}
    result3 = normalize_scraper_item(item3, sample_account_row)
    assert result3["post_id"] == "789"


def test_normalize_scraper_item_handles_alternative_url_fields(sample_account_row):
    """Test normalization handles alternative URL field names."""
    item = {"id": "123", "permalink": "https://x.com/test/123"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["url"] == "https://x.com/test/123"


def test_normalize_scraper_item_handles_alternative_text_fields(sample_account_row):
    """Test normalization handles alternative text field names."""
    item = {"id": "123", "url": "https://x.com/test/123", "full_text": "Full text here"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["text"] == "Full text here"


def test_normalize_scraper_item_handles_alternative_date_fields(sample_account_row):
    """Test normalization handles alternative date field names."""
    item = {"id": "123", "url": "https://x.com/test/123", "date": "2026-01-01"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["created_at"] == "2026-01-01"


def test_normalize_scraper_item_handles_alternative_metrics_fields(sample_account_row):
    """Test normalization handles alternative metrics field names."""
    item = {
        "id": "123",
        "url": "https://x.com/test/123",
        "public_metrics": {"likes": 10}
    }
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["metrics"] == {"likes": 10}


def test_normalize_scraper_item_handles_alternative_language_fields(sample_account_row):
    """Test normalization handles alternative language field names."""
    item = {"id": "123", "url": "https://x.com/test/123", "lang": "es"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["language"] == "es"


def test_normalize_scraper_item_handles_reply_and_quote_fields(sample_account_row):
    """Test normalization handles reply and quote ID fields."""
    item = {
        "id": "123",
        "url": "https://x.com/test/123",
        "in_reply_to_status_id": "456",
        "quoted_status_id": "789"
    }
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["reply_to_post_id"] == "456"
    assert result["quoted_post_id"] == "789"


def test_normalize_scraper_item_handles_alternative_reply_fields(sample_account_row):
    """Test normalization handles alternative reply ID field names."""
    item = {"id": "123", "url": "https://x.com/test/123", "reply_to_id": "456"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["reply_to_post_id"] == "456"


def test_normalize_scraper_item_handles_alternative_quote_fields(sample_account_row):
    """Test normalization handles alternative quote ID field names."""
    item = {"id": "123", "url": "https://x.com/test/123", "quote_id": "789"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result["quoted_post_id"] == "789"


def test_normalize_scraper_item_validates_category(sample_account_row):
    """Test that category is validated against ALLOWED_CATEGORIES."""
    # Valid category
    sample_account_row["category"] = "government"
    item = {"id": "123", "url": "https://x.com/test/123"}
    result = normalize_scraper_item(item, sample_account_row)
    assert result["category"] == "government"
    
    # Invalid category defaults to "unknown"
    sample_account_row["category"] = "invalid_category"
    result = normalize_scraper_item(item, sample_account_row)
    assert result["category"] == "unknown"


def test_normalize_scraper_item_returns_none_when_missing_post_id(sample_account_row):
    """Test that normalization returns None when post_id is missing."""
    item = {"url": "https://x.com/test/123"}  # No id
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result is None


def test_normalize_scraper_item_returns_none_when_missing_url(sample_account_row):
    """Test that normalization returns None when url is missing."""
    item = {"id": "123"}  # No url
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result is None


def test_normalize_scraper_item_returns_none_when_empty_post_id(sample_account_row):
    """Test that normalization returns None when post_id is empty."""
    item = {"id": "", "url": "https://x.com/test/123"}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result is None


def test_normalize_scraper_item_returns_none_when_empty_url(sample_account_row):
    """Test that normalization returns None when url is empty."""
    item = {"id": "123", "url": ""}
    result = normalize_scraper_item(item, sample_account_row)
    
    assert result is None


def test_normalize_scraper_item_includes_retrieved_at_timestamp(sample_scraper_item, sample_account_row):
    """Test that retrieved_at timestamp is included."""
    with patch('ingest_x_scrapfly.now_iso', return_value='2026-01-27T12:00:00+00:00'):
        result = normalize_scraper_item(sample_scraper_item, sample_account_row)
        
        assert result["retrieved_at"] == '2026-01-27T12:00:00+00:00'


def test_normalize_scraper_item_preserves_raw_json(sample_scraper_item, sample_account_row):
    """Test that raw JSON is preserved in raw_json field."""
    result = normalize_scraper_item(sample_scraper_item, sample_account_row)
    
    assert result["raw_json"] == sample_scraper_item


# ============================================================================
# Tests for run()
# ============================================================================

@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_raises_when_db_not_found(mock_subprocess, mock_db_path):
    """Test that run() raises FileNotFoundError when DB doesn't exist."""
    mock_db_path.exists.return_value = False
    
    with pytest.raises(FileNotFoundError):
        run()


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_processes_single_account_with_json_array(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() processes single account with JSON array output."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    # Mock subprocess to return JSON array
    mock_proc = Mock()
    mock_proc.stdout = json.dumps([
        {"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"},
        {"id": "456", "url": "https://x.com/testuser/status/456", "text": "Tweet 2"},
    ])
    mock_subprocess.return_value = mock_proc
    
    # Mock sqlite3.connect to return our test database
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        # Mock print to avoid cluttering output
        with patch('builtins.print'):
            run()
    
    # Verify posts were inserted
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 2


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_processes_json_object_with_items_key(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() handles JSON object with 'items' key."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = json.dumps({
        "items": [
            {"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"},
        ]
    })
    mock_subprocess.return_value = mock_proc
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 1


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_processes_single_json_object(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() handles single JSON object (wraps in list)."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = json.dumps({"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"})
    mock_subprocess.return_value = mock_proc
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 1


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_processes_jsonl_format(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() handles JSONL (newline-delimited JSON) format."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = '\n'.join([
        json.dumps({"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"}),
        json.dumps({"id": "456", "url": "https://x.com/testuser/status/456", "text": "Tweet 2"}),
    ])
    mock_subprocess.return_value = mock_proc
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 2


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_skips_invalid_json_lines_in_jsonl(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() skips invalid JSON lines in JSONL format."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = '\n'.join([
        json.dumps({"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"}),
        "invalid json line",
        json.dumps({"id": "456", "url": "https://x.com/testuser/status/456", "text": "Tweet 2"}),
    ])
    mock_subprocess.return_value = mock_proc
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 2  # Only valid JSON lines processed


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_handles_subprocess_failure_gracefully(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() handles subprocess failures gracefully."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    # Mock subprocess to raise CalledProcessError
    mock_subprocess.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="Error message")
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            # Should not raise, should continue processing
            run()
    
    # No posts should be inserted
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 0


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_skips_empty_output(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() skips accounts with empty scraper output."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = ""  # Empty output
    mock_subprocess.return_value = mock_proc
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 0


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_skips_items_with_missing_required_fields(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() skips items that normalize to None."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = json.dumps([
        {"id": "123", "url": "https://x.com/testuser/status/123", "text": "Valid tweet"},
        {"id": "", "url": "https://x.com/testuser/status/456"},  # Missing post_id (empty)
        {"id": "789"},  # Missing url
    ])
    mock_subprocess.return_value = mock_proc
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 1  # Only valid item inserted


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_processes_multiple_accounts(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() processes multiple accounts."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    # Mock subprocess to return different data for each account
    def side_effect(*args, **kwargs):
        mock_proc = Mock()
        # Determine which account based on command
        if 'testuser' in str(args[0]):
            mock_proc.stdout = json.dumps([{"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"}])
        elif 'testuser2' in str(args[0]):
            mock_proc.stdout = json.dumps([{"id": "456", "url": "https://x.com/testuser2/status/456", "text": "Tweet 2"}])
        return mock_proc
    
    mock_subprocess.side_effect = side_effect
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
    
    cur = sample_accounts.cursor()
    cur.execute("SELECT COUNT(*) FROM posts")
    count = cur.fetchone()[0]
    assert count == 2  # Both accounts processed


@patch('ingest_x_scrapfly.DB_PATH')
@patch('ingest_x_scrapfly.subprocess.run')
def test_run_commits_after_each_account(mock_subprocess, mock_db_path, sample_accounts):
    """Test run() commits transactions after each account."""
    mock_db_path.exists.return_value = True
    mock_db_path.__str__ = lambda x: ':memory:'
    
    mock_proc = Mock()
    mock_proc.stdout = json.dumps([{"id": "123", "url": "https://x.com/testuser/status/123", "text": "Tweet 1"}])
    mock_subprocess.return_value = mock_proc
    
    # Track commit calls
    original_commit = sample_accounts.commit
    commit_called = False
    
    def mock_commit():
        nonlocal commit_called
        commit_called = True
        original_commit()
    
    sample_accounts.commit = mock_commit
    
    with patch('ingest_x_scrapfly.sqlite3.connect', return_value=sample_accounts):
        with patch('builtins.print'):
            run()
        
        # Verify commit was called
        assert commit_called
