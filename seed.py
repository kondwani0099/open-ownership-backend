"""
Seed script — creates demo users for development.

Creates:
  • demo@applicant.com / password123  (role: applicant)
  • demo@reviewer.com / password123   (role: reviewer)

Run: python seed.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from app.database import get_users_collection, create_indexes
from app.routers.auth import hash_password


SEED_USERS = [
    {
        "email": "demo@applicant.com",
        "password": "password123",
        "role": "applicant",
        "name": "Alice Applicant",
    },
    {
        "email": "demo@reviewer.com",
        "password": "password123",
        "role": "reviewer",
        "name": "Bob Reviewer",
    },
]


async def seed():
    await create_indexes()
    collection = get_users_collection()
    now = datetime.now(timezone.utc)

    for user in SEED_USERS:
        existing = await collection.find_one({"email": user["email"]})
        if existing:
            print(f"User already exists: {user['email']} (role={user['role']}) — skipping")
            continue

        doc = {
            "email": user["email"],
            "password_hash": hash_password(user["password"]),
            "role": user["role"],
            "name": user["name"],
            "created_at": now,
        }
        await collection.insert_one(doc)
        print(f"Created user: {user['email']} (role={user['role']}) password={user['password']}")

    print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
