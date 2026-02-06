#!/usr/bin/env python3
"""
Pull the database from Render (or any deployed instance) to your local machine.
Uses the same secret as the server's EXPORT_SECRET env var.

Usage:
  python pull_from_render.py https://icenews.eu
  python pull_from_render.py https://icenews.eu -o local_backup.db

Set EXPORT_SECRET in your local environment to match the server, or you'll be prompted.
"""
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


def main():
    url = (sys.argv[1] if len(sys.argv) > 1 else "").strip().rstrip("/")
    if not url:
        print("Usage: python pull_from_render.py <base_url> [-o output.db]", file=sys.stderr)
        print("  Example: python pull_from_render.py https://icenews.eu", file=sys.stderr)
        sys.exit(1)

    out_idx = 2
    output_path = None
    if len(sys.argv) > 3 and sys.argv[2] == "-o":
        output_path = Path(sys.argv[3])
        out_idx = 4

    secret = os.getenv("EXPORT_SECRET", "").strip()
    if not secret:
        try:
            secret = input("Export secret (EXPORT_SECRET): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("Aborted.", file=sys.stderr)
            sys.exit(1)
    if not secret:
        print("Export secret is required.", file=sys.stderr)
        sys.exit(1)

    export_url = f"{url}/api/admin/export-db"
    headers = {"X-Export-Secret": secret}
    print(f"Fetching database from {export_url} ...")
    try:
        r = requests.get(export_url, headers=headers, timeout=120, stream=True)
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("Invalid or missing export secret.", file=sys.stderr)
        elif e.response.status_code == 503:
            print("Export not configured on server (EXPORT_SECRET not set).", file=sys.stderr)
        else:
            print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not output_path:
        # Default: save next to project's db so you can replace local copy
        root = Path(__file__).resolve().parent
        output_path = root / "icenews_social_render.db"
    else:
        output_path = Path(output_path).resolve()

    written = 0
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                written += len(chunk)
    print(f"Saved to {output_path} ({written} bytes).")
    print("To use as your local DB: copy over icenews_social.db or point your app at this file.")


if __name__ == "__main__":
    main()
