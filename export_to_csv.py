#!/usr/bin/env python3
"""
Export ICENews database to CSV files.

Usage:
    python export_to_csv.py                     # Export to ./exports/
    python export_to_csv.py --output ./backup   # Export to ./backup/
"""
import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db import get_connection


def export_to_csv(output_dir: Path):
    """Export all tables to CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get list of tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cur.fetchall()]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exported = []
    
    for table in tables:
        # Get column names
        cur.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cur.fetchall()]
        
        # Get data
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        
        # Write CSV
        filename = f"{table}_{timestamp}.csv"
        filepath = output_dir / filename
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)  # Header
            writer.writerows(rows)    # Data
        
        exported.append((table, len(rows), filepath))
        print(f"✅ Exported {table}: {len(rows)} rows → {filepath}")
    
    conn.close()
    
    # Summary
    print(f"\n📊 Export Summary:")
    print(f"   Location: {output_dir}")
    total_rows = sum(count for _, count, _ in exported)
    print(f"   Tables: {len(exported)}")
    print(f"   Total rows: {total_rows}")
    
    return exported


def main():
    parser = argparse.ArgumentParser(description="Export ICENews database to CSV")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("./exports"),
        help="Output directory (default: ./exports)"
    )
    args = parser.parse_args()
    
    print(f"🗃️  Exporting database to CSV...")
    export_to_csv(args.output)
    print(f"\n✨ Export complete!")


if __name__ == "__main__":
    main()
