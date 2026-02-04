# Basic Authentication Setup Guide

ICENews includes HTTP Basic Authentication to protect your site before public deployment.

## How It Works

- **Disabled by default** (for local development)
- **Enable by setting both** `ICENEWS_AUTH_EMAIL` and `ICENEWS_AUTH_PASSWORD` in `.env`
- Uses email as username, password as password
- Protects all routes **except** `/health` (for monitoring)
- Uses `secrets.compare_digest()` to prevent timing attacks

## Setup Instructions

### Step 1: Edit `.env` File

Open `.env` and add your credentials:

```bash
# Basic auth for public access (set before deploying to public internet)
# Leave empty to disable auth (for local development)
# Set both to enable password protection (for production)
ICENEWS_AUTH_EMAIL=your.email@example.com
ICENEWS_AUTH_PASSWORD=YourSecurePasswordHere123
```

**Important:**
- Both fields must be set for auth to be enabled
- If either is empty, auth is disabled
- Use a strong password (at least 12 characters)
- This is **not** meant for multi-user authentication - it's a single password gate

### Step 2: Restart the Server

```bash
# Stop the current server (Ctrl+C)
# Then restart
python -m app.main
```

### Step 3: Test Authentication

Open `http://localhost:8000/` in your browser. You should see a login prompt.

- **Username**: The email you set
- **Password**: The password you set

### Testing with curl:

```bash
# Without credentials (should fail)
curl http://localhost:8000/

# With credentials (should succeed)
curl -u "your.email@example.com:YourSecurePasswordHere123" http://localhost:8000/

# Health check (always accessible, no auth required)
curl http://localhost:8000/health
```

### Step 4: Disable Authentication (for development)

To disable auth, simply empty both fields in `.env`:

```bash
ICENEWS_AUTH_EMAIL=
ICENEWS_AUTH_PASSWORD=
```

Then restart the server.

## When to Use Basic Auth

### ✅ Use Basic Auth When:
- Deploying to a public domain before full launch
- Want to limit access to friends/colleagues for testing
- Need simple password protection with no user accounts

### ❌ Don't Use Basic Auth For:
- Multi-user authentication (everyone shares one password)
- High-security applications (basic auth is not encrypted without HTTPS)
- Public launch (remove auth gate when ready for public access)

## Security Notes

### HTTPS is Required for Production

Basic Auth sends credentials with every request. **Always use HTTPS in production** to prevent credentials from being intercepted.

The password gate deployment guide includes automatic HTTPS setup with Let's Encrypt.

### Password Storage

- The password in `.env` is **not hashed** (it's plaintext)
- `.env` should **never** be committed to git (already in `.gitignore`)
- Use a unique password (not reused elsewhere)

### Rate Limiting

Basic auth does not include rate limiting. Add rate limiting at the reverse proxy layer (Caddy/nginx) to prevent brute force attacks.

See the deployment guide in the plan for Caddy rate limiting configuration.

## Testing Basic Auth

### Manual Testing

1. Enable auth in `.env`
2. Restart server
3. Test in browser - should prompt for login
4. Test all features work after login
5. Test /health endpoint works without auth

### Automated Testing

Run auth tests with credentials:

```bash
ICENEWS_AUTH_EMAIL=test@example.com ICENEWS_AUTH_PASSWORD=testpass123 pytest tests/test_auth.py -v
```

By default, auth tests are skipped to avoid interfering with other tests.

## Troubleshooting

### "Invalid credentials" but credentials are correct

- Check for typos in `.env`
- Make sure there's no trailing whitespace
- Restart the server after changing `.env`
- Clear browser cache/cookies

### Browser keeps asking for credentials

- The browser caches failed login attempts
- Try incognito/private mode
- Or clear the site's authentication cache

### Tests fail with 401 errors

- Auth is probably enabled (check `.env`)
- Clear `.env` credentials and restart
- Run `./run_tests.sh` which expects auth to be disabled

## Example Production Setup

### 1. Before DNS Cutover

```bash
# .env
ICENEWS_AUTH_EMAIL=admin@yourdomain.com
ICENEWS_AUTH_PASSWORD=RandomSecurePassword789!
```

Share these credentials with trusted testers.

### 2. After Testing, Before Public Launch

```bash
# .env - remove auth gate
ICENEWS_AUTH_EMAIL=
ICENEWS_AUTH_PASSWORD=
```

Restart the server and the site is now public.

### 3. If You Want to Re-enable Later

Just set the credentials again and restart.

## Next Steps

After setting up basic auth:

1. ✅ Test locally with auth enabled
2. ✅ Run all tests (`./run_tests.sh`) with auth disabled
3. ✅ Deploy to VM with HTTPS (see deployment guide in plan)
4. ✅ Set up rate limiting at Caddy/nginx
5. ✅ Monitor with health check endpoint
6. ✅ When ready for public, disable auth
