# ICENews Testing & Quality Assurance

This document describes the testing strategy and verification procedures for ICENews.

## Test Suite Overview

### Automated Tests: 48 Total

All tests are located in the `/tests` directory and can be run with `./run_tests.sh`.

#### Security Tests (28 tests)
Located in `tests/test_security.py`:

- **SQL Injection Prevention** (12 tests)
  - Category parameter injection attempts
  - Account ID parameter injection attempts
  - Integer overflow attempts
  - All payloads are safely handled without crashes

- **XSS Prevention** (2 tests)
  - Homepage renders correctly
  - Initial JSON payload has `<` and `>` escaped

- **Input Validation** (5 tests)
  - Invalid limit values rejected
  - Negative values handled correctly
  - Large numbers capped (soft cap)
  - Reasonable defaults applied

- **API Response Structure** (3 tests)
  - `/api/posts` returns valid structure
  - `/api/accounts` returns valid structure
  - Individual post objects have required fields

- **Error Handling** (4 tests)
  - 404 for nonexistent routes
  - 405 for method not allowed
  - Empty and whitespace filters handled

- **Authorization Basics** (2 tests)
  - No sensitive data (raw_json) in API
  - No credentials exposed in accounts API

#### Smoke Tests (20 tests)
Located in `tests/test_smoke.py`:

- **Homepage Rendering** (4 tests)
  - Homepage returns 200
  - Alpine.js app is initialized
  - Initial posts JSON is valid
  - Initial posts JSON is XSS-safe

- **API Endpoints** (4 tests)
  - `/api/posts` returns valid JSON
  - Posts include `like_count` field
  - `/api/accounts` returns list
  - Pagination caps work (soft cap at 100)

- **Likes Endpoints** (5 tests)
  - 404 for non-existent posts (like)
  - 404 for non-existent posts (unlike)
  - Like endpoint increments count
  - Unlike endpoint decrements count
  - Unlike floors at zero (never negative)

- **Health Check** (1 test)
  - `/health` endpoint returns 200 or 503

- **Security Features** (3 tests)
  - XSS prevention still active
  - Large number defense still active
  - SQL injection defense still active

- **Database Integrity** (3 tests)
  - `post_likes` table exists
  - `posts` table exists
  - `accounts` table exists

## Running Tests

### Quick Test (before deployment)
```bash
./run_tests.sh
```

### Manual Test Run
```bash
source venv/bin/activate
pytest tests/ -v
```

### Test Specific Areas
```bash
# Security only
pytest tests/test_security.py -v

# Smoke tests only
pytest tests/test_smoke.py -v

# Just likes functionality
pytest tests/test_smoke.py::TestLikesEndpoints -v
```

## Manual Testing Guide

In addition to automated tests, perform these manual checks:

### 1. Homepage & Feed
- [ ] Open `http://localhost:8000/` - posts load immediately
- [ ] Refresh button updates the feed
- [ ] Filter by category works (Government, Independent)
- [ ] Stats cards show correct counts

### 2. Like Functionality
- [ ] Click Like on a post - button turns rose/pink
- [ ] Like count increments and displays as a number
- [ ] Click again to unlike - count decrements
- [ ] Open in multiple tabs - like count syncs across tabs
- [ ] Stop server, try to like - shows error toast and reverts

### 3. Share Functionality
- [ ] Click Share - copies link (desktop) or opens native share (mobile)
- [ ] Toast notification appears confirming copy

### 4. Post Actions
- [ ] Click anywhere on post card - opens tweet in new tab
- [ ] "View on X" link works

### 5. Debug Mode
- [ ] Open `http://localhost:8000/?debug=1`
- [ ] Open browser console - see detailed logs
- [ ] All actions log correctly

### 6. API Endpoints
```bash
# Get posts
curl http://localhost:8000/api/posts | jq

# Get accounts
curl http://localhost:8000/api/accounts | jq

# Like a post (replace POST_ID)
curl -X POST http://localhost:8000/api/posts/POST_ID/like | jq

# Unlike a post
curl -X POST http://localhost:8000/api/posts/POST_ID/unlike | jq

# Health check
curl http://localhost:8000/health | jq
```

## Pre-Deployment Checklist

Before deploying to production:

- [ ] All 48 automated tests pass (`./run_tests.sh`)
- [ ] Manual testing checklist completed
- [ ] No console errors in browser
- [ ] Database has `post_likes` table
- [ ] Health check endpoint returns 200
- [ ] XSS escaping verified (view page source, check initial-posts JSON)
- [ ] Large number soft caps working (try `?limit=999999`)
- [ ] Like counts persist across server restarts
- [ ] Umami analytics configured (or disabled)

## Security Verification

### XSS Prevention
The `_posts_to_json()` function in `app/main.py` escapes `<` and `>` characters:
```python
return json.dumps(posts).replace("<", "\\u003c").replace(">", "\\u003e")
```

Verified by tests:
- `test_security.py::TestXSSPrevention::test_posts_json_escaping`
- `test_smoke.py::TestHomepageRendering::test_initial_posts_xss_safe`

### SQL Injection Prevention
All database queries use parameterized queries (SQLite placeholders):
```python
cur.execute("SELECT * FROM posts WHERE category = ?", (category,))
```

Verified by 12 SQL injection tests in `test_security.py`.

### Large Number Defense
Soft caps applied at both API and database layers:
- API: `limit = min(limit, 100)`
- DB: `_clamp_int(limit, minimum=1, maximum=100)`

Verified by input validation tests.

## Test Maintenance

### When to Update Tests

1. **New Feature Added**: Add smoke test for core functionality
2. **New API Endpoint**: Add security + smoke tests
3. **User Input Added**: Add SQL injection + XSS tests
4. **Bug Fixed**: Add regression test

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<what>_<expected_behavior>`

Example: `test_like_endpoint_increments_count`

## Known Deprecation Warnings

The following warnings appear but don't affect functionality:

1. **Pydantic ConfigDict**: `app/models.py` uses class-based config (Pydantic v2 deprecation)
2. **FastAPI on_event**: `app/main.py` uses `@app.on_event("startup")` (should migrate to lifespan)
3. **Starlette TemplateResponse**: Parameter order changed in newer version

These can be fixed in a future refactor but don't impact security or functionality.

## Next Steps

After testing is complete:
1. Deploy to staging environment
2. Run tests against staging
3. Perform load testing (optional)
4. Deploy to production behind HTTPS + password gate
5. Set up external health check monitoring
