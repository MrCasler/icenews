"""
Smoke tests for ICENews web application.

These tests verify core functionality is working before deployment:
- Homepage renders with initial JSON
- API returns posts correctly
- Like/unlike endpoints update count
- Security features remain active

Run with: pytest tests/test_smoke.py -v
"""
import json
import pytest
from fastapi.testclient import TestClient

# Import the app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app
from app.db import get_connection

client = TestClient(app)


class TestHomepageRendering:
    """Test that the homepage renders correctly with initial data."""

    def test_homepage_returns_200(self):
        """Verify homepage loads successfully."""
        response = client.get("/")
        assert response.status_code == 200

    def test_homepage_contains_alpine_app(self):
        """Verify Alpine.js app is initialized."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        
        # Check for Alpine app initialization
        assert 'x-data="iceNews()"' in html
        assert 'id="initial-posts"' in html
        assert 'id="initial-total"' in html

    def test_initial_posts_json_valid(self):
        """Verify initial-posts JSON is valid and well-formed."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        
        # Extract the JSON payload
        marker = 'id="initial-posts"'
        assert marker in html
        start = html.index(marker)
        start = html.index(">", start) + 1
        end = html.index("</script>", start)
        payload = html[start:end]
        
        # Parse JSON to verify it's valid
        posts = json.loads(payload)
        assert isinstance(posts, list)
        
        # If there are posts, verify structure
        if posts:
            post = posts[0]
            assert "post_id" in post
            assert "url" in post
            assert "text" in post
            assert "author_handle" in post

    def test_initial_posts_xss_safe(self):
        """Verify initial posts JSON is XSS-safe (< and > are escaped)."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        
        # Extract the JSON payload
        marker = 'id="initial-posts"'
        start = html.index(marker)
        start = html.index(">", start) + 1
        end = html.index("</script>", start)
        payload = html[start:end]
        
        # Should not contain literal < or > (must be escaped)
        assert "<" not in payload
        assert ">" not in payload


class TestAPIEndpoints:
    """Test core API endpoints."""

    def test_api_posts_returns_valid_json(self):
        """Verify /api/posts returns valid JSON with expected structure."""
        response = client.get("/api/posts")
        assert response.status_code == 200
        
        data = response.json()
        assert "posts" in data
        assert "total" in data
        assert isinstance(data["posts"], list)
        assert isinstance(data["total"], int)

    def test_api_posts_has_like_count(self):
        """Verify posts include like_count field."""
        response = client.get("/api/posts?limit=1")
        assert response.status_code == 200
        
        data = response.json()
        if data["posts"]:
            post = data["posts"][0]
            assert "like_count" in post
            assert isinstance(post["like_count"], int)
            assert post["like_count"] >= 0

    def test_api_accounts_returns_list(self):
        """Verify /api/accounts returns a list."""
        response = client.get("/api/accounts")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)

    def test_api_posts_pagination_capped(self):
        """Verify large limit values are capped (soft cap)."""
        response = client.get("/api/posts?limit=999999")
        assert response.status_code == 200
        
        data = response.json()
        # Should not return more than 100 posts (soft cap)
        assert len(data["posts"]) <= 100


class TestLikesEndpoints:
    """Test like/unlike endpoints."""

    def test_like_nonexistent_post_returns_404(self):
        """Verify liking a non-existent post returns 404."""
        fake_post_id = "fake_post_id_999999"
        response = client.post(f"/api/posts/{fake_post_id}/like")
        assert response.status_code == 404

    def test_unlike_nonexistent_post_returns_404(self):
        """Verify unliking a non-existent post returns 404."""
        fake_post_id = "fake_post_id_999999"
        response = client.post(f"/api/posts/{fake_post_id}/unlike")
        assert response.status_code == 404

    def test_like_endpoint_increments_count(self):
        """Verify like endpoint increments count correctly."""
        # Get a real post first
        response = client.get("/api/posts?limit=1")
        assert response.status_code == 200
        data = response.json()
        
        if not data["posts"]:
            pytest.skip("No posts in database to test")
        
        post = data["posts"][0]
        post_id = post["post_id"]
        initial_count = post["like_count"]
        
        # Like the post
        response = client.post(f"/api/posts/{post_id}/like")
        assert response.status_code == 200
        
        like_data = response.json()
        assert "post_id" in like_data
        assert "like_count" in like_data
        assert like_data["post_id"] == post_id
        assert like_data["like_count"] == initial_count + 1

    def test_unlike_endpoint_decrements_count(self):
        """Verify unlike endpoint decrements count correctly."""
        # Get a real post first
        response = client.get("/api/posts?limit=1")
        assert response.status_code == 200
        data = response.json()
        
        if not data["posts"]:
            pytest.skip("No posts in database to test")
        
        post = data["posts"][0]
        post_id = post["post_id"]
        
        # Like the post first to ensure count > 0
        client.post(f"/api/posts/{post_id}/like")
        
        # Get current count
        response = client.get("/api/posts?limit=50")
        data = response.json()
        current_post = next(p for p in data["posts"] if p["post_id"] == post_id)
        current_count = current_post["like_count"]
        
        # Unlike the post
        response = client.post(f"/api/posts/{post_id}/unlike")
        assert response.status_code == 200
        
        unlike_data = response.json()
        assert unlike_data["like_count"] == max(0, current_count - 1)

    def test_unlike_floors_at_zero(self):
        """Verify unlike endpoint doesn't go below zero."""
        # Get a real post
        response = client.get("/api/posts?limit=1")
        assert response.status_code == 200
        data = response.json()
        
        if not data["posts"]:
            pytest.skip("No posts in database to test")
        
        post = data["posts"][0]
        post_id = post["post_id"]
        
        # Unlike multiple times
        for _ in range(5):
            response = client.post(f"/api/posts/{post_id}/unlike")
            assert response.status_code == 200
            data = response.json()
            # Should never be negative
            assert data["like_count"] >= 0


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_endpoint_exists(self):
        """Verify /health endpoint exists and returns status."""
        response = client.get("/health")
        # Should return 200 (healthy) or 503 (database unavailable during test)
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "posts" in data


class TestSecurityFeatures:
    """Verify security features are still active."""

    def test_xss_prevention_active(self):
        """Verify XSS prevention is still working."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        
        # Extract JSON payload
        marker = 'id="initial-posts"'
        if marker in html:
            start = html.index(marker)
            start = html.index(">", start) + 1
            end = html.index("</script>", start)
            payload = html[start:end]
            
            # Must not contain unescaped < or >
            assert "<" not in payload

    def test_large_number_defense_active(self):
        """Verify large number soft caps are still working."""
        response = client.get("/api/posts?limit=1000000&offset=1000000")
        assert response.status_code == 200
        
        data = response.json()
        # Should be capped, not cause error
        assert len(data["posts"]) <= 100

    def test_sql_injection_defense_active(self):
        """Verify SQL injection prevention is still working."""
        payload = "'; DROP TABLE posts; --"
        response = client.get(f"/api/posts?category={payload}")
        # Should return 200 (safe handling), not crash
        assert response.status_code == 200


class TestDatabaseIntegrity:
    """Test database integrity and schema."""

    def test_post_likes_table_exists(self):
        """Verify post_likes table exists."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='post_likes'"
        )
        result = cur.fetchone()
        conn.close()
        
        assert result is not None
        assert result[0] == "post_likes"

    def test_posts_table_exists(self):
        """Verify posts table exists."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
        )
        result = cur.fetchone()
        conn.close()
        
        assert result is not None

    def test_accounts_table_exists(self):
        """Verify accounts table exists."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
        )
        result = cur.fetchone()
        conn.close()
        
        assert result is not None
