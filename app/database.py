"""
MongoDB connection layer for the Submission & Approval Workflow.

Uses Motor (async) for FastAPI compatibility.
Collections are lazy-loaded on the shared client.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env from project root
load_dotenv()
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://root:example@localhost:27017")
DB_NAME = os.getenv("DB_NAME", "open_ownership")

_client: AsyncIOMotorClient | None = None


def _get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        uri = MONGO_URI
        use_tls = "mongodb+srv://" in uri
        kwargs = {
            "serverSelectionTimeoutMS": 30000,
            "connectTimeoutMS": 30000,
            "socketTimeoutMS": 30000,
        }
        if use_tls:
            # Append TLS bypass params to URI — fixes Windows + Atlas SSL handshake
            sep = "&" if "?" in uri else "?"
            uri = f"{uri}{sep}tls=true&tlsAllowInvalidCertificates=true"
            kwargs["tls"] = True
        else:
            kwargs["tls"] = False

        logger.info("Connecting to MongoDB (tls=%s)...", use_tls)
        _client = AsyncIOMotorClient(uri, **kwargs)
    return _client


def get_db():
    """Return the application database."""
    return _get_client()[DB_NAME]


def get_users_collection():
    return get_db()["users"]


def get_applications_collection():
    return get_db()["applications"]


def get_audit_logs_collection():
    return get_db()["audit_logs"]


async def create_indexes():
    """Create necessary indexes on boot."""
    db = get_db()
    await db["users"].create_index("email", unique=True)
    await db["applications"].create_index("applicant_id")
    await db["applications"].create_index("status")
    await db["audit_logs"].create_index("application_id")
