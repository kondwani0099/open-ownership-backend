"""
Seed script — creates demo users for development (PostgreSQL edition).
Run: python seed.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from app.database import AsyncSessionLocal, create_tables
from app.models.user import User
from app.routers.auth import hash_password
from sqlalchemy import select

SEED_USERS = [
    {"email": "demo@applicant.com", "password": "password123", "role": "applicant", "name": "Alice Applicant"},
    {"email": "demo@reviewer.com", "password": "password123", "role": "reviewer", "name": "Bob Reviewer"},
]


async def seed():
    await create_tables()
    async with AsyncSessionLocal() as db:
        for u in SEED_USERS:
            result = await db.execute(select(User).where(User.email == u["email"]))
            if result.scalar_one_or_none():
                print(f"User already exists: {u['email']} — skipping")
                continue
            user = User(
                email=u["email"],
                password_hash=hash_password(u["password"]),
                role=u["role"],
                name=u["name"],
            )
            db.add(user)
            print(f"Created: {u['email']} (role={u['role']}) password={u['password']}")
        await db.commit()
    print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
