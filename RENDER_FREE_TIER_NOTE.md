# Render Free Tier - Database Persistence

## Good News! 🎉

The solution works perfectly on **Render's free tier** - no paid features needed!

**Important:** Uses **native Python runtime** (not Docker) for better persistence on free tier.

## How It Works

### The Problem:
- `/tmp/` gets wiped on every restart (ephemeral storage)
- Persistent disks require paid plan ($7/month+)

### The Solution (Free Tier):
- Use `/opt/render/project/src/` (your project directory)
- This directory **persists across restarts** even on free tier
- Perfect for SQLite databases

### What Persists:
✅ Service restarts (manual or automatic)
✅ Free tier auto-sleep/wake cycles (after 15 min inactivity)
✅ Error crashes and recoveries

### What Doesn't Persist:
❌ Fresh deploys from dashboard (new build)
❌ Deleting and recreating the service

## Practical Impact

### For Normal Use (Restarts):
Your database **WILL persist**! You won't need to run `import_data.py` every time.

### For Fresh Deploys:
If you trigger a fresh deploy (rebuild), you'll need to re-import data once. This is rare - usually only when:
- You manually trigger "Clear build cache & deploy"
- You delete and recreate the service
- Major infrastructure changes

### Regular code updates (git push):
✅ Database persists! Just normal hot-reload, data stays.

## Setup (Already Done!)

The code is already configured for free tier:

```python
# app/db.py
if os.getenv("RENDER"):
    DB_PATH = Path("/opt/render/project/src/icenews_social.db")
```

No dashboard configuration needed. Just deploy and import data once!

## Cost Comparison

### Current Solution (Free Tier):
- **Cost**: $0
- **Storage**: Limited by service disk (10GB on free tier)
- **Persistence**: Across restarts (not fresh deploys)
- **Perfect for**: Development, small projects, proof of concept

### Upgrade to Paid Plan:
- **Cost**: $7/month + $0.25/GB storage
- **Storage**: Configurable (1GB+)
- **Persistence**: Across everything (even fresh deploys)
- **Perfect for**: Production apps with frequent deploys

## Recommendation

**Start with free tier** (current solution):
1. Deploy the updated code
2. Import data once
3. Use normally
4. Database persists across restarts

**Upgrade later** if needed:
- Only if you do frequent fresh deploys
- Or need guaranteed persistence for production
- Or need more than 10GB storage

## Deployment Steps (Free Tier)

```bash
# 1. Commit and push
git add .
git commit -m "Fix database persistence (free tier compatible)"
git push

# 2. Render auto-deploys

# 3. Import data once
python import_data.py database_export.sql

# 4. Done! ✅
# - Data persists across restarts
# - No monthly fees
# - Perfect for your use case
```

## When to Upgrade

Consider upgrading to paid tier if:
- You deploy fresh builds multiple times per day
- You need 100% guarantee of persistence
- Your database exceeds 10GB
- You're running a production business

Otherwise, **free tier is perfect** for your needs!

---

**Bottom line:** The free tier solution works great. Your database will persist across normal restarts and wake-from-sleep cycles. You only need to re-import if you do a complete fresh deploy, which is rare.
