"""
Authentication module for ICENews.

Implements magic link (passwordless) authentication with session management.
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.db import (
    create_or_get_user,
    get_user_by_email,
    get_user_by_id,
    save_magic_link,
    get_magic_link,
    mark_magic_link_used,
    update_user_last_login,
)

# Configuration
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-secret-key-change-in-production")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
MAGIC_LINK_EXPIRY_MINUTES = 15
SESSION_EXPIRY_DAYS = 30

# Session serializer
_serializer = URLSafeTimedSerializer(APP_SECRET_KEY)


def generate_magic_link(email: str) -> tuple[str, str]:
    """
    Generate a magic link for email authentication.
    
    Returns: (token, full_url)
    """
    email = email.lower().strip()
    
    # Generate secure random token
    token = secrets.token_urlsafe(32)
    
    # Calculate expiration
    expires_at = (datetime.now() + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)).isoformat()
    
    # Save to database
    save_magic_link(email, token, expires_at)
    
    # Build full URL
    full_url = urljoin(APP_BASE_URL, f"/auth/verify/{token}")
    
    return token, full_url


def verify_magic_link(token: str) -> Optional[dict]:
    """
    Verify a magic link token and return user info if valid.
    
    Returns: User dict if valid, None if invalid/expired/used
    """
    if not token:
        return None
    token = token.strip()
    # Get token from database
    link = get_magic_link(token)
    
    if not link:
        return None
    
    # Check if already used
    if link.get("used"):
        return None
    
    # Check expiration
    expires_at = link.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if datetime.now() > expiry:
                return None
        except (ValueError, TypeError):
            return None
    
    # Mark as used
    mark_magic_link_used(token)
    
    # Get or create user
    email = link.get("email")
    if not email:
        return None
    
    user = create_or_get_user(email)
    if user:
        update_user_last_login(user["id"])
    
    return user


def create_session_token(user_id: int, email: str) -> str:
    """
    Create a signed session token for the user.
    
    Returns: Signed session token string
    """
    data = {
        "user_id": user_id,
        "email": email,
    }
    return _serializer.dumps(data)


def verify_session_token(token: str) -> Optional[dict]:
    """
    Verify a session token and return session data.
    
    Returns: Session dict with user_id and email, or None if invalid
    """
    try:
        # Max age in seconds (30 days)
        max_age = SESSION_EXPIRY_DAYS * 24 * 60 * 60
        data = _serializer.loads(token, max_age=max_age)
        return data
    except (BadSignature, SignatureExpired):
        return None


def get_session_user(token: str) -> Optional[dict]:
    """
    Get full user info from a session token.
    
    Returns: User dict or None if invalid session
    """
    session = verify_session_token(token)
    if not session:
        return None
    
    user_id = session.get("user_id")
    if not user_id:
        return None
    
    return get_user_by_id(user_id)


async def send_magic_link_email(email: str, magic_link_url: str) -> bool:
    """
    Send magic link email to user.
    
    Uses Resend API if RESEND_API_KEY is set, otherwise logs to console.
    Returns: True if sent successfully
    """
    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    
    email_subject = "Sign in to ICENews"
    email_body = f"""
Hello,

Click the link below to sign in to ICENews:

{magic_link_url}

This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes.

If you didn't request this link, you can safely ignore this email.

- ICENews Team
    """.strip()
    
    email_html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .button {{ display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
        .button:hover {{ background: #1d4ed8; }}
        .footer {{ margin-top: 30px; font-size: 14px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Sign in to ICENews</h2>
        <p>Click the button below to sign in:</p>
        <a href="{magic_link_url}" class="button">Sign In</a>
        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #2563eb;">{magic_link_url}</p>
        <p>This link will expire in {MAGIC_LINK_EXPIRY_MINUTES} minutes.</p>
        <div class="footer">
            <p>If you didn't request this link, you can safely ignore this email.</p>
            <p>- ICENews Team</p>
        </div>
    </div>
</body>
</html>
    """.strip()
    
    if resend_api_key and resend_api_key.startswith("re_"):
        try:
            import resend
            resend.api_key = resend_api_key
            
            from_email = os.getenv("RESEND_FROM_EMAIL", "").strip()
            # Use Resend's default sender when unset or when domain may not be verified (e.g. localhost)
            app_base = os.getenv("APP_BASE_URL", "").lower()
            if not from_email or "localhost" in app_base:
                from_email = "onboarding@resend.dev"
            print(f"[AUTH] Sending magic link email to: {email}", flush=True)
            print(f"[AUTH] From: {from_email}", flush=True)
            print(f"[AUTH] API Key prefix: {resend_api_key[:15]}...", flush=True)
            
            # Send email using Resend SDK - correct format per their docs
            response = resend.Emails.send({
                "from": from_email,
                "to": email,  # Single email string, not array
                "subject": email_subject,
                "html": email_html,
                "text": email_body,
            })
            
            print(f"[AUTH] Resend response: {response}", flush=True)
            
            # Check if response has an id (success indicator)
            if response and (hasattr(response, 'id') or (isinstance(response, dict) and response.get('id'))):
                email_id = response.get('id') if isinstance(response, dict) else getattr(response, 'id', None)
                print(f"[AUTH] Email sent successfully! ID: {email_id}", flush=True)
                return True
            else:
                print(f"[AUTH] Unexpected response format: {response}", flush=True)
                return True  # Assume success if no error was raised
                
        except Exception as e:
            import traceback
            print(f"[AUTH] Failed to send email via Resend: {e}", flush=True)
            print(f"[AUTH] Traceback: {traceback.format_exc()}", flush=True)
            # If domain not verified, retry with Resend's test sender so the user still gets the email
            err_str = str(e).lower()
            if "domain" in err_str and ("not verified" in err_str or "verify" in err_str):
                try:
                    print(f"[AUTH] Retrying with onboarding@resend.dev (domain not verified)", flush=True)
                    response = resend.Emails.send({
                        "from": "onboarding@resend.dev",
                        "to": email,
                        "subject": email_subject,
                        "html": email_html,
                        "text": email_body,
                    })
                    if response and (hasattr(response, "id") or (isinstance(response, dict) and response.get("id"))):
                        print(f"[AUTH] Sent via onboarding@resend.dev", flush=True)
                        return True
                except Exception as retry_e:
                    print(f"[AUTH] Retry failed: {retry_e}", flush=True)
            # Fall back to console logging
            print(f"\n{'='*60}")
            print(f"[FALLBACK] Magic Link Email (Resend failed)")
            print(f"To: {email}")
            print(f"Subject: {email_subject}")
            print(f"Link: {magic_link_url}")
            print(f"{'='*60}\n", flush=True)
            return False
    else:
        # Development mode - log to console
        if resend_api_key:
            print(f"[AUTH] Warning: RESEND_API_KEY appears invalid (should start with 're_'): {resend_api_key[:20]}...", flush=True)
        else:
            print(f"[AUTH] RESEND_API_KEY not set, using console mode", flush=True)
        
        print(f"\n{'='*60}")
        print(f"[DEV MODE] Magic Link Email")
        print(f"To: {email}")
        print(f"Subject: {email_subject}")
        print(f"Link: {magic_link_url}")
        print(f"{'='*60}\n", flush=True)
        return True
