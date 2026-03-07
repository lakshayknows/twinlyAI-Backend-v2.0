# app/api/v1/endpoints/recruiter.py

from fastapi import APIRouter, Depends, HTTPException, Request
from app.db.session import bots_collection
from app.schemas.bot import Bot
from app.api.v1.deps import get_current_user, check_tier
from app.schemas.user import User
from typing import List
from bson import ObjectId
from pydantic import BaseModel

# Import the Global Index for Semantic Search
from app.core.rag_pipeline import GlobalRecruiterIndex
from app.core.rate_limit import limiter

router = APIRouter()

class SearchRequest(BaseModel):
    query: str

@router.get("/candidates")
async def get_all_candidates(
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "recruiter":
        raise HTTPException(status_code=403, detail="Only recruiters can view candidates")

    try:
        candidates_cursor = bots_collection.find()
        candidates = await candidates_cursor.to_list(100)

        formatted_results = []
        
        for idx, res in enumerate(candidates):
            skills_list = res.get("skills", [])
            
            if not isinstance(skills_list, list):
                skills_list = [] 

            formatted_results.append({
                "id": str(res["_id"]),
                "name": res.get("name", "Unknown Candidate"),
                # Optional placeholder match score for default view
                "match_score": max(70, 99 - idx * 3) if False else 0, # Note: using 0 since python has no Math.max default this way simply
                "skills": skills_list, 
                "summary": res.get("summary", "No summary available."),
                "experience_years": res.get("experience_years", 0),
                "resume_url": res.get("resume_url"),
                "thumbnail_url": res.get("thumbnail_url"),
                "avatar_url": res.get("avatar_url")
            })
            
        return formatted_results

    except Exception as e:
        print(f"Fetch Error: {str(e)}") 
        raise HTTPException(status_code=500, detail=f"Error fetching candidates: {str(e)}")

@router.post("/search")
@limiter.limit("20/minute")
async def search_candidates(
    request: Request,
    search_request: SearchRequest,  
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "recruiter":
        raise HTTPException(status_code=403, detail="Only recruiters can search candidates")

    if not search_request.query.strip():
        return []

    try:
        # 1. Initialize Index and Run Vector Search
        # Note: This returns a list of ID strings (e.g. ['60d5...', '60d6...'])
        global_index = GlobalRecruiterIndex()
        matching_bot_ids = global_index.semantic_search(search_request.query, k=10)

        if not matching_bot_ids:
            return []

        # 2. Fetch Full Documents from MongoDB
        # We need to convert string IDs to ObjectIds for the DB query
        bot_object_ids = [ObjectId(bid) for bid in matching_bot_ids]
        
        candidates_cursor = bots_collection.find({"_id": {"$in": bot_object_ids}})
        candidates = await candidates_cursor.to_list(100)

        # 3. Format the results safely
        formatted_results = []
        
        # Helper map to preserve search order (relevance)
        candidates_map = {str(c["_id"]): c for c in candidates}

        for bid in matching_bot_ids:
            res = candidates_map.get(bid)
            if not res:
                continue

            # --- FIX: Use .get() to avoid 'skills' KeyError ---
            skills_list = res.get("skills", [])
            
            # Ensure skills is actually a list (handle None or strings)
            if not isinstance(skills_list, list):
                skills_list = [] 

            formatted_results.append({
                "id": str(res["_id"]),
                "name": res.get("name", "Unknown Candidate"),
                # 'score' might not be available from Mongo, 
                # usually vector engines return it separately. 
                # For now we can omit it or set a default.
                "match_score": 0, 
                "skills": skills_list,  # Safe access
                "summary": res.get("summary", "No summary available."),
                "experience_years": res.get("experience_years", 0),
                "resume_url": res.get("resume_url"),
                "thumbnail_url": res.get("thumbnail_url"),
                "avatar_url": res.get("avatar_url")
            })
            
        return formatted_results

    except Exception as e:
        print(f"Search Error: {str(e)}") # Print to console for debugging
        raise HTTPException(status_code=500, detail=f"Error performing semantic search: {str(e)}")