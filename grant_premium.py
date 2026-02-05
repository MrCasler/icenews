#!/usr/bin/env python3
"""
Helper script to grant premium access to users.

Usage:
    python grant_premium.py user@example.com
    python grant_premium.py user@example.com --expires 2027-12-31
"""
import sys
import requests
from datetime import datetime, timedelta


def grant_premium(email: str, expires_at: str = None):
    """Grant premium access via API."""
    
    # Read credentials from .env or prompt
    try:
        with open('.env', 'r') as f:
            env_lines = f.readlines()
            auth_email = None
            auth_password = None
            for line in env_lines:
                if line.startswith('ICENEWS_AUTH_EMAIL='):
                    auth_email = line.split('=', 1)[1].strip().strip('"')
                elif line.startswith('ICENEWS_AUTH_PASSWORD='):
                    auth_password = line.split('=', 1)[1].strip().strip('"')
    except FileNotFoundError:
        print("❌ .env file not found")
        sys.exit(1)
    
    if not auth_email or not auth_password:
        print("❌ Auth credentials not found in .env")
        sys.exit(1)
    
    # Get site URL
    site_url = input("Enter site URL (default: https://icenews.eu): ").strip() or "https://icenews.eu"
    
    # Prepare request
    payload = {"email": email}
    if expires_at:
        # Validate and format expiration date
        try:
            exp_date = datetime.fromisoformat(expires_at.replace('T', ' '))
            payload["expires_at"] = exp_date.isoformat()
        except ValueError:
            print(f"❌ Invalid date format: {expires_at}")
            print("   Use format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
            sys.exit(1)
    
    print(f"\n🔐 Granting premium access to: {email}")
    if expires_at:
        print(f"⏰ Expires: {expires_at}")
    else:
        print("⏰ Expires: Never (lifetime access)")
    
    # Make request
    try:
        response = requests.post(
            f"{site_url}/api/admin/premium/add",
            json=payload,
            auth=(auth_email, auth_password),
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ {data.get('message', 'Success')}")
            print(f"📧 User: {email}")
            print(f"⏳ Expires: {data.get('expires_at', 'Never')}")
            print("\n🎉 Premium access granted!")
        else:
            print(f"\n❌ Error {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    
    if len(sys.argv) < 2:
        print("Usage: python grant_premium.py <email> [--expires YYYY-MM-DD]")
        print("\nExamples:")
        print("  python grant_premium.py user@example.com")
        print("  python grant_premium.py user@example.com --expires 2027-12-31")
        sys.exit(1)
    
    email = sys.argv[1]
    expires_at = None
    
    # Check for --expires flag
    if len(sys.argv) > 2 and sys.argv[2] == '--expires':
        if len(sys.argv) < 4:
            print("❌ --expires requires a date argument")
            sys.exit(1)
        expires_at = sys.argv[3]
    
    grant_premium(email, expires_at)


if __name__ == "__main__":
    main()
