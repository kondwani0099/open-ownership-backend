"""
Authentication router — login, token verification, and current-user dependency.

Uses JWT with HS256. In production, use RS256 + key rotation.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from bson import ObjectId

from app.database import get_users_collection
from app.models.user import (
    UserResponse,
    UserCreate,
    LoginRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Configuration ──────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ── Helpers ────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """FastAPI dependency: extracts and validates the current user from JWT."""
    try:
        payload = decode_token(credentials.credentials)
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    collection = get_users_collection()
    doc = await collection.find_one({"email": email})
    if doc is None:
        raise HTTPException(status_code=401, detail="User not found")

    return UserResponse(
        id=str(doc["_id"]),
        email=doc["email"],
        role=doc["role"],
        name=doc["name"],
        created_at=doc.get("created_at", datetime.utcnow()),
    )


def require_role(*allowed_roles: str):
    """Dependency factory: only allows users with one of the given roles."""
    async def dependency(user: UserResponse = Depends(get_current_user)) -> UserResponse:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}. Your role: {user.role}",
            )
        return user
    return dependency


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate and return a JWT."""
    collection = get_users_collection()
    doc = await collection.find_one({"email": body.email})
    if doc is None or not verify_password(body.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = UserResponse(
        id=str(doc["_id"]),
        email=doc["email"],
        role=doc["role"],
        name=doc["name"],
        created_at=doc.get("created_at", datetime.utcnow()),
    )

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserResponse)
async def me(user: UserResponse = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return user


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserCreate):
    """Register a new user and return a JWT."""
    collection = get_users_collection()

    # Check if email already exists
    existing = await collection.find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Validate role
    if body.role not in ("applicant", "reviewer"):
        raise HTTPException(status_code=400, detail="Role must be 'applicant' or 'reviewer'")

    now = datetime.now(timezone.utc)
    doc = {
        "email": body.email,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "name": body.name,
        "created_at": now,
    }
    result = await collection.insert_one(doc)

    user = UserResponse(
        id=str(result.inserted_id),
        email=body.email,
        role=body.role,
        name=body.name,
        created_at=now,
    )

    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token, user=user)
