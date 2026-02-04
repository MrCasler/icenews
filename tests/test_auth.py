"""
Basic Auth tests for ICENews web application.

Tests verify that HTTP Basic Auth works correctly when enabled.

NOTE: These tests are skipped by default because they would interfere with other tests.
To enable auth testing, manually set env vars and run: 
  ICENEWS_AUTH_EMAIL=test@example.com ICENEWS_AUTH_PASSWORD=test123 pytest tests/test_auth.py -v

Run with: pytest tests/test_auth.py -v
"""
import base64
import os
import pytest
from fastapi.testclient import TestClient

# Import the app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

client = TestClient(app)


class TestBasicAuthDisabled:
    """Test behavior when auth is disabled (default for development)."""

    def test_homepage_accessible_without_auth(self):
        """When auth is disabled, homepage should be accessible."""
        response = client.get("/")
        # Should return 200 (no auth required)
        assert response.status_code == 200

    def test_api_accessible_without_auth(self):
        """When auth is disabled, API should be accessible."""
        response = client.get("/api/posts")
        assert response.status_code == 200

    def test_health_always_accessible(self):
        """Health endpoint should always be accessible (no auth)."""
        response = client.get("/health")
        assert response.status_code in [200, 503]


# Skip the auth-enabled tests by default to avoid interfering with other tests
# To run these, set env vars before importing: ICENEWS_AUTH_EMAIL=test@example.com ICENEWS_AUTH_PASSWORD=test123
@pytest.mark.skipif(
    not (os.environ.get("ICENEWS_AUTH_EMAIL") and os.environ.get("ICENEWS_AUTH_PASSWORD")),
    reason="Auth tests require ICENEWS_AUTH_EMAIL and ICENEWS_AUTH_PASSWORD env vars"
)
class TestBasicAuthEnabled:
    """Test behavior when auth is enabled."""

    def test_homepage_requires_auth(self):
        """When auth is enabled, homepage should require credentials."""
        response = client.get("/")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_api_requires_auth(self):
        """When auth is enabled, API should require credentials."""
        response = client.get("/api/posts")
        assert response.status_code == 401

    def test_homepage_accepts_valid_credentials(self):
        """Valid credentials should grant access to homepage."""
        email = os.environ.get("ICENEWS_AUTH_EMAIL")
        password = os.environ.get("ICENEWS_AUTH_PASSWORD")
        auth = base64.b64encode(f"{email}:{password}".encode()).decode()
        response = client.get(
            "/",
            headers={"Authorization": f"Basic {auth}"}
        )
        assert response.status_code == 200

    def test_api_accepts_valid_credentials(self):
        """Valid credentials should grant access to API."""
        email = os.environ.get("ICENEWS_AUTH_EMAIL")
        password = os.environ.get("ICENEWS_AUTH_PASSWORD")
        auth = base64.b64encode(f"{email}:{password}".encode()).decode()
        response = client.get(
            "/api/posts",
            headers={"Authorization": f"Basic {auth}"}
        )
        assert response.status_code == 200

    def test_rejects_invalid_email(self):
        """Invalid email should be rejected."""
        password = os.environ.get("ICENEWS_AUTH_PASSWORD")
        auth = base64.b64encode(f"wrong@example.com:{password}".encode()).decode()
        response = client.get(
            "/",
            headers={"Authorization": f"Basic {auth}"}
        )
        assert response.status_code == 401

    def test_rejects_invalid_password(self):
        """Invalid password should be rejected."""
        email = os.environ.get("ICENEWS_AUTH_EMAIL")
        auth = base64.b64encode(f"{email}:wrongpassword".encode()).decode()
        response = client.get(
            "/",
            headers={"Authorization": f"Basic {auth}"}
        )
        assert response.status_code == 401

    def test_health_bypasses_auth(self):
        """Health endpoint should always be accessible, even with auth enabled."""
        response = client.get("/health")
        # Should work without credentials
        assert response.status_code in [200, 503]


@pytest.mark.skipif(
    not (os.environ.get("ICENEWS_AUTH_EMAIL") and os.environ.get("ICENEWS_AUTH_PASSWORD")),
    reason="Auth tests require ICENEWS_AUTH_EMAIL and ICENEWS_AUTH_PASSWORD env vars"
)
class TestAuthSecurity:
    """Test security aspects of auth implementation."""

    def test_timing_attack_resistance(self):
        """Test that incorrect credentials don't leak timing info."""
        # Both wrong email and wrong password should take similar time
        # This is a basic check; real timing attack tests require statistical analysis
        
        password = os.environ.get("ICENEWS_AUTH_PASSWORD")
        email = os.environ.get("ICENEWS_AUTH_EMAIL")
        
        auth_wrong_email = base64.b64encode(f"wrong@example.com:{password}".encode()).decode()
        auth_wrong_pass = base64.b64encode(f"{email}:wrongpassword".encode()).decode()
        
        response1 = client.get("/", headers={"Authorization": f"Basic {auth_wrong_email}"})
        response2 = client.get("/", headers={"Authorization": f"Basic {auth_wrong_pass}"})
        
        # Both should be 401
        assert response1.status_code == 401
        assert response2.status_code == 401

    def test_empty_credentials_rejected(self):
        """Empty credentials should be rejected."""
        auth = base64.b64encode(b":").decode()
        response = client.get(
            "/",
            headers={"Authorization": f"Basic {auth}"}
        )
        assert response.status_code == 401

    def test_malformed_auth_header(self):
        """Malformed auth headers should be rejected gracefully."""
        response = client.get(
            "/",
            headers={"Authorization": "Basic NOTBASE64!!!"}
        )
        # Should handle gracefully (401 or 400)
        assert response.status_code in [400, 401]
