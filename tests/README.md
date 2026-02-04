# ICENews Test Suite

This directory contains automated tests to verify the security, functionality, and stability of the ICENews application.

## Test Files

### `test_security.py`
Security and hardening tests covering:
- **SQL Injection Prevention**: Tests various SQL injection payloads in API parameters
- **XSS Prevention**: Verifies that user content is properly escaped in HTML output
- **Input Validation**: Tests handling of invalid, negative, and extreme values
- **API Response Structure**: Validates JSON response formats
- **Error Handling**: Tests 404s, method restrictions, and edge cases
- **Authorization**: Ensures sensitive data is not exposed in API responses

### `test_smoke.py`
Smoke tests for core functionality before deployment:
- **Homepage Rendering**: Verifies the homepage loads with valid Alpine.js initialization and JSON data
- **API Endpoints**: Tests `/api/posts`, `/api/accounts`, and pagination behavior
- **Likes Endpoints**: Tests the global like/unlike functionality
- **Health Check**: Verifies the `/health` endpoint for monitoring
- **Security Features**: Confirms XSS, SQL injection, and large-number defenses remain active
- **Database Integrity**: Verifies required tables exist

## Running Tests

### Run all tests:
```bash
./run_tests.sh
```

Or manually:
```bash
source venv/bin/activate
pytest tests/ -v
```

### Run specific test file:
```bash
pytest tests/test_smoke.py -v
pytest tests/test_security.py -v
```

### Run specific test class:
```bash
pytest tests/test_smoke.py::TestLikesEndpoints -v
```

### Run specific test:
```bash
pytest tests/test_smoke.py::TestLikesEndpoints::test_like_endpoint_increments_count -v
```

## Test Coverage

- **48 total tests** (as of last run)
- Security: 28 tests
- Smoke: 20 tests

## Pre-Deployment Checklist

Before deploying to production, ensure:
1. ✅ All tests pass (`./run_tests.sh`)
2. ✅ No new deprecation warnings introduced
3. ✅ Database schema matches expectations (test_smoke.py verifies this)
4. ✅ XSS and SQL injection defenses active
5. ✅ Like/unlike endpoints work correctly

## Adding New Tests

When adding new features:
1. Add security tests to `test_security.py` if the feature handles user input
2. Add smoke tests to `test_smoke.py` for core functionality verification
3. Update this README with test counts and coverage

## Test Dependencies

- `pytest>=7.0.0`
- `httpx>=0.25.0` (for TestClient)
- FastAPI's `TestClient`

All dependencies are in `requirements.txt`.
