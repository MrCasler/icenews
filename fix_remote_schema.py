#!/usr/bin/env python3
"""
One-time script to add missing columns to the deployed posts table.
Run this BEFORE running import_data.py.
"""
import requests
import sys

# SQL to add the missing columns
ALTER_SQL = """
ALTER TABLE posts ADD COLUMN reply_to_post_id TEXT;
ALTER TABLE posts ADD COLUMN quoted_post_id TEXT;
"""

def main():
    site_url = input("Enter your site URL (e.g., https://www.icenews.eu): ").strip()
    
    print(f"Adding missing columns to posts table...")
    
    response = requests.post(
        f"{site_url}/api/admin/import",
        json={"sql": ALTER_SQL},
        timeout=30
    )
    
    if response.status_code == 200:
        print("✅ Schema updated successfully!")
        print("Now you can run: python import_data.py database_export_inserts_only.sql")
    else:
        print(f"❌ Failed: {response.status_code}")
        print(response.text)
        sys.exit(1)

if __name__ == "__main__":
    main()
