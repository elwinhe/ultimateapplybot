"""
app/api/v1/auth.py

Authentication endpoints for user login/signup and token management.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
import secrets
import hashlib

from app.config import settings
from app.services.postgres_client import postgres_client

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

# JWT settings
SECRET_KEY = settings.JWT_SECRET_KEY or secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

router = APIRouter(prefix="/user", tags=["user-authentication"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)


class TokenResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    name: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    # Simple SHA256 hash for now - in production use bcrypt
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password


def get_password_hash(password: str) -> str:
    """Hash a password."""
    # Simple SHA256 hash for now - in production use bcrypt
    return hashlib.sha256(password.encode()).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    async with postgres_client._pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT user_id, email, name FROM users WHERE user_id = $1",
            user_id
        )
        
    if user is None:
        raise credentials_exception
        
    return dict(user)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login with email and password."""
    async with postgres_client._pool.acquire() as conn:
        # Get user by email
        user = await conn.fetchrow(
            "SELECT user_id, email, name, password_hash FROM users WHERE email = $1",
            request.email
        )
        
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user["user_id"])})
    
    return TokenResponse(
        token=access_token,
        user={
            "id": str(user["user_id"]),
            "email": user["email"],
            "name": user["name"],
        }
    )


@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    """Create a new user account."""
    async with postgres_client._pool.acquire() as conn:
        # Check if user already exists
        existing_user = await conn.fetchrow(
            "SELECT user_id FROM users WHERE email = $1",
            request.email
        )
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        
        # Create new user
        password_hash = get_password_hash(request.password)
        
        try:
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, name, password_hash, created_at)
                VALUES ($1, $2, $3, $4)
                RETURNING user_id, email, name
                """,
                request.email,
                request.name,
                password_hash,
                datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user",
            )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user["user_id"])})
    
    return TokenResponse(
        token=access_token,
        user={
            "id": str(user["user_id"]),
            "email": user["email"],
            "name": user["name"],
        }
    )


@router.get("/verify")
async def verify_token(current_user: dict = Depends(get_current_user)):
    """Verify the current JWT token and return user info."""
    return {
        "user": {
            "id": str(current_user["user_id"]),
            "email": current_user["email"],
            "name": current_user["name"],
        }
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=str(current_user["user_id"]),
        email=current_user["email"],
        name=current_user["name"],
    )
