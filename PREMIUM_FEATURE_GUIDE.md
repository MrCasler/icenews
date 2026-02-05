# ICENews Premium Feature Guide

## Overview

ICENews now includes a **premium download feature** that allows authorized users to download media (videos, images) from X/Twitter posts directly from the interface.

### Key Features:
- 🔒 **Paywall Protected** - Only premium users can download
- ⚡ **One-Click Downloads** - Download button appears on each post for premium users
- 🎯 **X/Twitter Integration** - Uses yt-dlp to download media from posts
- 💳 **Easy to Extend** - Database-backed system ready for payment integration

---

## How It Works

### For Regular Users:
- See posts, like, and share normally
- Download button is hidden

### For Premium Users:
- See a "Premium" badge in the header
- Download button appears on each post
- Click to download media directly to their device

---

## Setup Guide

### 1. Install yt-dlp on Server

The download feature requires `yt-dlp` to be installed on your server.

**On Render.com:**
```yaml
# Add to render.yaml buildCommand:
buildCommand: |
  pip install -r requirements.txt
  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
  chmod a+rx /usr/local/bin/yt-dlp
```

**On Ubuntu/Docker:**
```bash
# Install via apt (recommended for production)
sudo apt update
sudo apt install -y yt-dlp

# Or install via pip (included in requirements.txt)
pip install yt-dlp
```

### 2. Deploy Updated Code

```bash
# Commit changes
git add .
git commit -m "Add premium download feature with paywall"
git push

# Render will auto-deploy, or manually deploy via dashboard
```

### 3. Grant Premium Access to Users

Use the admin API endpoint to add premium users:

```bash
curl -X POST https://icenews.eu/api/admin/premium/add \
  -H "Content-Type: application/json" \
  -u "your-email@example.com:your-password" \
  -d '{
    "email": "premium-user@example.com",
    "expires_at": "2027-12-31T23:59:59"
  }'
```

**Parameters:**
- `email` (required): User's email address (must match their login)
- `expires_at` (optional): ISO datetime when premium expires (omit for lifetime access)

**Response:**
```json
{
  "status": "success",
  "message": "Premium access granted to premium-user@example.com",
  "expires_at": "2027-12-31T23:59:59"
}
```

---

## User Experience

### Premium User Login Flow:

1. User visits icenews.eu
2. Enters credentials (email/password via Basic Auth)
3. System checks if email is in `premium_users` table
4. If premium:
   - "Premium" badge appears in header
   - Download buttons appear on all posts
5. User clicks Download button on any post
6. Media is downloaded directly to their device

### Non-Premium User:

1. User visits icenews.eu
2. Enters credentials
3. Can view, like, and share posts
4. Download button is hidden
5. Attempting direct API access returns 403 error

---

## Database Schema

### New Table: `premium_users`

```sql
CREATE TABLE premium_users (
    email TEXT PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    subscription_tier TEXT DEFAULT 'premium',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    notes TEXT
);
```

### Manually Add Premium User (SQL):

```sql
-- Add user with lifetime access
INSERT INTO premium_users (email, is_active, subscription_tier)
VALUES ('user@example.com', 1, 'premium');

-- Add user with expiration
INSERT INTO premium_users (email, is_active, subscription_tier, expires_at)
VALUES ('user@example.com', 1, 'premium', '2027-12-31 23:59:59');

-- Check premium status
SELECT * FROM premium_users WHERE email = 'user@example.com';
```

---

## API Endpoints

### Download Media (Premium Only)

```
GET /api/posts/{post_id}/download
```

**Authentication:** Required (Basic Auth)  
**Premium:** Required  

**Response:** Binary file (video/image)

**Example:**
```bash
curl -X GET https://icenews.eu/api/posts/1234567890/download \
  -u "premium@example.com:password" \
  --output video.mp4
```

### Grant Premium Access (Admin)

```
POST /api/admin/premium/add
```

**Authentication:** Required (Basic Auth)  
**Body:**
```json
{
  "email": "user@example.com",
  "expires_at": "2027-12-31T23:59:59"  // optional
}
```

---

## Monetization Integration

### Ready for Payment Processors

The premium system is designed to integrate with payment processors:

#### Stripe Integration (Example):

1. **Create Stripe checkout session**
2. **On successful payment**, call premium API:

```python
import stripe
import requests

# After successful Stripe payment
def handle_successful_payment(session):
    customer_email = session.customer_email
    
    # Grant premium access
    response = requests.post(
        "https://icenews.eu/api/admin/premium/add",
        json={
            "email": customer_email,
            "expires_at": "2027-12-31T23:59:59"  # 1 year from now
        },
        auth=(ADMIN_EMAIL, ADMIN_PASSWORD)
    )
    return response.json()
```

#### Recommended Subscription Tiers:

- **Free**: View posts, like, share
- **Premium ($5/month)**: + Download media
- **Pro ($15/month)**: + API access, custom feeds, analytics

---

## Security Considerations

### Current Security:

✅ **Authentication Required** - All endpoints require Basic Auth  
✅ **Premium Status Check** - Server validates premium access on every download  
✅ **Database-Backed** - Premium status stored in SQLite, not client-side  
✅ **Expiration Support** - Automatic expiration checking  

### Production Recommendations:

1. **Rate Limiting** - Add rate limits to download endpoint (e.g., 10 downloads/hour)
2. **Admin Protection** - Move `/api/admin/premium/add` to separate admin auth
3. **Payment Integration** - Connect to Stripe/PayPal for automated billing
4. **Usage Tracking** - Log download counts per user for analytics
5. **HTTPS Only** - Ensure Basic Auth only works over HTTPS (handled by Caddy)

---

## Troubleshooting

### Download Button Not Showing

**Check:**
1. Is user logged in with correct email?
2. Is email in `premium_users` table?
3. Check browser console for JavaScript errors
4. Verify `is_premium` is true in page context

**Debug:**
```bash
# Check premium status in database
sqlite3 icenews_social.db "SELECT * FROM premium_users WHERE email = 'user@example.com';"

# Check server logs for auth info
docker logs icenews-web | grep premium
```

### Download Fails with 403 Error

**Cause:** User is not premium or premium access expired

**Solution:**
```bash
# Re-add premium access
curl -X POST https://icenews.eu/api/admin/premium/add \
  -u "admin@example.com:password" \
  -d '{"email": "user@example.com"}'
```

### Download Fails with 503 Error

**Cause:** yt-dlp not installed on server

**Solution:**
```bash
# SSH into server and install yt-dlp
apt install -y yt-dlp

# Or via pip
pip install yt-dlp
```

### Downloads Are Slow

**Explanation:** Downloads proxy through server (user → server → X.com → server → user)

**Optimization Ideas:**
- Use CDN/edge functions for downloads
- Implement download queuing system
- Cache popular downloads temporarily

---

## Future Enhancements

### Planned Features:

1. **Batch Downloads** - Download all media from a feed
2. **Download History** - Track user's downloaded content
3. **Format Selection** - Choose video quality/format
4. **Scheduled Downloads** - Download posts automatically
5. **API Access** - RESTful API for premium users
6. **Usage Analytics** - Dashboard showing download stats

### Payment Integration Options:

- **Stripe** - Credit card subscriptions (recommended)
- **PayPal** - One-time or recurring payments
- **Crypto** - Bitcoin/Ethereum via Coinbase Commerce
- **Manual** - Invoice-based for enterprise

---

## Cost Analysis

### Server Requirements:

- **Storage**: +100MB for yt-dlp binary
- **Bandwidth**: ~5-20MB per download (varies by video)
- **CPU**: Minimal (yt-dlp is efficient)

### Pricing Recommendation:

- **Free tier**: 0 downloads/month
- **Premium ($5/month)**: 100 downloads/month
- **Pro ($15/month)**: Unlimited downloads

### Break-Even Analysis:

Assuming 5MB average download, 1GB bandwidth costs ~$0.08:
- 100 downloads = 500MB = ~$0.04 bandwidth cost
- $5 subscription = **99.2% profit margin** on bandwidth

---

## Quick Start Checklist

- [ ] Deploy updated code with `yt-dlp` dependency
- [ ] Install yt-dlp on production server
- [ ] Add yourself as first premium user via API
- [ ] Test download feature works
- [ ] Update `.env` with proper auth credentials
- [ ] (Optional) Integrate payment processor
- [ ] (Optional) Add rate limiting
- [ ] (Optional) Set up usage analytics

---

## Support

For issues or questions:
1. Check logs: `docker logs icenews-web`
2. Verify yt-dlp: `yt-dlp --version`
3. Test download API directly with curl
4. Check database: `sqlite3 icenews_social.db`

Need help? Contact your system administrator or check the main README.md.
