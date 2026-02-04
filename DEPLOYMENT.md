# ICENews Deployment Guide

Complete guide to deploy ICENews on a Ubuntu VM with Docker, accessible at `icenews.eu`.

---

## Part 1: Set Up Ubuntu VM (VirtualBox)

### 1.1 Download Ubuntu Server
1. Go to https://ubuntu.com/download/server
2. Download **Ubuntu Server 24.04 LTS** (or 22.04 LTS)
3. Choose the minimal ISO (~2GB)

### 1.2 Create VM in VirtualBox
1. Open VirtualBox → **New**
2. Settings:
   - **Name**: icenews
   - **Type**: Linux
   - **Version**: Ubuntu (64-bit)
   - **Memory**: 2048 MB (2GB minimum)
   - **Hard disk**: Create a virtual hard disk now
   - **Size**: 20 GB (dynamic allocation)
3. Before starting, go to **Settings**:
   - **System** → Processor: 2 CPUs
   - **Network** → Adapter 1: **Bridged Adapter** (so VM gets its own IP)
   - **Storage** → Controller: IDE → Empty → Choose the Ubuntu ISO

### 1.3 Install Ubuntu
1. Start the VM
2. Follow the installer:
   - Language: English
   - Keyboard: Your layout
   - **Minimized** installation (no snaps)
   - Network: Use DHCP (automatic)
   - Storage: Use entire disk
   - Username: `icenews` (or your choice)
   - Password: Choose a strong password
   - **Install OpenSSH server**: Yes
   - No additional snaps needed
3. Reboot when prompted
4. Remove the ISO from Settings → Storage

### 1.4 Find VM's IP address
After boot, login and run:
```bash
ip addr show
```
Look for `inet 192.168.x.x` or similar. This is your VM's IP.

### 1.5 SSH into the VM (from your Mac)
```bash
ssh icenews@192.168.x.x
```

---

## Part 2: Install Docker

### 2.1 Update system
```bash
sudo apt update && sudo apt upgrade -y
```

### 2.2 Install Docker
```bash
# Install prerequisites
sudo apt install -y ca-certificates curl gnupg

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to docker group (so you don't need sudo)
sudo usermod -aG docker $USER

# Log out and back in for group change to take effect
exit
```

SSH back in:
```bash
ssh icenews@192.168.x.x
```

Verify Docker:
```bash
docker --version
docker compose version
```

---

## Part 3: Deploy ICENews

### 3.1 Copy project to VM

**Option A: Git clone** (if you push to GitHub)
```bash
git clone https://github.com/yourusername/icenews.git
cd icenews
```

**Option B: SCP from your Mac**
```bash
# On your Mac, from the project directory:
scp -r . icenews@192.168.x.x:~/icenews/
```

### 3.2 Create production .env file
```bash
cd ~/icenews
nano .env
```

Add these variables:
```env
# Scrapfly (REQUIRED)
SCRAPFLY_KEY=scp-live-your-actual-key
SCRAPFLY_USE_TEST=0
SCRAPFLY_TEST_KEY=scp-test-your-test-key

# Ingestion settings
ICENEWS_MAX_TWEETS_PER_ACCOUNT=4

# Umami Analytics (get from Umami Cloud dashboard)
UMAMI_WEBSITE_ID=your-website-id-from-umami
UMAMI_SCRIPT_URL=https://cloud.umami.is/script.js

# Basic auth password (optional, for public access)
ICENEWS_AUTH_PASSWORD=
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### 3.3 Initialize the database (if not already done)
```bash
# If you don't have icenews_social.db yet:
sqlite3 icenews_social.db < db

# Import accounts
docker compose run --rm web python -m app.ingest.import_accounts
```

### 3.4 Update Caddyfile with your domain
```bash
nano Caddyfile
```
Replace `icenews.eu` with your actual domain.

### 3.5 Build and start services
```bash
docker compose build
docker compose up -d
```

### 3.6 Check status
```bash
docker compose ps
docker compose logs -f
```

---

## Part 4: Point Domain to VM

### 4.1 Get your public IP
Your VM needs a public IP. Options:

**Option A: Port forwarding on your router**
1. Find your public IP: https://whatismyip.com
2. In your router settings, forward ports 80 and 443 to your VM's internal IP (192.168.x.x)

**Option B: Cloud VM**
If using a cloud provider (DigitalOcean, Hetzner, etc.), your VM already has a public IP.

### 4.2 Configure DNS
In your DNS provider (inwx, Cloudflare, etc.):

1. Add an **A record**:
   - **Name**: `@` (or blank, for root domain)
   - **Value**: Your public IP
   - **TTL**: 300 (or Auto)

2. Add a **CNAME** for www (optional):
   - **Name**: `www`
   - **Value**: `icenews.eu`

### 4.3 Wait for DNS propagation
DNS changes can take 5-30 minutes. Check with:
```bash
dig icenews.eu
```

### 4.4 Caddy will automatically get HTTPS
Once DNS is pointing to your server, Caddy automatically:
- Gets a Let's Encrypt certificate
- Redirects HTTP → HTTPS
- Renews certificates automatically

---

## Part 5: Verify Everything Works

### 5.1 Test the site
Open in browser: `https://icenews.eu`

### 5.2 Check scheduler is running
```bash
docker compose logs scheduler
```
Should show periodic ingestion runs.

### 5.3 Manually trigger ingestion
```bash
docker compose exec scheduler python -m app.ingest.ingest_x_scrapfly
```

---

## Part 6: Optional Enhancements

### 6.1 Enable basic auth
Generate password hash:
```bash
docker run --rm caddy caddy hash-password --plaintext "your-secret-password"
```

Edit Caddyfile, uncomment the basicauth section, paste the hash:
```
basicauth /* {
    reader $2a$14$xxxYOUR_HASH_HERExxx
}
```

Restart Caddy:
```bash
docker compose restart caddy
```

### 6.2 Set up automatic backups
Create backup script:
```bash
mkdir -p ~/backups
nano ~/backup-icenews.sh
```

Add:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
cp ~/icenews/icenews_social.db ~/backups/icenews_social_$DATE.db
# Keep only last 7 days
find ~/backups -name "*.db" -mtime +7 -delete
```

Make executable and schedule:
```bash
chmod +x ~/backup-icenews.sh
crontab -e
```

Add line:
```
0 2 * * * /home/icenews/backup-icenews.sh
```

### 6.3 Auto-start on boot
Docker Compose services with `restart: unless-stopped` will auto-start.
To ensure Docker starts on boot:
```bash
sudo systemctl enable docker
```

---

## Troubleshooting

### Caddy can't get certificate
- Check DNS is pointing to your IP: `dig icenews.eu`
- Check ports 80/443 are open: `sudo ufw allow 80,443/tcp`
- Check Caddy logs: `docker compose logs caddy`

### Scheduler not running
- Check logs: `docker compose logs scheduler`
- Make sure SCRAPFLY_KEY is set in .env
- Try manual run: `docker compose exec scheduler python -m app.ingest.ingest_x_scrapfly`

### Database locked errors
- Only one process should write at a time (scheduler)
- If stuck, restart: `docker compose restart`

### Out of disk space
- Check: `df -h`
- Clean Docker: `docker system prune -a`

---

## Quick Reference Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f

# Rebuild after code changes
docker compose build && docker compose up -d

# Manual ingestion
docker compose exec scheduler python -m app.ingest.ingest_x_scrapfly

# Enter web container shell
docker compose exec web bash

# Check database
docker compose exec web sqlite3 icenews_social.db "SELECT COUNT(*) FROM posts;"
```

---

## Summary

1. **Ubuntu VM** in VirtualBox with bridged networking
2. **Docker + Docker Compose** installed
3. **ICENews** deployed with:
   - `web`: FastAPI app on port 8000
   - `scheduler`: Runs ingestion every 6 hours
   - `caddy`: HTTPS + reverse proxy
4. **DNS** pointing `icenews.eu` → VM's public IP
5. **Caddy** auto-provisions HTTPS via Let's Encrypt

Your site is now live at `https://icenews.eu` with:
- Automatic HTTPS
- Scheduled ingestion every 6 hours (4 posts per account)
- Umami analytics tracking
- Like and share buttons
- Clickable post cards
