# app/core/security.py

from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.core.config import settings
import hashlib # <-- Import hashlib
from cryptography.fernet import Fernet

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

# --- NEW: Add the hash function here ---
def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()
# --- END OF NEW FUNCTION ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Token Encryption ---
def get_fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt_token(token: str) -> str:
    if not token: return token
    # Fernet requires bytes
    f = get_fernet()
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token: return encrypted_token
    f = get_fernet()
    return f.decrypt(encrypted_token.encode()).decode()