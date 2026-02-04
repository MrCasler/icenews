# Pre-M3 Deployment Checklist

All items completed before moving to M3 (deployment).

## ✅ Deprecation Warnings Fixed

### 1. Pydantic ConfigDict Warning
**Before:**
```python
class PostOut(BaseModel):
    # ... fields ...
    class Config:
        from_attributes = True  # Deprecated
```

**After:**
```python
class PostOut(BaseModel):
    model_config = {"from_attributes": True}  # Modern syntax
    # ... fields ...
```

**File:** `app/models.py`

### 2. FastAPI on_event Deprecation
**Before:**
```python
@app.on_event("startup")
async def startup_event():
    init_db()
```

**After:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown (if needed)

app = FastAPI(lifespan=lifespan)
```

**File:** `app/main.py`

### 3. Starlette TemplateResponse Parameter Order
**Before:**
```python
return templates.TemplateResponse(
    "index.html",
    {"request": request, ...}
)
```

**After:**
```python
return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={...}
)
```

**File:** `app/main.py`

## ✅ Self-Hosted Umami Setup

### render.yaml Created

Based on your `realorslop.fun` setup, created `render.yaml` with:

1. **ICENews service** (Python/FastAPI)
   - Automatic deployment from GitHub
   - Environment variables for Scrapfly, auth, Umami
   - Free tier compatible

2. **Umami service** (Docker)
   - Self-hosted analytics (no cloud.umami.is)
   - Privacy-friendly, no cookies
   - PostgreSQL database included

3. **PostgreSQL database**
   - Stores Umami analytics data
   - Free tier (limited storage)
   - Auto-configured via Render

### .env Updated

```bash
# Old (cloud-based):
UMAMI_SCRIPT_URL=https://cloud.umami.is/script.js

# New (self-hosted):
UMAMI_SCRIPT_URL=https://icenews-umami.onrender.com/script.js
```

Leave empty to disable analytics entirely.

## ✅ Test Results

All deprecation warnings eliminated:

```
======================== 51 passed, 10 skipped in 0.24s ========================
```

No warnings shown (previously had 8-11 warnings).

## Files Modified

1. **app/models.py** - Updated Pydantic config to modern syntax
2. **app/main.py** - Migrated to lifespan context manager, fixed TemplateResponse
3. **.env** - Updated Umami config comments for self-hosting

## Files Created

1. **render.yaml** - Render.com deployment configuration
2. **RENDER_DEPLOYMENT.md** - Complete deployment guide

## What Changed vs realorslop.fun

### Similarities:
- ✅ render.yaml structure (services + database)
- ✅ Self-hosted Umami with PostgreSQL
- ✅ Free tier compatible
- ✅ Auto-generated HASH_SALT

### Differences:
- ❌ No Tailwind build step (ICENews uses CDN Tailwind)
- ✅ Added basic auth environment variables
- ✅ Added Scrapfly API key variables
- ✅ Simplified build command (just pip install)

## Ready for M3 Deployment

You can now deploy to Render.com:

### Option 1: Via Blueprint (Recommended)
1. Push code to GitHub
2. Go to Render → New Blueprint
3. Connect GitHub repo
4. Render auto-detects `render.yaml`
5. Click "Apply"

### Option 2: Manual Setup
Follow the step-by-step guide in `RENDER_DEPLOYMENT.md`

## Post-Deployment Tasks

After deploying:

1. **Change Umami password** (default is admin/umami)
2. **Create website in Umami** and get Website ID
3. **Set UMAMI_WEBSITE_ID** in icenews service
4. **Import accounts** for monitoring
5. **Run first ingestion** to populate posts
6. **Enable password gate** if needed (set auth env vars)
7. **Set up external monitoring** (UptimeRobot for /health)

## Migration from Umami Cloud (if needed)

If you were using cloud.umami.is:

1. Export data from Umami Cloud (if any)
2. Update `UMAMI_SCRIPT_URL` in .env
3. Update `UMAMI_WEBSITE_ID` (new ID from self-hosted instance)
4. Restart service
5. Verify events are being tracked in your self-hosted Umami

## Cost Comparison

**Before (Umami Cloud):**
- Free tier: 100k events/month
- Paid: $9/month for 1M events
- Data stored on third-party servers

**After (Self-hosted on Render):**
- Free tier: Unlimited events (within resource limits)
- No monthly fee for analytics
- Full data ownership

## Notes

- SQLite database is ephemeral on Render free tier (consider PostgreSQL for production)
- Services sleep after 15 minutes on free tier (upgrade for 24/7 uptime)
- Umami PostgreSQL database is persistent (included in free tier)
- Self-hosted Umami gives you full control and privacy

## Verification

Run tests to confirm everything still works:

```bash
./run_tests.sh
```

Expected: 51 passed, 10 skipped, **0 warnings**

## Next Step: M3 Deployment

Follow `RENDER_DEPLOYMENT.md` for complete deployment instructions.
