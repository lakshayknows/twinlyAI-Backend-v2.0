# app/schemas/bot.py

from pydantic import BaseModel, Field
from typing import Optional, List # <-- Make sure List is imported
from .pyobjectid import PyObjectId
from bson import ObjectId

class Project(BaseModel):
    name: str
    description: Optional[str] = None
    link: Optional[str] = None


class BotBase(BaseModel):
    name: str

class BotCreate(BotBase):
    pass

# --- UPDATED BotUpdate MODEL ---
class BotUpdate(BaseModel):
    name: Optional[str] = None #<-- Make name optional
    # --- NEW FIELDS ---
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[float] = None
    avatar_url: Optional[str] = None
    # --- SOCIAL LINKS ---
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None
    website_url: Optional[str] = None
    projects: Optional[List[Project]] = None
    # ------------------

class Bot(BotBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: Optional[str] = None
    # --- NEW FIELDS ---
    summary: Optional[str] = None
    skills: Optional[List[str]] = []
    experience_years: Optional[float] = 0.0
    avatar_url: Optional[str] = None
    # --- SOCIAL LINKS ---
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    twitter_url: Optional[str] = None
    website_url: Optional[str] = None
    projects: Optional[List[Project]] = []
    # ------------------

    class Config:
        json_encoders = {ObjectId: str}
        populate_by_name = True
        arbitrary_types_allowed = True