"""ICENews web app: FastAPI + Jinja2 + Alpine.js + TailwindCSS."""
import os

# Load environment variables from .env file FIRST
from dotenv import load_dotenv
load_dotenv()

import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.db import (
    add_premium_user,
    create_or_get_user,
    create_user_post,
    delete_user_post,
    get_accounts,
    get_all_downloads,
    get_download_by_id,
    get_user_by_twitter_id,
    save_twitter_connection,
    get_community_post_count,
    get_community_posts,
    get_connection,
    get_download_count,
    get_post_by_post_id,
    get_post_count,
    get_posts,
    get_user_by_email,
    get_user_by_id,
    get_user_downloads,
    get_user_posts_by_user,
    get_user_stats,
    init_db,
    is_premium_user,
    like_post,
    like_user_post,
    unlike_user_post,
    save_download,
    unlike_post,
    update_user_nickname,
    update_user_profile,
)
from app.db import DB_PATH as _DB_PATH
from app.downloads import check_yt_dlp_available, download_x_content

# Optional: X (Twitter) OAuth
try:
    from authlib.integrations.starlette_client import OAuth
    _OAUTH_AVAILABLE = True
except ImportError:
    _OAUTH_AVAILABLE = False
from app.models import AccountOut, LikeUpdateOut, PostListResponse, PostOut
from app.auth import (
    generate_magic_link,
    verify_magic_link,
    create_session_token,
    get_session_user,
    send_magic_link_email,
)
from app.stripe_handlers import (
    create_checkout_session,
    create_portal_session,
    handle_webhook,
    get_subscription_status,
    SUBSCRIPTION_PRICE_EUR,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: Initialize the database schema
    print(f"[STARTUP] Current working directory: {os.getcwd()}", flush=True)
    print(f"[STARTUP] DB_PATH configured as: {get_connection.__module__}", flush=True)
    from app.db import DB_PATH
    print(f"[STARTUP] Database path: {DB_PATH}", flush=True)
    print(f"[STARTUP] Database path exists: {DB_PATH.exists()}", flush=True)
    print(f"[STARTUP] Database parent exists: {DB_PATH.parent.exists()}", flush=True)
    print(f"[STARTUP] Database parent writable: {os.access(DB_PATH.parent, os.W_OK)}", flush=True)
    init_db()
    print(f"[STARTUP] Database initialized successfully", flush=True)
    yield
    # Shutdown: nothing to do currently


app = FastAPI(
    title="ICENews",
    description="Social monitoring for government & independent sources",
    lifespan=lifespan
)
# Required for X (Twitter) OAuth: Authlib stores state in request.session
_session_secret = os.getenv("APP_SECRET_KEY", "dev-secret-key-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=_session_secret)
security = HTTPBasic()

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# Umami Analytics config (set in .env; empty = disabled)
UMAMI_WEBSITE_ID = os.environ.get("UMAMI_WEBSITE_ID", "")
UMAMI_SCRIPT_URL = os.environ.get("UMAMI_SCRIPT_URL", "https://cloud.umami.is/script.js")

# Basic Auth config (set in .env; empty = disabled)
AUTH_EMAIL = os.environ.get("ICENEWS_AUTH_EMAIL", "").strip()
AUTH_PASSWORD = os.environ.get("ICENEWS_AUTH_PASSWORD", "").strip()
# Auth is only enabled if BOTH email and password are non-empty
AUTH_ENABLED = bool(AUTH_EMAIL) and bool(AUTH_PASSWORD)

# Session cookie name
SESSION_COOKIE_NAME = "icenews_session"

# X (Twitter) OAuth - optional, enabled if authlib + X_CLIENT_ID + X_CLIENT_SECRET are set
if _OAUTH_AVAILABLE and os.getenv("X_CLIENT_ID") and os.getenv("X_CLIENT_SECRET"):
    _oauth = OAuth()
    _oauth.register(
        name="twitter",
        client_id=os.getenv("X_CLIENT_ID"),
        client_secret=os.getenv("X_CLIENT_SECRET"),
        authorize_url="https://twitter.com/i/oauth2/authorize",
        access_token_url="https://api.twitter.com/2/oauth2/token",
        client_kwargs={
            "scope": "tweet.read users.read offline.access",
            "code_challenge_method": "S256",
        },
    )
else:
    _oauth = None


async def get_optional_auth():
    """
    Conditionally return auth security or None based on AUTH_ENABLED.
    
    This is a workaround to make HTTPBasic optional - we can't use
    Depends(security) conditionally in function signatures, so we return
    the security object itself and let verify_auth call it.
    """
    if AUTH_ENABLED:
        return security
    return None


async def verify_auth(
    request: Request,
    auth_security = Depends(get_optional_auth)
) -> dict:
    """
    Verify authentication via session cookie OR HTTP Basic Auth.
    
    Returns a dict with authentication info:
    - authenticated: bool (True if logged in via any method)
    - email: str or None (user's email if authenticated)
    - is_premium: bool (whether user has premium access)
    - user_id: int or None (user's database ID if session-authenticated)
    - nickname: str or None (user's nickname if set)
    
    Authentication order:
    1. Check session cookie first (magic link auth)
    2. Fall back to HTTP Basic Auth if no session
    3. Return guest access if neither present
    
    Security notes:
    - Uses secrets.compare_digest to prevent timing attacks on basic auth
    - Session tokens are signed with itsdangerous
    - /health endpoint should bypass this dependency
    """
    # 1. Check session cookie first
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        user = get_session_user(session_token)
        if user:
            # Check premium from users table
            is_premium = bool(user.get("is_premium"))
            # Also check legacy premium_users table
            if not is_premium:
                is_premium = is_premium_user(user.get("email", ""))
            
            return {
                "authenticated": True,
                "email": user.get("email"),
                "is_premium": is_premium,
                "user_id": user.get("id"),
                "nickname": user.get("nickname"),
            }
    
    # 2. Check HTTP Basic Auth (for admin/legacy access)
    if AUTH_ENABLED:
        from fastapi.security.utils import get_authorization_scheme_param
        
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, credentials_str = get_authorization_scheme_param(authorization)
            if scheme.lower() == "basic":
                import base64
                try:
                    decoded = base64.b64decode(credentials_str).decode("utf-8")
                    username, _, password = decoded.partition(":")
                    
                    correct_username = secrets.compare_digest(username, AUTH_EMAIL)
                    correct_password = secrets.compare_digest(password, AUTH_PASSWORD)
                    
                    if correct_username and correct_password:
                        # Check premium status
                        premium_status = is_premium_user(username)
                        # Get or create user record
                        user = get_user_by_email(username)
                        
                        return {
                            "authenticated": True,
                            "email": username,
                            "is_premium": premium_status,
                            "user_id": user.get("id") if user else None,
                            "nickname": user.get("nickname") if user else None,
                        }
                except Exception:
                    pass  # Invalid credentials, continue to guest
    
    # 3. Return guest access (not authenticated)
    return {
        "authenticated": False,
        "email": None,
        "is_premium": False,
        "user_id": None,
        "nickname": None,
    }


def _posts_to_json(posts: list) -> str:
    """Serialize posts for safe JSON in HTML (no XSS)."""
    import json
    return json.dumps(posts).replace("<", "\\u003c").replace(">", "\\u003e")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, auth_info: dict = Depends(verify_auth)):
    """Homepage: community board with scraped posts and user posts."""
    import time
    
    # Get scraped posts (from X/Twitter monitoring)
    scraped_posts = get_posts(limit=30)
    
    # Get community posts (user-submitted)
    community_posts = get_community_posts(limit=20)
    
    # Merge and sort by created_at (most recent first)
    # Add a 'post_type' field to distinguish them
    for post in scraped_posts:
        post['post_type'] = 'scraped'
        post['is_community'] = False
    
    for post in community_posts:
        post['post_type'] = 'community'
        post['is_community'] = True
        post['post_id'] = f"community_{post['id']}"  # Unique ID for frontend
        post['url'] = '#'  # Community posts don't have external URLs
        post['category'] = 'independent'  # Label as community
        post['author_handle'] = post.get('nickname') or post.get('email', '').split('@')[0]
        post['author_display_name'] = post.get('nickname') or 'Community Member'
        # Use the content field as text
        post['text'] = post.get('content', '')
    
    # Merge and sort by created_at
    all_posts = scraped_posts + community_posts
    all_posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Limit to 50 total
    all_posts = all_posts[:50]
    
    total = get_post_count() + get_community_post_count()
    accounts = get_accounts()
    posts_json = _posts_to_json(all_posts)
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "posts": all_posts,
            "posts_json": posts_json,
            "total_posts": total,
            "accounts": accounts,
            # User auth and premium status
            "is_premium": auth_info.get("is_premium", False),
            "user_email": auth_info.get("email"),
            # Umami analytics (empty string = disabled in template)
            "umami_website_id": UMAMI_WEBSITE_ID,
            "umami_script_url": UMAMI_SCRIPT_URL,
            # Cache-busting for static assets during development
            "cache_bust": int(time.time()),
        },
    )


@app.get("/why", response_class=HTMLResponse)
async def morality_page(request: Request):
    """Why this matters - morality/about page."""
    return templates.TemplateResponse(
        request=request,
        name="morality.html",
        context={}
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy policy."""
    return templates.TemplateResponse(request=request, name="privacy.html", context={})


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms of service."""
    return templates.TemplateResponse(request=request, name="terms.html", context={})


@app.get("/api/posts", response_model=PostListResponse)
async def api_posts(
    # Security note:
    # We validate basic shape (int, non-negative) in FastAPI, then apply a
    # *soft cap* below. This prevents "large number attacks" (resource
    # exhaustion / lower-layer integer edge cases) while staying user-friendly
    # (asking for limit=1000000 still returns a normal response).
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    category: str | None = None,
    account_id: int | None = Query(default=None, ge=1, le=10_000_000),
    auth_info: dict = Depends(verify_auth),
):
    """JSON API for posts (for Alpine.js / fetch)."""
    # Soft caps (defense-in-depth; DB layer also clamps).
    # Professor-note: in APIs, "reject" vs "cap" is a product decision.
    # - Reject (422) is strict and explicit.
    # - Cap (200) is friendlier and still safe.
    limit = min(limit, 100)
    offset = min(offset, 10_000)

    posts = get_posts(limit=limit, offset=offset, category=category, account_id=account_id)
    total = get_post_count(category=category, account_id=account_id)
    return PostListResponse(
        posts=[PostOut(**p) for p in posts],
        total=total,
    )


@app.get("/api/accounts")
async def api_accounts(auth_info: dict = Depends(verify_auth)):
    """JSON API for accounts."""
    accounts = get_accounts()
    return [AccountOut(**a) for a in accounts]


@app.post("/api/posts/{post_id}/like", response_model=LikeUpdateOut)
async def api_like_post(post_id: str, auth_info: dict = Depends(verify_auth)):
    """
    Increment the global like count for a post.
    
    Security note:
    - No user identity is stored (privacy-preserving).
    - This is a global counter; abuse mitigation (rate limiting) should be
      added at the reverse proxy layer before public deployment.
    """
    # Verify the post exists before allowing like
    post = get_post_by_post_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    new_count = like_post(post_id)
    return LikeUpdateOut(post_id=post_id, like_count=new_count)


@app.post("/api/posts/{post_id}/unlike", response_model=LikeUpdateOut)
async def api_unlike_post(post_id: str, auth_info: dict = Depends(verify_auth)):
    """
    Decrement the global like count for a post (floored at 0).
    
    Security note:
    - No user identity is stored (privacy-preserving).
    - This is a global counter; abuse mitigation (rate limiting) should be
      added at the reverse proxy layer before public deployment.
    """
    # Verify the post exists before allowing unlike
    post = get_post_by_post_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    new_count = unlike_post(post_id)
    return LikeUpdateOut(post_id=post_id, like_count=new_count)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns 200 if the app and database are accessible.
    Returns 503 if the database is unavailable.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM posts")
        count = cur.fetchone()[0]
        conn.close()
        return {"status": "healthy", "posts": count}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/api/posts/{post_id}/download")
async def download_post_media(post_id: str, auth_info: dict = Depends(verify_auth)):
    """
    Download media from a post (X/Twitter).
    
    Available to all users. Premium users also get downloads saved to their gallery.
    """
    # Downloads are available to everyone - no premium check needed
    
    # Check if yt-dlp is available
    if not check_yt_dlp_available():
        raise HTTPException(
            status_code=503,
            detail="Download service temporarily unavailable (yt-dlp not installed)"
        )
    
    # Get post details
    post = get_post_by_post_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    url = post.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Post has no URL")
    
    # Validate it's a supported platform URL
    platform = _detect_platform(url)
    if not platform:
        raise HTTPException(status_code=400, detail="Unsupported platform URL")
    
    # Download the content (images, videos, all media types)
    success, message, file_path = download_x_content(url)
    
    if not success or not file_path:
        raise HTTPException(status_code=500, detail=f"Download failed: {message}")
    
    # If user is premium and authenticated, save to their gallery
    if auth_info.get("is_premium") and auth_info.get("user_id"):
        try:
            save_download(
                user_id=auth_info["user_id"],
                source_url=url,
                platform=platform or "x",
                post_id=post_id,
                title=post.get("text", "")[:100] if post.get("text") else None,
                file_path=str(file_path),
                is_user_submitted=False,
            )
        except Exception as e:
            # Don't fail the download if saving to gallery fails
            print(f"[DOWNLOAD] Failed to save to gallery: {e}", flush=True)
    
    # Return the file
    import mimetypes
    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"'
        }
    )


@app.post("/api/admin/premium/add")
async def add_premium_access(request: Request, auth_info: dict = Depends(verify_auth)):
    """
    Admin endpoint to grant premium access to a user.
    
    POST with JSON: {"email": "user@example.com", "expires_at": "2026-12-31T23:59:59"}
    
    Security: Should be protected by admin-only auth in production.
    """
    try:
        data = await request.json()
        email = data.get("email", "").strip()
        expires_at = data.get("expires_at")  # Optional ISO datetime string
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        success = add_premium_user(email, expires_at=expires_at)
        
        if success:
            return {
                "status": "success",
                "message": f"Premium access granted to {email}",
                "expires_at": expires_at or "never"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add premium user")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/export-db")
async def export_database(
    request: Request,
    secret: Optional[str] = Query(None, alias="secret"),
):
    """
    Stream the database file to the client (e.g. for syncing Render DB to local).
    Requires EXPORT_SECRET in env; pass ?secret=... or header X-Export-Secret.
    """
    export_secret = os.getenv("EXPORT_SECRET", "").strip()
    if not export_secret:
        raise HTTPException(status_code=503, detail="Export not configured")
    provided = (secret or request.headers.get("X-Export-Secret") or "").strip()
    if not secrets.compare_digest(provided, export_secret):
        raise HTTPException(status_code=403, detail="Invalid or missing export secret")
    db_path = Path(_DB_PATH)
    if not db_path.is_file():
        raise HTTPException(status_code=404, detail="Database file not found")
    return FileResponse(
        path=str(db_path),
        media_type="application/x-sqlite3",
        filename=db_path.name,
        headers={"Content-Disposition": f'attachment; filename="{db_path.name}"'},
    )


# ============================================================================
# Authentication Routes (Magic Link)
# ============================================================================

@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request, auth_info: dict = Depends(verify_auth)):
    """Render the login page."""
    if auth_info.get("authenticated") and auth_info.get("email"):
        # Already logged in, redirect to home
        return RedirectResponse(url="/", status_code=302)
    
    error_param = request.query_params.get("error")
    error_message = {
        "x_auth_failed": "X sign-in failed. Please try again or use email.",
        "x_not_configured": "X sign-in is not configured.",
        "x_create_failed": "Could not create account. Please try again.",
    }.get(error_param, error_param or "")
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "umami_website_id": UMAMI_WEBSITE_ID,
            "umami_script_url": UMAMI_SCRIPT_URL,
            "x_login_enabled": _oauth is not None,
            "error": error_message,
        }
    )


@app.post("/auth/magic-link")
async def send_magic_link_route(request: Request):
    """Send a magic link to the provided email."""
    try:
        data = await request.json()
        email = data.get("email", "").strip().lower()
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Basic email validation
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Generate magic link
        token, magic_link_url = generate_magic_link(email)
        
        # Send email (will log to console if Resend fails or domain not verified)
        sent = await send_magic_link_email(email, magic_link_url)
        
        # Always return success - in dev mode or if email fails, 
        # the link is logged to console for testing
        return {"status": "success", "message": "Magic link sent to your email"}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/verify/{token}")
async def verify_magic_link_route(token: str, request: Request):
    """Verify magic link token and create session."""
    # Normalize token (strip in case of encoding/whitespace)
    token = (token or "").strip()
    user = verify_magic_link(token)
    
    if not user:
        # Log reason for debugging (e.g. link points to wrong server if APP_BASE_URL mismatch)
        from app.db import get_magic_link
        link = get_magic_link(token) if token else None
        if not link:
            print(f"[AUTH] Magic link failed: token not found (wrong server or bad link?). APP_BASE_URL should match where you open the link.", flush=True)
        elif link.get("used"):
            print(f"[AUTH] Magic link failed: already used.", flush=True)
        else:
            print(f"[AUTH] Magic link failed: expired or invalid.", flush=True)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "This link has expired or is invalid. Please request a new one.",
                "umami_website_id": UMAMI_WEBSITE_ID,
                "umami_script_url": UMAMI_SCRIPT_URL,
                "x_login_enabled": _oauth is not None,
            }
        )
    
    # Create session token
    session_token = create_session_token(user["id"], user["email"])
    
    # Redirect to home with session cookie
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        path="/",
        httponly=True,
        secure=os.getenv("RENDER") is not None,  # Secure in production
        samesite="lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
    )
    
    return response


@app.get("/auth/logout")
async def logout():
    """Clear session and redirect to home. Cookie options must match set_cookie for browser to clear it (e.g. on Render with HTTPS)."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=os.getenv("RENDER") is not None,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/auth/x/login")
async def x_login(request: Request):
    """Initiate X (Twitter) OAuth login."""
    if not _oauth:
        raise HTTPException(
            status_code=503,
            detail="X login is not configured (set X_CLIENT_ID and X_CLIENT_SECRET)",
        )
    redirect_uri = os.getenv("X_REDIRECT_URI", "http://localhost:8000/auth/x/callback")
    return await _oauth.twitter.authorize_redirect(request, redirect_uri)


@app.get("/auth/x/callback")
async def x_callback(request: Request):
    """Handle X OAuth callback: create or get user, set session, redirect home."""
    if not _oauth:
        return RedirectResponse(url="/login?error=x_not_configured", status_code=302)
    try:
        token = await _oauth.twitter.authorize_access_token(request)
        resp = await _oauth.twitter.get(
            "https://api.twitter.com/2/users/me",
            params={"user.fields": "profile_image_url,username"},
        )
        user_info = resp.json()
        data = user_info.get("data") or {}
        x_user_id = data.get("id")
        x_handle = (data.get("username") or "user").strip()
        x_avatar = data.get("profile_image_url")

        user = get_user_by_twitter_id(x_user_id)
        if not user:
            email = f"{x_handle}@x.temp"
            user = create_or_get_user(email)
            if not user:
                return RedirectResponse(url="/login?error=x_create_failed", status_code=302)
            update_user_nickname(user["id"], f"@{x_handle}")
        save_twitter_connection(
            user_id=user["id"],
            twitter_id=x_user_id,
            twitter_handle=x_handle,
            twitter_avatar=x_avatar,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
        )

        session_token = create_session_token(user["id"], user["email"])
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            path="/",
            httponly=True,
            secure=os.getenv("RENDER") is not None,
            samesite="lax",
            max_age=30 * 24 * 60 * 60,
        )
        return response
    except Exception as e:
        print(f"[X AUTH ERROR] {e}", flush=True)
        return RedirectResponse(url="/login?error=x_auth_failed", status_code=302)


# ============================================================================
# Stripe Routes
# ============================================================================

@app.get("/api/stripe/checkout")
async def stripe_checkout(auth_info: dict = Depends(verify_auth)):
    """Create a Stripe checkout session for premium subscription."""
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(
            status_code=401,
            detail="Please log in first to subscribe"
        )
    
    if auth_info.get("is_premium"):
        raise HTTPException(
            status_code=400,
            detail="You already have premium access"
        )
    
    user_email = auth_info["email"]
    user_id = auth_info.get("user_id")
    
    if not user_id:
        # Ensure user exists in database
        user = create_or_get_user(user_email)
        user_id = user["id"] if user else None
    
    if not user_id:
        raise HTTPException(status_code=500, detail="Failed to create user")
    
    checkout_url = create_checkout_session(user_email, user_id)
    
    if checkout_url:
        return RedirectResponse(url=checkout_url, status_code=302)
    else:
        raise HTTPException(
            status_code=503,
            detail="Payment service temporarily unavailable"
        )


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    
    result = handle_webhook(payload, sig_header)
    
    if result.get("success"):
        return {"status": "success", "message": result.get("message")}
    else:
        raise HTTPException(status_code=400, detail=result.get("message"))


@app.get("/api/stripe/portal")
async def stripe_portal(auth_info: dict = Depends(verify_auth)):
    """Redirect to Stripe customer portal for subscription management."""
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    user = get_user_by_email(auth_info["email"])
    if not user or not user.get("stripe_customer_id"):
        raise HTTPException(
            status_code=400,
            detail="No subscription found"
        )
    
    portal_url = create_portal_session(user["stripe_customer_id"])
    
    if portal_url:
        return RedirectResponse(url=portal_url, status_code=302)
    else:
        raise HTTPException(
            status_code=503,
            detail="Portal service temporarily unavailable"
        )


@app.get("/api/subscription/status")
async def subscription_status(auth_info: dict = Depends(verify_auth)):
    """Get current user's subscription status."""
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        return {"is_premium": False, "has_subscription": False}
    
    return get_subscription_status(auth_info["email"])


# ============================================================================
# Downloads Page and API
# ============================================================================

@app.get("/downloads", response_class=HTMLResponse)
async def downloads_page(request: Request, auth_info: dict = Depends(verify_auth)):
    """Render the public downloads gallery page."""
    import time
    downloads = get_all_downloads(limit=50)
    total = get_download_count()
    for d in downloads:
        if d.get("file_path") and d.get("platform") == "upload":
            d["view_url"] = f"/api/downloads/{d['id']}/file"
        else:
            d["view_url"] = None
    return templates.TemplateResponse(
        request=request,
        name="downloads.html",
        context={
            "downloads": downloads,
            "total_downloads": total,
            "is_authenticated": auth_info.get("authenticated", False),
            "is_premium": auth_info.get("is_premium", False),
            "user_email": auth_info.get("email"),
            "user_nickname": auth_info.get("nickname"),
            "subscription_price": SUBSCRIPTION_PRICE_EUR,
            "umami_website_id": UMAMI_WEBSITE_ID,
            "umami_script_url": UMAMI_SCRIPT_URL,
            "cache_bust": int(time.time()),
        }
    )


@app.get("/api/downloads")
async def api_downloads(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    platform: str | None = None,
):
    """JSON API for downloads gallery."""
    downloads = get_all_downloads(limit=limit, offset=offset, platform=platform)
    total = get_download_count(platform=platform)
    # Add view_url for uploads (local file) so frontend can show/embed them
    for d in downloads:
        if d.get("file_path") and d.get("platform") == "upload":
            d["view_url"] = f"/api/downloads/{d['id']}/file"
        else:
            d["view_url"] = None
    return {
        "downloads": downloads,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/downloads/{download_id}/file")
async def serve_download_file(download_id: int):
    """Serve the file for a download (e.g. user uploads). Public so gallery can display."""
    download = get_download_by_id(download_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download not found")
    file_path = download.get("file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail="No file for this download")
    path = Path(file_path).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    upload_root = UPLOAD_DIR.resolve()
    if upload_root not in path.parents:
        raise HTTPException(status_code=403, detail="Invalid file")
    import mimetypes
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=path.name,
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


# ============================================================================
# User Content Submission
# ============================================================================

def _detect_platform(url: str) -> Optional[str]:
    """Detect platform from URL."""
    url_lower = url.lower()
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "x"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "tiktok.com" in url_lower:
        return "tiktok"
    elif "instagram.com" in url_lower:
        return "instagram"
    return None


# Directory for user-uploaded files (create if missing)
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


@app.post("/api/uploads/submit")
async def submit_url(request: Request, auth_info: dict = Depends(verify_auth)):
    """
    Premium users can submit URLs for content to be downloaded and added to gallery.
    
    POST with JSON: {"url": "https://x.com/user/status/123", "title": "Optional title"}
    
    Supports: X/Twitter, YouTube, TikTok, Instagram
    """
    # Check authentication
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    # Check premium status
    if not auth_info.get("is_premium"):
        raise HTTPException(
            status_code=403,
            detail="Uploading content requires premium membership"
        )
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    try:
        data = await request.json()
        url = data.get("url", "").strip()
        title = data.get("title", "").strip()[:200]
        description = (data.get("description") or "").strip()[:2000]
        links = (data.get("links") or "").strip()
        link_lines = [ln.strip() for ln in links.splitlines() if ln.strip()]
        related_links_str = "\n".join(link_lines[1:]) if len(link_lines) > 1 else None
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL format")
        
        # Detect platform
        platform = _detect_platform(url)
        if not platform:
            raise HTTPException(
                status_code=400,
                detail="Supported platforms: X/Twitter, YouTube, TikTok, Instagram"
            )
        
        # Check yt-dlp availability
        if not check_yt_dlp_available():
            raise HTTPException(
                status_code=503,
                detail="Download service temporarily unavailable"
            )
        
        # Download the content (works for all platforms via yt-dlp)
        success, message, file_path = download_x_content(url)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Download failed: {message}")
        
        # Save to downloads table
        download_id = save_download(
            user_id=user_id,
            source_url=url,
            platform=platform,
            title=title or None,
            file_path=str(file_path) if file_path else None,
            is_user_submitted=True,
            description=description or None,
            related_links=related_links_str,
        )
        
        if not download_id:
            raise HTTPException(status_code=500, detail="Failed to save download")
        
        return {
            "status": "success",
            "message": "Content downloaded and added to gallery",
            "download_id": download_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"[UPLOAD ERROR] {error_detail}", flush=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# Allowed extensions for direct file uploads
UPLOAD_ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mov", ".webm", ".mkv", ".avi",
}


@app.post("/api/uploads/file")
async def submit_file_upload(
    request: Request,
    auth_info: dict = Depends(verify_auth),
    file: Optional[UploadFile] = File(None),
    files: Optional[list[UploadFile]] = File(None),
    title: Optional[str] = Form(""),
    description: Optional[str] = Form(""),
    links: Optional[str] = Form(""),
):
    """
    Premium users can upload files directly (drag-and-drop), with title, description, and links.
    Send as multipart/form-data: file (or files), title, description, links (one per line).
    """
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(status_code=401, detail="Please log in first")
    if not auth_info.get("is_premium"):
        raise HTTPException(status_code=403, detail="Uploading requires premium membership")

    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")

    # Collect all files (support both single "file" and multiple "files")
    to_upload: list[UploadFile] = []
    if file and file.filename:
        to_upload.append(file)
    if files:
        to_upload.extend(f for f in files if f and f.filename)

    if not to_upload:
        raise HTTPException(status_code=400, detail="At least one file is required")

    # Parse links: first line = source_url, rest = related_links (newline-separated)
    links_stripped = (links or "").strip()
    link_lines = [ln.strip() for ln in links_stripped.splitlines() if ln.strip()]
    source_url = link_lines[0] if link_lines else ""
    related_links_str = "\n".join(link_lines[1:]) if len(link_lines) > 1 else None
    title_clean = (title or "").strip()[:200] or None
    description_clean = (description or "").strip()[:2000] or None

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    import time
    saved_paths: list[Path] = []

    for uf in to_upload:
        ext = Path(uf.filename or "").suffix.lower()
        if ext not in UPLOAD_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed: {uf.filename}. Allowed: images and video (e.g. jpg, png, mp4, webm)."
            )
        # Safe filename: user_id_timestamp_random_original
        safe_name = f"{user_id}_{int(time.time() * 1000)}_{secrets.token_hex(4)}{ext}"
        dest = UPLOAD_DIR / safe_name
        try:
            content = await uf.read()
            if len(content) > 100 * 1024 * 1024:  # 100 MB
                raise HTTPException(status_code=400, detail="File too large (max 100 MB per file)")
            dest.write_bytes(content)
            saved_paths.append(dest)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    created = 0
    for fp in saved_paths:
        download_id = save_download(
            user_id=user_id,
            source_url=source_url,
            platform="upload",
            title=title_clean,
            file_path=str(fp),
            is_user_submitted=True,
            description=description_clean,
            related_links=related_links_str,
        )
        if download_id:
            created += 1

    return {
        "status": "success",
        "message": f"{created} file(s) added to gallery",
        "count": created,
    }


# ============================================================================
# User Profile
# ============================================================================

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, auth_info: dict = Depends(verify_auth)):
    """Render the user profile page."""
    import time
    from datetime import datetime
    
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        return RedirectResponse(url="/auth/login", status_code=302)
    
    user_id = auth_info.get("user_id")
    user = get_user_by_id(user_id) if user_id else None
    
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    
    # Get user stats
    stats = get_user_stats(user_id)
    
    # Get user's posts and downloads
    user_posts = get_user_posts_by_user(user_id, limit=50)
    user_downloads = get_user_downloads(user_id, limit=50)
    
    # Format member since date
    created_at = user.get("created_at")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            member_since = dt.strftime("%B %Y")
        except:
            member_since = "Unknown"
    else:
        member_since = "Unknown"
    
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "is_authenticated": True,
            "is_premium": auth_info.get("is_premium", False),
            "user_email": auth_info.get("email"),
            "user_nickname": user.get("nickname"),
            "user_bio": user.get("bio"),
            "user_posts": user_posts,
            "user_downloads": user_downloads,
            "stats": stats,
            "member_since": member_since,
            "subscription_price": SUBSCRIPTION_PRICE_EUR,
            "umami_website_id": UMAMI_WEBSITE_ID,
            "umami_script_url": UMAMI_SCRIPT_URL,
            "cache_bust": int(time.time()),
        }
    )


@app.post("/api/user/nickname")
async def update_nickname(request: Request, auth_info: dict = Depends(verify_auth)):
    """Update the current user's nickname (premium only)."""
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    if not auth_info.get("is_premium"):
        raise HTTPException(
            status_code=403,
            detail="Nicknames are a premium feature"
        )
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    try:
        data = await request.json()
        nickname = data.get("nickname", "").strip()
        
        if not nickname:
            raise HTTPException(status_code=400, detail="Nickname is required")
        
        if len(nickname) > 50:
            raise HTTPException(status_code=400, detail="Nickname too long (max 50 characters)")
        
        # Basic sanitization - alphanumeric, spaces, underscores, hyphens
        if not re.match(r"^[\w\s\-]+$", nickname):
            raise HTTPException(
                status_code=400,
                detail="Nickname can only contain letters, numbers, spaces, underscores, and hyphens"
            )
        
        success = update_user_nickname(user_id, nickname)
        
        if success:
            return {"status": "success", "nickname": nickname}
        else:
            raise HTTPException(status_code=500, detail="Failed to update nickname")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/user/profile")
async def update_profile(request: Request, auth_info: dict = Depends(verify_auth)):
    """Update the current user's profile (nickname, bio)."""
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    try:
        data = await request.json()
        nickname = data.get("nickname", "").strip() if data.get("nickname") else None
        bio = data.get("bio", "").strip() if data.get("bio") else None
        
        # Validate nickname if provided
        if nickname:
            if len(nickname) > 50:
                raise HTTPException(status_code=400, detail="Nickname too long (max 50 characters)")
            if not re.match(r"^[\w\s\-]+$", nickname):
                raise HTTPException(
                    status_code=400,
                    detail="Nickname can only contain letters, numbers, spaces, underscores, and hyphens"
                )
        
        # Validate bio if provided
        if bio and len(bio) > 500:
            raise HTTPException(status_code=400, detail="Bio too long (max 500 characters)")
        
        success = update_user_profile(user_id, nickname=nickname, bio=bio)
        
        if success:
            return {"status": "success", "nickname": nickname, "bio": bio}
        else:
            raise HTTPException(status_code=500, detail="Failed to update profile")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/posts")
async def get_my_posts(auth_info: dict = Depends(verify_auth)):
    """Get the current user's posts."""
    if not auth_info.get("authenticated"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    posts = get_user_posts_by_user(user_id, limit=50)
    return {"posts": posts}


@app.get("/api/user/downloads")
async def get_my_downloads(auth_info: dict = Depends(verify_auth)):
    """Get the current user's downloads (private)."""
    if not auth_info.get("authenticated"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    downloads = get_user_downloads(user_id, limit=50)
    return {"downloads": downloads}


# ============================================================================
# V2: Community Posts API
# ============================================================================

@app.post("/api/posts/create")
async def create_community_post(request: Request, auth_info: dict = Depends(verify_auth)):
    """Create a new community post (premium only)."""
    if not auth_info.get("authenticated") or not auth_info.get("email"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    if not auth_info.get("is_premium"):
        raise HTTPException(
            status_code=403,
            detail="Posting requires premium membership"
        )
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    try:
        data = await request.json()
        content = data.get("content", "").strip()
        media_urls = data.get("media_urls")  # Optional JSON array
        
        if not content:
            raise HTTPException(status_code=400, detail="Content is required")
        
        if len(content) > 2000:
            raise HTTPException(status_code=400, detail="Content too long (max 2000 characters)")
        
        # Serialize media_urls if provided
        media_json = None
        if media_urls:
            import json
            if isinstance(media_urls, list):
                media_json = json.dumps(media_urls[:10])  # Limit to 10 URLs
        
        post_id = create_user_post(user_id, content, media_json)
        
        if post_id:
            return {"status": "success", "post_id": post_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to create post")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/posts/{post_id}")
async def delete_community_post(post_id: int, auth_info: dict = Depends(verify_auth)):
    """Delete a user's own community post."""
    if not auth_info.get("authenticated"):
        raise HTTPException(status_code=401, detail="Please log in first")
    
    user_id = auth_info.get("user_id")
    if not user_id:
        raise HTTPException(status_code=500, detail="User session invalid")
    
    success = delete_user_post(post_id, user_id)
    
    if success:
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Post not found or not authorized")


@app.get("/api/posts/community")
async def get_community_feed(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Get community posts feed."""
    posts = get_community_posts(limit=limit, offset=offset)
    total = get_community_post_count()
    return {"posts": posts, "total": total}


@app.post("/api/posts/community/{post_id}/like")
async def like_community_post(post_id: int, auth_info: dict = Depends(verify_auth)):
    """Like a community post."""
    new_count = like_user_post(post_id)
    return {"post_id": post_id, "like_count": new_count}


@app.post("/api/posts/community/{post_id}/unlike")
async def unlike_community_post(post_id: int, auth_info: dict = Depends(verify_auth)):
    """Unlike a community post."""
    new_count = unlike_user_post(post_id)
    return {"post_id": post_id, "like_count": new_count}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
