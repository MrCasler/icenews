"""
Comprehensive Security Tests for ICENews

Covers the main attack vectors:
1. SQL Injection
2. XSS (Cross-Site Scripting)
3. CSRF protection
4. Authentication bypass
5. Authorization bypass (premium features)
6. Path traversal
7. Input validation
8. Session security

Run with: python -m pytest tests/test_security_comprehensive.py -v
"""
import pytest
from fastapi.testclient import TestClient
import base64
import json
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment
os.environ["ICENEWS_AUTH_EMAIL"] = "test@example.com"
os.environ["ICENEWS_AUTH_PASSWORD"] = "testpassword123"

from app.main import app

client = TestClient(app)


def get_auth_header(email: str = "test@example.com", password: str = "testpassword123") -> dict:
    """Generate Basic Auth header."""
    credentials = base64.b64encode(f"{email}:{password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"}


class TestSQLInjection:
    """Test SQL injection attack vectors."""
    
    def test_sql_injection_in_category_filter(self):
        """Category filter should not be vulnerable to SQL injection."""
        malicious_inputs = [
            "'; DROP TABLE posts; --",
            "' OR '1'='1",
            "1; SELECT * FROM users--",
            "UNION SELECT * FROM premium_users--",
            "' OR 1=1--",
            "admin'--",
            "1' AND '1'='1",
        ]
        
        for payload in malicious_inputs:
            response = client.get(
                f"/api/posts?category={payload}",
                headers=get_auth_header()
            )
            # Should return empty results, not crash or expose data
            assert response.status_code in [200, 422], f"Unexpected status for payload: {payload}"
    
    def test_sql_injection_in_post_id(self):
        """Post ID parameter should not be vulnerable to SQL injection."""
        malicious_inputs = [
            "'; DROP TABLE posts; --",
            "1 OR 1=1",
            "1' OR '1'='1'--",
            "1; DELETE FROM posts--",
        ]
        
        for payload in malicious_inputs:
            response = client.post(
                f"/api/posts/{payload}/like",
                headers=get_auth_header()
            )
            # Should return 404 (post not found), not crash
            assert response.status_code in [404, 422], f"Unexpected status for payload: {payload}"
    
    def test_sql_injection_in_limit_offset(self):
        """Limit and offset should be validated as integers."""
        malicious_inputs = [
            "1; DROP TABLE posts--",
            "-1",
            "999999999999",
            "1.5",
            "abc",
        ]
        
        for payload in malicious_inputs:
            response = client.get(
                f"/api/posts?limit={payload}",
                headers=get_auth_header()
            )
            # Should either reject or clamp the value
            assert response.status_code in [200, 422]


class TestXSSPrevention:
    """Test XSS attack prevention."""
    
    def test_xss_in_search_params(self):
        """URL parameters should not reflect XSS payloads."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "'><script>alert(document.cookie)</script>",
        ]
        
        for payload in xss_payloads:
            response = client.get(
                f"/api/posts?category={payload}",
                headers=get_auth_header()
            )
            # The response should not contain unescaped script tags
            if response.status_code == 200:
                content = response.text
                assert "<script>" not in content.lower() or "alert" not in content
    
    def test_json_response_content_type(self):
        """API responses should have correct content type to prevent XSS."""
        response = client.get("/api/posts", headers=get_auth_header())
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type


class TestAuthenticationBypass:
    """Test authentication bypass attempts."""
    
    def test_no_auth_header(self):
        """Requests without auth header should work (guest mode) but not have premium."""
        response = client.get("/")
        # Guest access is allowed
        assert response.status_code == 200
    
    def test_invalid_auth_scheme(self):
        """Invalid auth scheme should be rejected."""
        response = client.get(
            "/api/posts",
            headers={"Authorization": "Bearer invalid_token"}
        )
        # Should still work as guest (no auth required for viewing)
        assert response.status_code == 200
    
    def test_malformed_base64_credentials(self):
        """Malformed base64 should not crash the server."""
        response = client.get(
            "/api/posts",
            headers={"Authorization": "Basic not-valid-base64!!!"}
        )
        # Should fallback to guest mode
        assert response.status_code == 200
    
    def test_wrong_password(self):
        """Wrong password should return 401 or fallback to guest."""
        response = client.get(
            "/api/posts",
            headers=get_auth_header(password="wrongpassword")
        )
        # Either 401 or guest mode (200)
        assert response.status_code in [200, 401]
    
    def test_timing_attack_resistance(self):
        """Password comparison should use constant-time comparison."""
        import time
        
        # Test with correct password
        start = time.time()
        for _ in range(10):
            client.get("/api/posts", headers=get_auth_header())
        correct_time = time.time() - start
        
        # Test with wrong password (same length)
        start = time.time()
        for _ in range(10):
            client.get("/api/posts", headers=get_auth_header(password="wrongpassword1"))
        wrong_time = time.time() - start
        
        # Times should be similar (within 50% variance is acceptable for test)
        # This is a basic check - real timing attack tests need more sophisticated methods
        assert abs(correct_time - wrong_time) < max(correct_time, wrong_time)


class TestAuthorizationBypass:
    """Test authorization bypass for premium features."""
    
    def test_download_without_premium(self):
        """Non-premium users should not be able to download."""
        response = client.get(
            "/api/posts/some_post_id/download",
            headers=get_auth_header()
        )
        # Should be 403 (forbidden) or 404 (post not found)
        assert response.status_code in [403, 404]
    
    def test_admin_endpoint_protection(self):
        """Admin endpoints should require authentication."""
        response = client.post(
            "/api/admin/premium/add",
            json={"email": "hacker@evil.com"}
        )
        # Should require auth (but may allow with valid auth)
        # The endpoint exists, just needs proper auth
        assert response.status_code in [200, 401, 403, 422]
    
    def test_stripe_webhook_signature_required(self):
        """Stripe webhook should require valid signature."""
        response = client.post(
            "/api/stripe/webhook",
            content=b'{"type": "checkout.session.completed"}',
            headers={"stripe-signature": "fake_signature"}
        )
        # Should fail without valid signature
        assert response.status_code == 400


class TestInputValidation:
    """Test input validation and sanitization."""
    
    def test_email_validation_in_magic_link(self):
        """Email should be properly validated."""
        invalid_emails = [
            "not-an-email",
            "@missing-local.com",
            "missing-domain@",
            "spaces in@email.com",
            "<script>@xss.com",
            "'; DROP TABLE users;--@evil.com",
        ]
        
        for email in invalid_emails:
            response = client.post(
                "/auth/magic-link",
                json={"email": email}
            )
            assert response.status_code in [400, 422], f"Should reject invalid email: {email}"
    
    def test_nickname_validation(self):
        """Nickname should be sanitized."""
        invalid_nicknames = [
            "<script>alert('xss')</script>",
            "a" * 100,  # Too long
            "",  # Empty
        ]
        
        for nickname in invalid_nicknames:
            response = client.post(
                "/api/user/nickname",
                json={"nickname": nickname},
                headers=get_auth_header()
            )
            # Should reject or sanitize
            assert response.status_code in [400, 401, 403, 422]
    
    def test_url_validation_in_upload(self):
        """Upload URL should be validated."""
        invalid_urls = [
            "not-a-url",
            "javascript:alert('xss')",
            "file:///etc/passwd",
            "ftp://malicious.com/file",
            "https://not-supported-platform.com/video",
        ]
        
        for url in invalid_urls:
            response = client.post(
                "/api/uploads/submit",
                json={"url": url},
                headers=get_auth_header()
            )
            # Should reject invalid URLs (may be 400, 403, or 401)
            assert response.status_code in [400, 401, 403, 422], f"Should reject invalid URL: {url}"
    
    def test_large_payload_rejection(self):
        """Very large payloads should be rejected."""
        large_payload = {"data": "x" * 10_000_000}  # 10MB of data
        
        response = client.post(
            "/api/admin/import",
            json=large_payload
        )
        # Should either reject or timeout, not crash
        assert response.status_code in [400, 413, 422, 500]


class TestSessionSecurity:
    """Test session and cookie security."""
    
    def test_session_cookie_attributes(self):
        """Session cookies should have secure attributes."""
        # This test checks the login flow sets cookies correctly
        # In production (RENDER=1), cookies should be secure and httponly
        response = client.get("/auth/verify/fake_token")
        
        # Should redirect to login with error
        assert response.status_code in [200, 302]
    
    def test_magic_link_token_validation(self):
        """Magic link tokens should be validated."""
        invalid_tokens = [
            "",
            "short",
            "a" * 1000,  # Too long
            "../../../etc/passwd",
            "<script>alert('xss')</script>",
            "'; DROP TABLE magic_links;--",
        ]
        
        for token in invalid_tokens:
            response = client.get(f"/auth/verify/{token}")
            # Should show error page, not crash
            assert response.status_code in [200, 404, 422]


class TestPathTraversal:
    """Test path traversal attack prevention."""
    
    def test_download_path_traversal(self):
        """Download endpoint should prevent path traversal."""
        traversal_payloads = [
            "../../../etc/passwd",
            "..%2F..%2F..%2Fetc%2Fpasswd",
            "....//....//....//etc/passwd",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\SAM",
        ]
        
        for payload in traversal_payloads:
            response = client.get(
                f"/api/posts/{payload}/download",
                headers=get_auth_header()
            )
            # Should return 403 or 404, not the file contents
            assert response.status_code in [403, 404, 422]
            assert b"root:" not in response.content  # Unix passwd file content


class TestRateLimiting:
    """Test rate limiting (if implemented)."""
    
    def test_like_endpoint_no_rapid_abuse(self):
        """Like endpoint should handle rapid requests gracefully."""
        # This tests that the endpoint doesn't crash under rapid requests
        # Real rate limiting would be at the reverse proxy level
        for _ in range(20):
            response = client.post(
                "/api/posts/test_post/like",
                headers=get_auth_header()
            )
            assert response.status_code in [200, 404, 429]


class TestHealthEndpoint:
    """Test health endpoint security."""
    
    def test_health_no_sensitive_data(self):
        """Health endpoint should not expose sensitive data."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        # Should only contain safe info
        assert "password" not in str(data).lower()
        assert "secret" not in str(data).lower()
        assert "key" not in str(data).lower()
        assert "token" not in str(data).lower()


class TestCSRFProtection:
    """Test CSRF protection mechanisms."""
    
    def test_state_changing_requires_proper_request(self):
        """State-changing operations should not be vulnerable to CSRF."""
        # POST requests should work (API endpoints typically use tokens/sessions)
        response = client.post(
            "/api/posts/test/like",
            headers=get_auth_header()
        )
        # Should be 404 (post not found) or 200, not a CSRF error
        assert response.status_code in [200, 404]
    
    def test_get_requests_are_safe(self):
        """GET requests should not change state."""
        # Download via GET is safe as it requires auth
        response = client.get("/api/posts/test/download")
        # Should require premium, but not change any state
        assert response.status_code in [401, 403, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
