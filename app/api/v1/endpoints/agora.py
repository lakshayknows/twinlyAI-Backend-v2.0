# app/api/v1/endpoints/agora.py

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.api.v1.deps import get_current_user
from app.schemas.user import User

# --- FIX 1: UNCOMMENT THIS IMPORT ---
from app.core.agora_token import generate_agora_token 

# We can keep VoiceAgent imported, but ensure you have 'edge-tts' installed locally!
#from app.core.voice_agent import VoiceAgent 
from app.db.session import bots_collection
from bson import ObjectId
import random

router = APIRouter()

# Global dictionary to keep track of active agents in memory
active_agents = {}

class TokenRequest(BaseModel):
    channel_name: str 

class StartCallRequest(BaseModel):
    channel_name: str

class TokenResponse(BaseModel):
    token: str
    channel_name: str
    uid: int

@router.post("/token", response_model=TokenResponse)
async def get_agora_token(
    request: TokenRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Generate an Agora RTC token for the authenticated user (recruiter).
    """
    # Generate a random 32-bit integer for the Agora UID.
    user_uid = random.randint(1, 2**32 - 1)
    
    try:
        # This function needs to be imported to work!
        token = generate_agora_token(
            channel_name=request.channel_name,
            user_uid=user_uid
        )
        
        return {
            "token": token,
            "channel_name": request.channel_name,
            "uid": user_uid
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start-call")
async def start_voice_agent(
    request: StartCallRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Initializes and joins the AI Agent to the Agora channel.
    """
    bot_id = request.channel_name
    
    # 1. Check if agent is already active
    if bot_id in active_agents and active_agents[bot_id].is_joined:
         return {"message": "Agent already in call"}

    # 2. Fetch Bot details
    try:
        bot = await bots_collection.find_one({"_id": ObjectId(bot_id)})
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid Bot ID format")
         
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    try:
        # --- MOCKED AI AGENT STARTUP ---
        # We comment out the actual VoiceAgent logic to verify connections first.
        
        # agent = VoiceAgent(
        #     bot_id=bot_id,
        #     user_id=str(bot["user_id"]),
        #     bot_name=bot["name"]
        # )
        # await agent.join_call()
        # active_agents[bot_id] = agent
        
        print(f" [MOCK] AI Agent summoned for channel: {bot_id}")
        return {"message": "AI Agent joined successfully (Mocked)"}

    except Exception as e:
        print(f"Error starting agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start AI Agent: {e}")