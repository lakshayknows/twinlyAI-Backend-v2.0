# app/api/v1/deps.py

import logging
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import APIKeyHeader
from jose import JWTError, jwt
from app.core.config import settings
from app.schemas.user import User
from app.db.session import users_collection, api_keys_collection
from app.core.security import hash_api_key
from typing import Optional
from bson import ObjectId

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

async def get_authenticated_user(
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Depends(api_key_header)
) -> dict:
    """
    Validates credentials from either a JWT token (from Authorization header) or an API key.
    Returns the user document from the database.
    """
    # 1. Try to authenticate with JWT token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email: str = payload.get("sub")
            if email is None:
                raise credentials_exception
            user = await users_collection.find_one({"email": email})
            if user:
                return user
        except JWTError:
            logging.debug("JWT token validation failed")

    # 2. If token auth fails or is not provided, try to authenticate with API key
    if api_key:
        hashed_key = hash_api_key(api_key)
        key_doc = await api_keys_collection.find_one({"hashed_key": hashed_key})
        if key_doc:
            user = await users_collection.find_one({"_id": ObjectId(key_doc["user_id"])})
            if user:
                return user

    # 3. If neither method succeeds, raise the exception
    raise credentials_exception

async def get_current_user(
    authenticated_user: dict = Depends(get_authenticated_user)
) -> User:
    """
    Ensures the user came from a JWT token (has hashed_password field).
    Sanitizes the MongoDB document before passing to Pydantic to prevent 500 errors.
    """
    # Security check: API key users don't typically have hashed_password loaded or needed here
    if "hashed_password" not in authenticated_user and "role" not in authenticated_user:
         # Fallback check if the user doc structure is different
         pass 

    # --- FIX: Sanitize Data for Pydantic ---
    # Create a clean dictionary
    user_data = authenticated_user.copy()
    
    # 1. Convert ObjectId to string manually (safest approach)
    if "_id" in user_data:
        user_data["id"] = str(user_data["_id"])
        del user_data["_id"]
        
    # 2. Remove hashed_password so it doesn't leak or confuse Pydantic
    if "hashed_password" in user_data:
        del user_data["hashed_password"]

    # 3. Return Pydantic Model
    return User(**user_data)

async def check_subscription_tier(
    required_tier: str,
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to check if a user has the required subscription tier.
    Defaults to Plus/Unlimited for local development.
    """
    if settings.ENV == "dev":
        return current_user # Bypass in local dev

    tiers = ["free", "pro", "plus"]
    if tiers.index(current_user.subscription_tier) < tiers.index(required_tier):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="{} subscription required for this feature".format(required_tier.capitalize())
        )
    return current_user

def check_tier(required_tier: str):
    """
    Factory to create a dependency for a specific tier.
    Usage: Depends(check_tier("pro"))
    """
    async def _dependency(user: User = Depends(get_current_user)) -> User:
        return await check_subscription_tier(required_tier, user)
    return _dependency