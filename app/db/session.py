# app/db/session.py

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
import certifi # <-- Import certifi

# --- THIS IS THE FIX ---
# Add tlsCAFile=certifi.where() to the client connection
client = AsyncIOMotorClient(
    settings.MONGO_CONNECTION_STRING,
    tlsCAFile=certifi.where()
)
# --- END OF FIX ---

database = client[settings.MONGO_DB_NAME]

# Define collections
users_collection = database["users"]
bots_collection = database["bots"]
api_keys_collection = database["api_keys"]