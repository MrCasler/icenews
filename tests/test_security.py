"""
Security tests for ICENews web application.

Tests cover:
- SQL injection prevention
- XSS prevention
- Input validation
- API parameter validation

Run with: pytest tests/test_security.py -v
"""
import json
import pytest
from fastapi.testclient import TestClient

# Import the app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

client = TestClient(app)


class TestSQLInjection:
    """Test SQL injection prevention in API endpoints."""

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE posts; --",
        "1 OR 1=1",
        "1'; DELETE FROM accounts; --",
        "1 UNION SELECT * FROM accounts --",
        "'; INSERT INTO accounts VALUES (999, 'hacked'); --",
        "1; UPDATE accounts SET is_enabled=1 WHERE 1=1; --",
    ])
    def test_api_posts_category_sqli(self, payload):
        """Test that SQL injection payloads in category param are handled safely."""
        response = client.get(f"/api/posts?category={payload}")
        # Should return 200 with empty or filtered results, not crash
        assert response.status_code == 200
        data = response.json()
        # Should not return all posts (which would indicate injection worked)
        assert "posts" in data

    @pytest.mark.parametrize("payload", [
        "-1 OR 1=1",
        "1; DROP TABLE posts",
        "NULL",
        "1 UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16 FROM accounts",
    ])
    def test_api_posts_account_id_sqli(self, payload):
        """Test that SQL injection in account_id is prevented."""
        response = client.get(f"/api/posts?account_id={payload}")
        # Should return 422 (validation error) for non-integer input
        # or 200 with empty results
        assert response.status_code in [200, 422]

    @pytest.mark.parametrize("payload", [
        "99999999999999999999",  # Integer overflow attempt
        "-99999999999999999999",
    ])
    def test_api_posts_large_integers(self, payload):
        """Test handling of extremely large integer values."""
        response = client.get(f"/api/posts?limit={payload}")
        # Should handle gracefully
        assert response.status_code in [200, 422]


class TestXSSPrevention:
    """Test XSS prevention in rendered pages."""

    def test_homepage_renders(self):
        """Test that homepage renders without errors."""
        response = client.get("/")
        assert response.status_code == 200
        assert "ICENews" in response.text

    def test_posts_json_escaping(self):
        """
        Test that the initial JSON payload is safe to embed in HTML.

        Professor-note: pages legitimately contain <script> tags (Tailwind/Alpine),
        so we focus specifically on the JSON payload carrier.
        """
        response = client.get("/")
        assert response.status_code == 200
        html = response.text

        # Extract the JSON payload from the script tag.
        marker = 'id="initial-posts"'
        assert marker in html
        start = html.index(marker)
        start = html.index(">", start) + 1
        end = html.index("</script>", start)
        payload = html[start:end]

        # The payload should not contain literal "<" characters. If the data ever
        # includes "<script>", it must be encoded as "\\u003cscript>" by the server.
        assert "<" not in payload


class TestInputValidation:
    """Test input validation on API endpoints."""

    def test_api_posts_invalid_limit(self):
        """Test that invalid limit values are handled."""
        response = client.get("/api/posts?limit=abc")
        assert response.status_code == 422  # Validation error

    def test_api_posts_negative_limit(self):
        """Test handling of negative limit."""
        response = client.get("/api/posts?limit=-1")
        # Should either reject or treat as 0/default
        assert response.status_code in [200, 422]

    def test_api_posts_negative_offset(self):
        """Test handling of negative offset."""
        response = client.get("/api/posts?offset=-1")
        assert response.status_code in [200, 422]

    def test_api_posts_reasonable_defaults(self):
        """Test that default pagination is reasonable."""
        response = client.get("/api/posts")
        assert response.status_code == 200
        data = response.json()
        assert "posts" in data
        assert "total" in data
        # Should not return unlimited results
        assert len(data["posts"]) <= 100

    def test_api_posts_limit_capped(self):
        """Test that extremely high limits don't cause issues."""
        response = client.get("/api/posts?limit=1000000")
        assert response.status_code == 200
        data = response.json()
        assert "posts" in data
        # Soft cap: should never return an unbounded result set.
        assert len(data["posts"]) <= 100


class TestAPIResponses:
    """Test API response structure and types."""

    def test_api_posts_response_structure(self):
        """Test that /api/posts returns expected structure."""
        response = client.get("/api/posts")
        assert response.status_code == 200
        data = response.json()
        
        assert "posts" in data
        assert "total" in data
        assert isinstance(data["posts"], list)
        assert isinstance(data["total"], int)
        assert data["total"] >= 0

    def test_api_accounts_response_structure(self):
        """Test that /api/accounts returns expected structure."""
        response = client.get("/api/accounts")
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            account = data[0]
            assert "account_id" in account
            assert "platform" in account
            assert "handle" in account

    def test_api_posts_post_structure(self):
        """Test individual post structure."""
        response = client.get("/api/posts?limit=1")
        assert response.status_code == 200
        data = response.json()
        
        if data["posts"]:
            post = data["posts"][0]
            required_fields = ["id", "platform", "post_id", "url", "author_handle", "category", "text"]
            for field in required_fields:
                assert field in post, f"Missing required field: {field}"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_nonexistent_route(self):
        """Test 404 for nonexistent routes."""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

    def test_method_not_allowed(self):
        """Test that POST to GET-only endpoint is rejected."""
        response = client.post("/api/posts")
        assert response.status_code == 405

    def test_empty_category_filter(self):
        """Test filtering with empty category string."""
        response = client.get("/api/posts?category=")
        assert response.status_code == 200

    def test_whitespace_category(self):
        """Test filtering with whitespace category."""
        response = client.get("/api/posts?category=%20%20")
        assert response.status_code == 200


class TestAuthorizationBasics:
    """Basic authorization tests (for future auth implementation)."""

    def test_no_sensitive_data_in_api(self):
        """Test that API doesn't expose sensitive fields."""
        response = client.get("/api/posts?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        # raw_json should not be in the standard response (contains full scraper data)
        for post in data["posts"]:
            # These fields should not be in public API response
            assert "raw_json" not in post or post.get("raw_json") is None

    def test_accounts_no_credentials(self):
        """Test that accounts API doesn't expose credentials."""
        response = client.get("/api/accounts")
        assert response.status_code == 200
        data = response.json()
        
        for account in data:
            # Should not have any credential-like fields
            assert "password" not in account
            assert "token" not in account
            assert "api_key" not in account
