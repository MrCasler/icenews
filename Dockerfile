# ICENews Docker image
# Runs the FastAPI web app or the scheduler (same image, different commands)

FROM python:3.11-slim

# Prevent Python from writing bytecode and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY scrapfly-scrapers/ scrapfly-scrapers/

# Create data directory for SQLite DB
RUN mkdir -p /data

# Default: run the web server
# Override with docker-compose to run scheduler instead
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
