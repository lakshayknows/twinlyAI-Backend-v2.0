# app/core/config.py

from pydantic_settings import BaseSettings
from dotenv import load_dotenv 
from typing import Optional

load_dotenv()  

class Settings(BaseSettings):
    """
    Application settings are loaded from environment variables.
    """
    MONGO_CONNECTION_STRING: str
    SECRET_KEY: str
    GROQ_API_KEY: str 
    ALGORITHM: str = "HS256"
    MONGO_DB_NAME: str = "twinlyai_db" 
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # OAuth Settings
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    SESSION_SECRET_KEY: str 

    # Vector DB Settings
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # URL Settings (Defaults to localhost for safety)
    FRONTEND_URL: str = "http://localhost:3000"

    # Agora Settings
    AGORA_APP_ID: Optional[str] = None
    AGORA_APP_CERTIFICATE: Optional[str] = None

    # Environment
    ENV: str = "dev" # options: dev, prod

    # Cloudinary Settings
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    STORAGE_TYPE: str = "local" # options: local, cloudinary

    class Config:
        env_file = ".env"

settings = Settings()