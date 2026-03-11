# app/api/v1/endpoints/recruiter.py

import logging
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

    except Exception:
        logging.exception("Error fetching candidates")
        raise HTTPException(status_code=500, detail="Error fetching candidates.")

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
        # 1. Run vector semantic search (now raises RuntimeError on failure instead of silent [])
        global_index = GlobalRecruiterIndex()
        matching_bot_ids = global_index.semantic_search(search_request.query, k=10)

    except RuntimeError as e:
        # Vector search failed (HuggingFace API down / Qdrant issue).
        # Fall back to MongoDB text search so recruiters always get results.
        logging.warning("[/search] Vector search failed, falling back to MongoDB text search: %s", type(e).__name__)
        try:
            query_words = search_request.query.strip().split()
            regex_pattern = "|".join(query_words)
            fallback_cursor = bots_collection.find({
                "$or": [
                    {"name": {"$regex": regex_pattern, "$options": "i"}},
                    {"summary": {"$regex": regex_pattern, "$options": "i"}},
                    {"skills": {"$elemMatch": {"$regex": regex_pattern, "$options": "i"}}},
                ]
            })
            fallback_candidates = await fallback_cursor.to_list(20)
            formatted_fallback = []
            for res in fallback_candidates:
                skills_list = res.get("skills", [])
                if not isinstance(skills_list, list):
                    skills_list = []
                formatted_fallback.append({
                    "id": str(res["_id"]),
                    "name": res.get("name", "Unknown Candidate"),
                    "match_score": 0,
                    "skills": skills_list,
                    "summary": res.get("summary", "No summary available."),
                    "experience_years": res.get("experience_years", 0),
                    "resume_url": res.get("resume_url"),
                    "thumbnail_url": res.get("thumbnail_url"),
                    "avatar_url": res.get("avatar_url")
                })
            return formatted_fallback
        except Exception as fallback_err:
            logging.exception("[/search] MongoDB fallback also failed")
            raise HTTPException(status_code=500, detail="Search is currently unavailable.")

    except Exception:
        logging.exception("[/search] Unexpected error")
        raise HTTPException(status_code=500, detail="Error performing search.")

    try:
        if not matching_bot_ids:
            return []

        # 2. Fetch full documents from MongoDB using matched bot_ids
        bot_object_ids = [ObjectId(bid) for bid in matching_bot_ids]
        candidates_cursor = bots_collection.find({"_id": {"$in": bot_object_ids}})
        candidates = await candidates_cursor.to_list(100)

        # 3. Format results, preserving relevance order from vector search
        candidates_map = {str(c["_id"]): c for c in candidates}
        formatted_results = []

        for bid in matching_bot_ids:
            res = candidates_map.get(bid)
            if not res:
                continue

            skills_list = res.get("skills", [])
            if not isinstance(skills_list, list):
                skills_list = []

            formatted_results.append({
                "id": str(res["_id"]),
                "name": res.get("name", "Unknown Candidate"),
                "match_score": 0,
                "skills": skills_list,
                "summary": res.get("summary", "No summary available."),
                "experience_years": res.get("experience_years", 0),
                "resume_url": res.get("resume_url"),
                "thumbnail_url": res.get("thumbnail_url"),
                "avatar_url": res.get("avatar_url")
            })

        return formatted_results

    except Exception:
        logging.exception("[/search] MongoDB fetch error")
        raise HTTPException(status_code=500, detail="Error fetching candidate details.")