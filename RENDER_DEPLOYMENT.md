# ICENews Deployment on Render.com

This guide walks you through deploying ICENews on Render.com with self-hosted Umami analytics.

## Overview

The `render.yaml` file defines two services:
1. **icenews** - The main FastAPI web app
2. **icenews-umami** - Self-hosted Umami analytics (privacy-friendly, no cookies)

## Why Self-Host Umami?

- **Privacy**: Your analytics data stays on your infrastructure
- **No third-party tracking**: Unlike cloud.umami.is or Google Analytics
- **Full control**: Customize, export data, no vendor lock-in
- **Free**: Runs on Render's free tier

## Prerequisites

1. GitHub account (to push your code)
2. Render.com account (free tier is fine)
3. Scrapfly API keys (for X/Twitter ingestion)

## Step 1: Push Code to GitHub

```bash
cd /Users/casler/Desktop/casler\ biz/personal\ projects/icenews

# Initialize git if not already done
git init
git add .
git commit -m "Initial ICENews deployment"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/icenews.git
git push -u origin main
```

## Step 2: Deploy to Render

### Option A: Deploy via Dashboard (Recommended for first time)

1. Go to https://render.com/
2. Click "New" → "Blueprint"
3. Connect your GitHub account
4. Select your `icenews` repository
5. Render will detect `render.yaml` automatically
6. Click "Apply"

Render will:
- Create the PostgreSQL database for Umami
- Deploy Umami (Docker container)
- Deploy ICENews (Python web service)
- Set up environment variables

### Option B: Deploy via render.yaml (Advanced)

Render automatically detects and deploys from `render.yaml` when you connect your repo.

## Step 3: Configure Environment Variables

After deployment, go to each service and set these environment variables:

### icenews Service

**Required:**
- `SCRAPFLY_KEY` - Your Scrapfly API key
- `SCRAPFLY_LIVE_KEY` - Same as SCRAPFLY_KEY
- `SCRAPFLY_TEST_KEY` - Your Scrapfly test key

**Optional (for password gate):**
- `ICENEWS_AUTH_EMAIL` - Email for basic auth (leave empty to disable)
- `ICENEWS_AUTH_PASSWORD` - Password for basic auth (leave empty to disable)

**Optional (for analytics):**
- `UMAMI_WEBSITE_ID` - Get this after setting up Umami (see Step 4)
- `UMAMI_SCRIPT_URL` - Auto-set to `https://icenews-umami.onrender.com/script.js`

### icenews-umami Service

These are auto-configured by Render:
- `DATABASE_TYPE` - Set to `postgresql`
- `DATABASE_URL` - Auto-generated from database connection
- `HASH_SALT` - Auto-generated random string

## Step 4: Set Up Umami Analytics

1. **Access Umami dashboard:**
   - Go to `https://icenews-umami.onrender.com`
   - Default login: `admin` / `umami`
   - **Change the password immediately!**

2. **Create a website:**
   - Click "Add website"
   - Name: `ICENews`
   - Domain: Your ICENews URL (e.g., `icenews.onrender.com`)
   - Click "Save"

3. **Get the Website ID:**
   - Click on your website in the list
   - Look at the URL: `https://icenews-umami.onrender.com/websites/XXXXX`
   - `XXXXX` is your website ID

4. **Update ICENews environment variables:**
   - Go to your `icenews` service settings
   - Set `UMAMI_WEBSITE_ID` to the ID from step 3
   - Restart the service

## Step 5: Set Up Database

The SQLite database is created automatically on first run. However, you need to add accounts to monitor:

1. **SSH into your Render service:**
   - Go to your `icenews` service
   - Click "Shell" tab
   - Run:
     ```bash
     python -c "from app.db import get_connection; print('DB path:', get_connection())"
     ```

2. **Add accounts to monitor:**
   - Create a CSV file with accounts (see `app/ingest/import_accounts.py`)
   - Upload via Render dashboard or use the import script

**Alternative:** Import accounts locally, then upload the SQLite database file to Render's persistent disk.

## Step 6: Enable Scheduled Ingestion

Render doesn't support cron jobs on the free tier. Options:

### Option A: External Cron Job

Use a service like cron-job.org or EasyCron to hit an ingestion endpoint every 6 hours.

Add this endpoint to `app/main.py`:

```python
@app.post("/api/ingest/trigger")
async def trigger_ingestion(authenticated: bool = Depends(verify_auth)):
    """Trigger ingestion manually (for external cron)."""
    # Run ingestion in background
    import subprocess
    subprocess.Popen(["python", "-m", "app.ingest.ingest_x_scrapfly"])
    return {"status": "triggered"}
```

### Option B: Upgrade to Paid Plan

Render's paid plans support background workers and cron jobs.

### Option C: Local Scheduler

Run the scheduler locally and push results to production:

```bash
# Run locally every 6 hours
python -m app.scheduler
```

## Step 7: Custom Domain (Optional)

1. Go to your `icenews` service settings
2. Click "Custom Domain"
3. Add your domain (e.g., `icenews.yourdomain.com`)
4. Update your DNS:
   - Add CNAME record pointing to your Render URL
5. Render automatically provisions Let's Encrypt SSL

## Step 8: Enable Password Gate (Optional)

For pre-launch testing:

1. Go to `icenews` service settings
2. Add environment variables:
   - `ICENEWS_AUTH_EMAIL` = `your.email@example.com`
   - `ICENEWS_AUTH_PASSWORD` = `YourSecurePassword123`
3. Restart service

Share these credentials with trusted testers.

## Step 9: Monitor Health

Render provides built-in monitoring, but you can also:

1. **Set up external monitoring:**
   - Use UptimeRobot or Healthchecks.io
   - Monitor: `https://icenews.onrender.com/health`
   - Alert on consecutive failures

2. **Check logs:**
   - Go to your service dashboard
   - Click "Logs" tab
   - Filter by service (icenews or icenews-umami)

## Step 10: Backup Your Data

### SQLite Database (ICENews)

Render's free tier doesn't include persistent disk. Your SQLite database is stored in ephemeral disk and will be lost on service restarts.

**Solutions:**

1. **Use PostgreSQL instead** (recommended for production):
   - Add a PostgreSQL database in `render.yaml`
   - Update `app/db.py` to use PostgreSQL
   - Render's free tier includes persistent PostgreSQL

2. **Manual backups:**
   - Download SQLite file via Shell periodically
   - Store in S3, Backblaze B2, or similar

3. **Automated backups:**
   - Write a script to export SQLite to S3
   - Trigger via external cron

### Umami Database

The Umami PostgreSQL database is automatically backed up by Render (on paid plans) or can be exported manually.

## Troubleshooting

### Service Won't Start

- Check logs for errors
- Verify all environment variables are set
- Ensure `requirements.txt` includes all dependencies

### Umami Won't Load

- Check if `icenews-umami` service is running
- Verify `DATABASE_URL` is set correctly
- Check PostgreSQL database status

### Ingestion Not Working

- Verify Scrapfly API keys are set
- Check logs for rate limit errors
- Test locally first: `python -m app.ingest.ingest_x_scrapfly`

### "No posts yet" on homepage

- You need to add accounts and run ingestion
- Check `accounts` table has enabled accounts
- Run ingestion manually first to populate posts

## Cost Estimate

**Free Tier (Render):**
- icenews web service: Free (750 hours/month)
- icenews-umami web service: Free (750 hours/month)
- PostgreSQL database: Free (limited storage)
- **Total: $0/month**

**Limitations:**
- Services sleep after 15 minutes of inactivity
- Limited resources (512 MB RAM, shared CPU)
- No persistent disk for SQLite

**Paid Tier ($7/month per service):**
- No sleeping
- More resources (512 MB - 8 GB RAM)
- Persistent disk available
- Background workers & cron jobs

## Next Steps

After deployment:

1. ✅ Verify health check: `https://icenews.onrender.com/health`
2. ✅ Test auth (if enabled)
3. ✅ Import accounts
4. ✅ Run first ingestion
5. ✅ Check Umami dashboard for events
6. ✅ Set up external monitoring
7. ✅ Schedule backups

## Alternatives to Render

If you prefer other platforms:

- **Fly.io**: Similar to Render, better free tier
- **Railway**: Easy to use, generous free tier
- **Heroku**: Classic PaaS, paid only now
- **DigitalOcean App Platform**: More control, similar pricing
- **Self-hosted VM**: Most control, use Caddy + Docker (see plan file)

## Support

For issues:
- Check Render docs: https://render.com/docs
- Check Umami docs: https://umami.is/docs
- Review logs in Render dashboard
- Test locally first with same environment variables
