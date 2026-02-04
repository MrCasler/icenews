"""
Scheduled ingestion for ICENews.

Usage:
  # Run once manually
  python -m app.scheduler

  # Run as cron job (e.g., every 6 hours):
  0 */6 * * * cd /path/to/icenews && ./venv/bin/python -m app.scheduler >> logs/ingest.log 2>&1

  # Or use the built-in scheduler (runs in background):
  python -m app.scheduler --daemon --interval 21600  # 6 hours = 21600 seconds
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Resolve project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_ingest():
    """Run the ingestion script and return success status."""
    try:
        # Import here to avoid circular imports and ensure .env is loaded
        sys.path.insert(0, str(PROJECT_ROOT))
        from app.ingest.ingest_x_scrapfly import run

        logger.info("Starting scheduled ingestion...")
        run()
        logger.info("Ingestion completed successfully")
        return True
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return False


def run_once():
    """Run ingestion once."""
    success = run_ingest()
    return 0 if success else 1


def run_daemon(interval_seconds: int = 21600):
    """Run ingestion on a schedule (default: every 6 hours)."""
    logger.info(f"Starting scheduler daemon (interval: {interval_seconds}s / {interval_seconds/3600:.1f}h)")
    
    while True:
        logger.info(f"Scheduled run at {datetime.now().isoformat()}")
        run_ingest()
        
        next_run = datetime.now().timestamp() + interval_seconds
        logger.info(f"Next run at {datetime.fromtimestamp(next_run).isoformat()}")
        
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break


def main():
    parser = argparse.ArgumentParser(description="ICENews scheduled ingestion")
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run as daemon (continuous scheduler)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=21600,  # 6 hours
        help="Interval between runs in seconds (default: 21600 = 6 hours)"
    )
    args = parser.parse_args()

    if args.daemon:
        run_daemon(args.interval)
    else:
        sys.exit(run_once())


if __name__ == "__main__":
    main()
