# Unit Test Explanation for ingest_x_scrapfly.py

## Overview

This document explains the unit tests created for `ingest_x_scrapfly.py`, including what is being tested and why, covering both success and failure paths.

## Test File

**Location:** `app/ingest/test_ingest_x_scrapfly.py`

**Framework:** pytest

## Functions Tested

### 1. `now_iso()` - Timestamp Generation

**Why test:** This function generates timestamps for the `retrieved_at` field. It's critical that it produces valid, parseable ISO format strings with timezone information for database storage and consistency.

**Good paths tested:**
- ✅ Returns valid ISO format string
- ✅ Contains timezone information (Z or offset)
- ✅ Uses UTC timezone
- ✅ Is parseable as datetime object

**Bad paths tested:**
- None (pure function with no inputs, always succeeds)

**Test rationale:** Ensures consistent timestamp format across the application and compatibility with database datetime fields.

---

### 2. `get_enabled_accounts(conn)` - Database Query

**Why test:** This function is critical for the ingestion pipeline - it determines which accounts to process. Incorrect filtering could lead to processing wrong accounts or skipping enabled ones.

**Good paths tested:**
- ✅ Returns only enabled accounts (`is_enabled = 1`)
- ✅ Returns only X platform accounts (`platform = 'x'`)
- ✅ Returns correct tuple structure: (account_id, platform, handle, display_name, category)
- ✅ Returns empty list when no matches exist

**Bad paths tested:**
- ✅ Raises error on invalid connection object

**Test rationale:** Validates SQL query correctness, filtering logic, and error handling. Ensures the ingestion process only processes the intended accounts.

---

### 3. `insert_post(conn, post: dict)` - Database Insert

**Why test:** This is the core data persistence function. It must correctly insert posts, handle duplicates (INSERT OR IGNORE), and serialize JSON fields properly. Any bugs here could lead to data loss or corruption.

**Good paths tested:**
- ✅ Successfully inserts new post, returns `True`
- ✅ Handles duplicate posts correctly (returns `False`, doesn't insert duplicate)
- ✅ Correctly serializes JSON fields (media_json, metrics_json, raw_json)
- ✅ Handles optional fields using `.get()` with defaults

**Bad paths tested:**
- ✅ Raises `KeyError` on missing required fields (`platform`, `post_id`, `url`, `category`)
- ✅ Raises error on invalid connection object

**Known Issues Exposed:**
- ⚠️ **BUG DETECTED:** The SQL INSERT statement has a column/value mismatch:
  - Columns list includes: `tagged_account_handle`, `tagged_hashtags`, `reply_to_post_id`, `quoted_post_id`
  - VALUES tuple has: `account_id` in wrong position, missing some columns, wrong order
  - This bug will cause database errors when inserting posts

**Test rationale:** Ensures data integrity, duplicate prevention, and proper error handling. Tests expose the column/value mismatch bug that needs to be fixed.

---

### 4. `normalize_scraper_item(item: dict, account_row: dict)` - Data Transformation

**Why test:** This function maps scraper output (which may vary in format) to the database schema. It handles multiple field name variations and must validate required fields. Bugs here could cause data loss or incorrect data storage.

**Good paths tested:**
- ✅ Normalizes item with all fields present
- ✅ Handles alternative field names:
  - ID fields: `id`, `tweet_id`, `rest_id`
  - URL fields: `url`, `permalink`
  - Text fields: `text`, `full_text`
  - Date fields: `created_at`, `date`
  - Metrics fields: `metrics`, `public_metrics`
  - Language fields: `lang`, `language`
  - Reply fields: `in_reply_to_status_id`, `reply_to_id`
  - Quote fields: `quoted_status_id`, `quote_id`
- ✅ Sets platform to "x"
- ✅ Validates category against `ALLOWED_CATEGORIES`, defaults to "unknown" if invalid
- ✅ Includes `retrieved_at` timestamp
- ✅ Preserves raw JSON in `raw_json` field
- ✅ Maps account information correctly

**Bad paths tested:**
- ✅ Returns `None` when `post_id` is missing or empty
- ✅ Returns `None` when `url` is missing or empty
- ✅ Handles invalid category (defaults to "unknown")

**Test rationale:** Ensures robust handling of varying scraper output formats, proper validation of required fields, and correct data mapping. This function is critical for data quality.

---

### 5. `run()` - Main Orchestration Function

**Why test:** This is the main entry point that coordinates all components. It handles subprocess execution, JSON parsing (multiple formats), error handling, and database transactions. This is the most complex function and most likely to have integration issues.

**Good paths tested:**
- ✅ Processes single account with valid JSON array output
- ✅ Processes multiple accounts sequentially
- ✅ Handles JSON array format: `[{...}, {...}]`
- ✅ Handles JSON object with "items" key: `{"items": [{...}]}`
- ✅ Handles single JSON object (wraps in list): `{...}`
- ✅ Handles JSONL format (newline-delimited JSON)
- ✅ Skips invalid JSON lines in JSONL (continues processing)
- ✅ Commits transactions after each account
- ✅ Handles empty scraper output (skips account gracefully)

**Bad paths tested:**
- ✅ Raises `FileNotFoundError` when database file doesn't exist
- ✅ Handles subprocess failures (`CalledProcessError`) gracefully - skips account, continues processing
- ✅ Skips items that normalize to `None` (missing required fields)
- ✅ Handles empty output from scraper

**Test rationale:** Ensures the entire ingestion pipeline works correctly, handles various output formats from scrapers, recovers from errors gracefully, and maintains data consistency through proper transaction handling.

---

## Test Implementation Details

### Mocking Strategy

1. **Database:** Uses `sqlite3.connect(':memory:')` for isolated, fast in-memory test databases
2. **Subprocess:** Mocks `subprocess.run()` to avoid actual scraper execution (faster, more reliable)
3. **File System:** Mocks `Path.exists()` for `DB_PATH` checks
4. **Time:** Can mock `datetime.now()` for deterministic timestamps (used in some tests)

### Test Fixtures

- `test_db`: Creates in-memory SQLite database with schema
- `sample_accounts`: Pre-populated test database with sample accounts
- `sample_account_row`: Sample account dictionary
- `sample_scraper_item`: Sample scraper output based on real tweet.json
- `sample_post_dict`: Sample normalized post dictionary

### Test Isolation

Each test is isolated:
- Uses fresh database fixtures
- Mocks external dependencies (subprocess, file system)
- No shared state between tests

---

## Running the Tests

```bash
# Run all tests
pytest app/ingest/test_ingest_x_scrapfly.py -v

# Run specific test function
pytest app/ingest/test_ingest_x_scrapfly.py::test_normalize_scraper_item_with_all_fields -v

# Run with coverage
pytest app/ingest/test_ingest_x_scrapfly.py --cov=ingest_x_scrapfly --cov-report=html
```

---

## Bugs Exposed by Tests

1. **`insert_post()` function:** SQL column list doesn't match VALUES tuple order/values
   - Columns reference `tagged_account_handle`, `tagged_hashtags`, `reply_to_post_id`, `quoted_post_id`
   - VALUES tuple has `account_id` in wrong position and mismatched order
   - This will cause database errors when inserting posts

---

## Test Coverage Summary

- **Total test functions:** ~35+
- **Functions covered:** 5/5 (100%)
- **Good paths:** Comprehensive coverage
- **Bad paths:** Error conditions and edge cases covered
- **Integration:** Full pipeline tested with mocking

---

## Notes

- Tests use realistic data based on actual scraper output (`scrapfly-scrapers/twitter-scraper/results/tweet.json`)
- Database schema in tests matches the actual schema from `db` file (with additions for columns referenced in code)
- Tests are designed to expose bugs while validating correct behavior
- All tests should pass once the `insert_post()` bug is fixed
