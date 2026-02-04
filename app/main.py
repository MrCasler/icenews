"""ICENews web app: FastAPI + Jinja2 + Alpine.js + TailwindCSS."""
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_accounts, get_connection, get_post_by_post_id, get_post_count, get_posts, init_db, like_post, unlike_post
from app.models import AccountOut, LikeUpdateOut, PostListResponse, PostOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: Initialize the database schema
    init_db()
    yield
    # Shutdown: nothing to do currently


app = FastAPI(
    title="ICENews",
    description="Social monitoring for government & independent sources",
    lifespan=lifespan
)
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
) -> bool:
    """
    Verify HTTP Basic Auth credentials.
    
    If AUTH_ENABLED is False (no credentials in .env), this always returns True.
    If AUTH_ENABLED is True, verifies the provided credentials match .env values.
    
    Security notes:
    - Uses secrets.compare_digest to prevent timing attacks
    - Only checks credentials if auth is explicitly enabled
    - /health endpoint should bypass this dependency
    """
    if not AUTH_ENABLED:
        return True
    
    # Auth is enabled, so we need to check credentials
    # Extract credentials from Authorization header
    from fastapi.security.utils import get_authorization_scheme_param
    
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    scheme, credentials_str = get_authorization_scheme_param(authorization)
    if scheme.lower() != "basic":
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # Decode base64 credentials
    import base64
    try:
        decoded = base64.b64decode(credentials_str).decode("utf-8")
        username, _, password = decoded.partition(":")
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials format",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # Compare email (username) and password
    correct_username = secrets.compare_digest(username, AUTH_EMAIL)
    correct_password = secrets.compare_digest(password, AUTH_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


def _posts_to_json(posts: list) -> str:
    """Serialize posts for safe JSON in HTML (no XSS)."""
    import json
    return json.dumps(posts).replace("<", "\\u003c").replace(">", "\\u003e")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, authenticated: bool = Depends(verify_auth)):
    """Homepage: dashboard with recent posts."""
    import time
    posts = get_posts(limit=50)
    total = get_post_count()
    accounts = get_accounts()
    posts_json = _posts_to_json(posts)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "posts": posts,
            "posts_json": posts_json,
            "total_posts": total,
            "accounts": accounts,
            # Umami analytics (empty string = disabled in template)
            "umami_website_id": UMAMI_WEBSITE_ID,
            "umami_script_url": UMAMI_SCRIPT_URL,
            # Cache-busting for static assets during development
            "cache_bust": int(time.time()),
        },
    )


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
    authenticated: bool = Depends(verify_auth),
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
async def api_accounts(authenticated: bool = Depends(verify_auth)):
    """JSON API for accounts."""
    accounts = get_accounts()
    return [AccountOut(**a) for a in accounts]


@app.post("/api/posts/{post_id}/like", response_model=LikeUpdateOut)
async def api_like_post(post_id: str, authenticated: bool = Depends(verify_auth)):
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
async def api_unlike_post(post_id: str, authenticated: bool = Depends(verify_auth)):
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
