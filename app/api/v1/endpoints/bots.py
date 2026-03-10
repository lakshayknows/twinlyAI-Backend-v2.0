# app/api/v1/endpoints/bots.py

import os
import shutil
import re
from typing import List
from bson import ObjectId

from fastapi import (
    APIRouter, UploadFile, File, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
)
from starlette.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage

from groq import AsyncGroq
import edge_tts
import tempfile
import base64
import json
from app.core.config import settings

# Initialize Groq for Whisper (Audio transcription)
try:
    groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
except Exception as e:
    print(f"Warning: Groq client failed to initialize for Whisper STT: {e}")
    groq_client = None

from app.api.v1.deps import get_current_user, get_authenticated_user
from app.schemas.user import User
from app.schemas.bot import Bot, BotCreate, BotUpdate
from app.db.session import bots_collection
from app.core.rag_pipeline import RAGPipeline, GlobalRecruiterIndex

router = APIRouter()

def strip_think_tags(text: str) -> str:
    """Removes <think> tags from the LLM response for a cleaner output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

@router.get("/public/{bot_id}")
async def get_public_bot_info(bot_id: str):
    try:
        obj_id = ObjectId(bot_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid bot ID format")

    bot = await bots_collection.find_one({"_id": obj_id})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return {"id": str(bot["_id"]), "name": bot.get("name", "Unknown")}

@router.post("/create", response_model=Bot, status_code=status.HTTP_201_CREATED)
async def create_bot(bot_in: BotCreate, current_user: User = Depends(get_current_user)):
    try:
        bot_doc = { "name": bot_in.name, "user_id": str(current_user.id) }
        result = await bots_collection.insert_one(bot_doc)
        created_bot = await bots_collection.find_one({"_id": result.inserted_id})
        return created_bot
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Create bot error: {str(e)}")

@router.post("/{bot_id}/upload", status_code=status.HTTP_200_OK)
async def upload_resume(bot_id: str, file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    print(f"[UPLOAD] bot_id={bot_id!r}  current_user.id={current_user.id!r}")
    try:
        bot = await bots_collection.find_one({"_id": ObjectId(bot_id), "user_id": str(current_user.id)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid bot ID: {e}")

    if not bot:
        # Fallback: look up by bot_id only and print what we find, to help diagnose mismatches
        any_bot = await bots_collection.find_one({"_id": ObjectId(bot_id)})
        print(f"[UPLOAD] Bot not found with user match. Bot by ID only: {any_bot}")
        raise HTTPException(status_code=404, detail="Bot not found")

    pipeline = RAGPipeline(bot_id=bot_id, user_id=str(current_user.id), bot_name=bot["name"])
    
    import tempfile
    file_location = os.path.join(tempfile.gettempdir(), file.filename)
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)

    try:
        # 1. Process file for RAG (Document Chunks)
        pipeline.process_file(file_location)

        # 2. Extract Structured Metadata
        print(f"Extracting metadata for bot {bot['name']}...")
        metadata = await pipeline.extract_metadata(file_location)
        
        update_data = {
            "summary": metadata.get("summary"),
            "skills": metadata.get("skills"),
            "experience_years": metadata.get("experience_years"),
            "name": metadata.get("candidate_name", bot["name"]) 
        }
        
        # 3. Update individual bot metadata in MongoDB
        await bots_collection.update_one(
            {"_id": ObjectId(bot_id)}, 
            {"$set": update_data}
        )

        # 4. ADD TO GLOBAL SEMANTIC SEARCH INDEX
        # We create a rich text representation of the candidate for the vector search to index.
        profile_text = (
            f"Candidate Name: {update_data['name']}\n"
            f"Professional Summary: {update_data['summary']}\n"
            f"Top Skills: {', '.join(update_data['skills'] if update_data['skills'] else [])}\n"
            f"Experience: {update_data['experience_years']} years."
        )
        
        global_index = GlobalRecruiterIndex()
        global_index.add_candidate_profile(bot_id=bot_id, profile_text=profile_text)

        return {
            "message": f"Successfully uploaded and indexed resume for bot '{bot['name']}'",
            "extracted_data": update_data 
        }

    except Exception as e:
        print(f"CRITICAL ERROR in upload_resume: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error during upload: {str(e)}")
    finally:
        if os.path.exists(file_location):
            os.remove(file_location)

@router.post("/{bot_id}/chat")
async def chat_with_bot(bot_id: str, request_data: dict, authenticated_user: dict = Depends(get_authenticated_user)):
    user_message = request_data.get("message")
    chat_history_raw = request_data.get("chat_history", [])

    bot = await bots_collection.find_one({"_id": ObjectId(bot_id)})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # --- PERMISSION LOGIC ---
    is_owner = str(bot.get("user_id")) == str(authenticated_user.get("_id"))
    is_recruiter = authenticated_user.get("role") == "recruiter"

    if not is_owner and not is_recruiter:
        raise HTTPException(status_code=403, detail="You do not have permission for this bot")
    # -----------------------------

    pipeline = RAGPipeline(bot_id=bot_id, user_id=str(bot["user_id"]), bot_name=bot["name"])
    
    # --- FIX: HANDLE ROLE VS TYPE MISMATCH ---
    chat_history = []
    for msg in chat_history_raw:
        # Frontend sends 'role', backend logic previously expected 'type'
        # We check both to be safe
        role = msg.get("role") or msg.get("type")
        content = msg.get("content", "")
        
        if role == "user":
            chat_history.append(HumanMessage(content=content))
        else:
            chat_history.append(AIMessage(content=content))
    # -----------------------------------------
    
    full_response = ""
    async for chunk in pipeline.get_response_stream(user_message, chat_history):
        full_response += chunk

    return {"reply": strip_think_tags(full_response)}

@router.post("/{bot_id}/chat/stream")
async def chat_with_bot_stream(bot_id: str, request_data: dict, authenticated_user: dict = Depends(get_authenticated_user)):
    user_message = request_data.get("message")
    chat_history_raw = request_data.get("chat_history", [])

    print(f"[CHAT/STREAM] Received bot_id={bot_id!r}")
    print(f"[CHAT/STREAM] authenticated_user role={authenticated_user.get('role')!r}  _id={authenticated_user.get('_id')!r}")

    try:
        obj_id = ObjectId(bot_id)
    except Exception as e:
        print(f"[CHAT/STREAM] Invalid ObjectId: {e}")
        raise HTTPException(status_code=404, detail="Bot not found")

    bot = await bots_collection.find_one({"_id": obj_id})
    print(f"[CHAT/STREAM] DB lookup result: {bot}")
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # --- PERMISSION LOGIC ---
    is_owner = str(bot.get("user_id")) == str(authenticated_user.get("_id"))
    is_recruiter = authenticated_user.get("role") == "recruiter"

    if not is_owner and not is_recruiter:
        raise HTTPException(status_code=403, detail="You do not have permission for this bot")
    # -----------------------------

    pipeline = RAGPipeline(bot_id=bot_id, user_id=str(bot["user_id"]), bot_name=bot["name"])

    # --- FIX: HANDLE ROLE VS TYPE MISMATCH ---
    chat_history = []
    for msg in chat_history_raw:
        role = msg.get("role") or msg.get("type")
        content = msg.get("content", "")
        
        if role == "user":
            chat_history.append(HumanMessage(content=content))
        else:
            chat_history.append(AIMessage(content=content))
    # -----------------------------------------

    import asyncio

    async def stream_generator():
        full_response = ""
        async for chunk in pipeline.get_response_stream(user_message, chat_history, bot_metadata=bot):
            full_response += chunk
            yield chunk
            
        # Background task for stateful interview tracking
        async def analyze_and_save():
            updated_history = chat_history + [
                HumanMessage(content=user_message), 
                AIMessage(content=full_response)
            ]
            assessment = await pipeline.analyze_interview(updated_history)
            if assessment:
                try:
                    recruiter_id = str(authenticated_user.get("_id"))
                    await bots_collection.update_one(
                        {"_id": obj_id},
                        {"$set": {f"assessments.{recruiter_id}": assessment}}
                    )
                except Exception as e:
                    print(f"Error saving assessment: {e}")

        asyncio.create_task(analyze_and_save())

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
    )

@router.get("/", response_model=List[Bot])
async def get_user_bots(current_user: User = Depends(get_current_user)):
    bots = await bots_collection.find({"user_id": str(current_user.id)}).to_list(100)
    return bots
    
@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(bot_id: str, current_user: User = Depends(get_current_user)):
    bot = await bots_collection.find_one({"_id": ObjectId(bot_id), "user_id": str(current_user.id)})
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

    await bots_collection.delete_one({"_id": ObjectId(bot_id)})
    user_data_dir = os.path.join("data", str(current_user.id), bot_id)
    if os.path.exists(user_data_dir):
        shutil.rmtree(user_data_dir)
    return

@router.patch("/{bot_id}", response_model=Bot)
async def update_bot(bot_id: str, bot_in: BotUpdate, current_user: User = Depends(get_current_user)):
    try:
        obj_id = ObjectId(bot_id)
    except Exception as e:
        print(f"Invalid bot ID in patch endpoint: {bot_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid bot ID")

    try:
        bot = await bots_collection.find_one({"_id": obj_id, "user_id": str(current_user.id)})
        if not bot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
            
        update_data = bot_in.model_dump(exclude_unset=True)
        await bots_collection.update_one({"_id": obj_id}, {"$set": update_data})
        updated_bot = await bots_collection.find_one({"_id": obj_id})
        return updated_bot
    except Exception as e:
        print(f"Error in update_bot: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal error updating bot: {str(e)}")

async def synthesize_speech(text: str, websocket: WebSocket):
    """Generates audio bytes using Edge TTS and sends via WebSocket"""
    try:
        # Check if the user is interrupted (basic implementations can just stream)
        voice = "en-US-ChristopherNeural"
        communicate = edge_tts.Communicate(text, voice)
        
        audio_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])
                
        # Convert full mp3 byte buffer to base64
        b64_audio = base64.b64encode(audio_buffer).decode("utf-8")
        
        # Send as a single JSON message
        await websocket.send_text(json.dumps({
            "event": "audio",
            "data": b64_audio
        }))
        
        # Send a special message to tell frontend the speech is done
        await websocket.send_text(json.dumps({"event": "speech_done"}))
    except Exception as e:
        print(f"TTS Error: {e}")
        await websocket.send_text(json.dumps({"event": "error", "message": f"TTS Error: {e}"}))

@router.websocket("/ws/{bot_id}/voice")
async def websocket_voice_endpoint(websocket: WebSocket, bot_id: str):
    await websocket.accept()
    print(f"Voice WebSocket connected for bot {bot_id}")
    
    try:
        obj_id = ObjectId(bot_id)
        bot = await bots_collection.find_one({"_id": obj_id})
        if not bot:
            await websocket.send_text(json.dumps({"event": "error", "message": "Bot not found"}))
            await websocket.close()
            return
            
        pipeline = RAGPipeline(bot_id=bot_id, user_id=str(bot["user_id"]), bot_name=bot["name"])
        
        await websocket.send_text(json.dumps({"event": "ready", "message": "Connected to Voice Interview."}))
        
        chat_history = []
        
        while True:
            audio_bytes = await websocket.receive_bytes()
            print(f"Received audio chunk: {len(audio_bytes)} bytes")
            
            if not groq_client:
                await websocket.send_text(json.dumps({"event": "error", "message": "Voice STT unavailable (Missing Groq Key)."}))
                continue

            await websocket.send_text(json.dumps({"event": "status", "message": "Transcribing..."}))

            # Save the binary audio to a temporary file since Whisper API needs a file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name
                
            try:
                # 1. Transcribe (STT)
                with open(temp_audio_path, "rb") as file:
                    transcription = await groq_client.audio.transcriptions.create(
                        file=(temp_audio_path, file.read()),
                        model="whisper-large-v3",
                        response_format="json",
                        temperature=0.0,
                        language="en" # Stop Whisper hallucinations
                    )
                
                user_text = transcription.text
                if not user_text.strip():
                    await websocket.send_text(json.dumps({"event": "status", "message": "Did not catch that. Hold to speak."}))
                    continue
                    
                await websocket.send_text(json.dumps({"event": "user_msg", "text": user_text}))
                await websocket.send_text(json.dumps({"event": "status", "message": "Thinking..."}))
                
                # 2. Get AI Response via the real RAG pipeline
                # Converting dict-like chat_history to LangChain messages
                lc_history = []
                for msg in chat_history[-10:]: # Limit context window to last 5 turns
                    if msg["role"] == "user":
                        lc_history.append(HumanMessage(content=msg["content"]))
                    else:
                        lc_history.append(AIMessage(content=msg["content"]))
                
                full_response = ""
                async for chunk in pipeline.get_response_stream(user_text, lc_history, bot_metadata=bot):
                    full_response += chunk
                    
                full_response = strip_think_tags(full_response)
                
                # Update history
                chat_history.append({"role": "user", "content": user_text})
                chat_history.append({"role": "assistant", "content": full_response})
                
                await websocket.send_text(json.dumps({"event": "ai_msg", "text": full_response}))
                await websocket.send_text(json.dumps({"event": "status", "message": "Speaking..."}))
                
                # 3. Text to Speech (TTS)
                await synthesize_speech(full_response, websocket)
                    
            finally:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                    
    except WebSocketDisconnect:
        print(f"Voice WebSocket disconnected for bot {bot_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_text(json.dumps({"event": "error", "message": f"Error: {str(e)}"}))
        except:
            pass