#!/usr/bin/env python3
"""Grant premium access to a user for testing V2 features."""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.db import add_premium_user, get_user_by_email, update_user_premium_status, create_or_get_user

def grant_premium(email: str):
    """Grant premium access to user."""
    # Create user if doesn't exist
    user = create_or_get_user(email)
    if not user:
        print(f"❌ Failed to create/get user: {email}")
        return False
    
    # Add to legacy premium_users table
    success1 = add_premium_user(email, expires_at=None)
    
    # Update users table is_premium flag
    success2 = update_user_premium_status(
        email=email,
        is_premium=True,
        premium_expires_at=None
    )
    
    if success1 or success2:
        print(f"✅ Premium access granted to: {email}")
        print(f"   User ID: {user['id']}")
        print(f"   Nickname: {user.get('nickname') or 'Not set'}")
        return True
    else:
        print(f"❌ Failed to grant premium access")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python grant_premium_v2.py <email>")
        print("Example: python grant_premium_v2.py abedrodriguez184@gmail.com")
        sys.exit(1)
    
    email = sys.argv[1].strip().lower()
    grant_premium(email)
