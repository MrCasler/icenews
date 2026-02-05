# Important: Render Configuration

## Why Not Docker on Render?

You have a `Dockerfile` and `docker-compose.yml` in your project, but **Render deployment uses native Python**, not Docker. Here's why:

### The Issue with Docker on Render Free Tier:

1. **Docker containers are ephemeral** - filesystem doesn't persist
2. **No persistent disks on free tier** - can't mount volumes
3. **Database gets wiped** on every restart
4. **Result**: You'd need to run `import_data.py` after every restart

### The Solution: Native Python Runtime

The `render.yaml` is configured to use:
```yaml
env: python
runtime: python-3.11
```

This gives you:
- ✅ Project directory persists across restarts
- ✅ Database survives service restarts
- ✅ Works on free tier
- ✅ No Docker needed

## When to Use Docker vs Native Python

### Use Docker (docker-compose.yml):
- **Local development**
- **Self-hosted VPS** (your own server)
- **Paid Render plan** with persistent disks

### Use Native Python (render.yaml):
- **Render.com free tier** ✅ (current setup)
- **Render.com deployment** (any tier)
- **Simpler deployments** without container overhead

## Your Setup

### For Render.com:
- Uses `render.yaml` (native Python)
- Database at `/opt/render/project/src/icenews_social.db`
- Persists across restarts ✅

### For Local Development:
- Use `docker-compose up` (Docker)
- Database at `./icenews_social.db`
- Full local environment with Caddy, scheduler, etc.

### For Self-Hosted Server:
- Use `docker-compose.yml` (Docker)
- Full production stack
- Persistent volumes work as expected

## Summary

- **Render.com** = Native Python (render.yaml) ✅ Currently configured
- **Local Dev** = Docker (docker-compose.yml)
- **Self-Hosted** = Docker (docker-compose.yml)

The Dockerfile exists for local development and self-hosting, but Render ignores it when you specify `env: python` in render.yaml.
