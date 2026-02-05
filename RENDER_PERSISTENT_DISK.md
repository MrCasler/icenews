# Render Database Persistence (Free Tier)

## Problem
The database was being stored in `/tmp/` which is **ephemeral** and gets wiped on every restart. This is why you had to run `import_data.py` every time.

## Solution (Free Tier Compatible)
Use Render's **project source directory** (`/opt/render/project/src/`) which persists across restarts even on the free tier. Persistent disks are only available on paid plans, but the source directory works perfectly for SQLite databases.

## Setup Steps (Free Tier - No Disk Required!)

### Automatic Setup via render.yaml

The solution is already configured in `render.yaml` and `app/db.py`. No manual setup needed!

**How it works:**

1. Render deploys your code to `/opt/render/project/src/`
2. This directory **persists between restarts** (but not between re-deploys from scratch)
3. Database is stored at `/opt/render/project/src/icenews_social.db`
4. Data survives service restarts and sleeps (free tier auto-sleep)

**To apply:**

1. Commit and push the updated `render.yaml` and `app/db.py` files
2. Render will automatically deploy
3. Run `import_data.py` once to populate the database
4. Done! Data now persists across restarts

## After Setup: Import Your Data

Once deployed:

1. Deploy the updated code (with the new DB_PATH)
2. Run the import script **one final time**:
   ```bash
   python import_data.py database_export.sql
   ```
3. Your data will now persist across restarts!

**Important Note:** Data persists across:
- ✅ Service restarts
- ✅ Free tier auto-sleep/wake cycles
- ❌ Manual re-deploys from scratch (need to re-import)

If you need persistence across re-deploys, consider:
- Upgrading to a paid plan with persistent disks ($7/month)
- Using PostgreSQL (Render's free PostgreSQL tier)
- Using an external DB service

## Verify It Works

To verify the database is using the persistent disk:

1. Check your deployed app works: https://icenews.eu
2. Trigger a manual restart in Render dashboard
3. Visit the site again - your data should still be there!
4. Check Render logs: you should NOT see any database initialization messages after restart

## Database Path Summary

- **Local development**: `./icenews_social.db` (in project root)
- **Render free tier**: `/opt/render/project/src/icenews_social.db` (project directory)

## Important Notes

- **Free tier**: No persistent disk needed! Uses project source directory
- **Limitation**: Data persists across restarts but NOT across fresh deploys
- **Backups**: Consider periodic database exports for safety
- **Upgrade option**: For full persistence, upgrade to paid plan ($7/month) with persistent disks

## Cost

- **Free tier**: $0 (uses project directory, no disk charges)
- **Paid tier with persistent disk**: $7/month base + $0.25/GB for additional storage

## Troubleshooting

### Database still empty after restart?

1. Check Render logs to confirm it's using `/opt/render/project/src/icenews_social.db`
2. Verify the file exists: `ls -la /opt/render/project/src/*.db` (via Render shell)
3. Make sure you imported data after deploying the updated code
4. If you did a fresh deploy (not just restart), you need to re-import

### Permission errors?

The project source directory should be writable by default. If you get permission errors:
```bash
# In Render shell:
ls -la /opt/render/project/src/
chmod 644 /opt/render/project/src/icenews_social.db
```

### Want to check database contents?

Use the Render shell:
```bash
# In Render dashboard → Shell tab
sqlite3 /opt/render/project/src/icenews_social.db "SELECT COUNT(*) FROM posts;"
```
