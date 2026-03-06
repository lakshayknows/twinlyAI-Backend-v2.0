# app/schemas/api_key.py

from pydantic import BaseModel
from typing import Optional

class APIKey(BaseModel):
    id: str
    prefix: str

class APIKeyCreateResponse(BaseModel):
    api_key: str
    message: str