#!/usr/bin/env python3
"""
One-time script to import data into Render deployment.
Run this once after deployment, then delete it.

Usage:
    python import_data.py database_export.sql
"""
import sys
import requests

if len(sys.argv) < 2:
    print("Usage: python import_data.py database_export.sql")
    sys.exit(1)

sql_file = sys.argv[1]
url = input("Enter your site URL (e.g., https://icenews.eu): ").strip()

with open(sql_file, 'r') as f:
    sql = f.read()

print(f"Importing {len(sql)} bytes of SQL...")
response = requests.post(
    f"{url}/api/admin/import",
    json={"sql": sql},
    timeout=60
)

if response.status_code == 200:
    print("✅ Import successful!")
    print(response.json())
else:
    print(f"❌ Import failed: {response.status_code}")
    print(f"Response text: {response.text}")
    try:
        error_detail = response.json()
        print(f"Error detail: {error_detail}")
    except:
        pass
