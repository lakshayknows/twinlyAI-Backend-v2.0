# app/api/v1/endpoints/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.user import User, UserUpdate
from app.api.v1.deps import get_current_user
from app.db.session import users_collection
from bson import ObjectId

router = APIRouter()

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Get current logged-in user.
    """
    return current_user

@router.put("/me", response_model=User)
async def update_user_me(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update current logged-in user.
    """
    update_data = user_in.model_dump(exclude_unset=True)
    if not update_data:
        return current_user

    await users_collection.update_one(
        {"_id": current_user.id},
        {"$set": update_data}
    )
    
    updated_user = await users_collection.find_one({"_id": current_user.id})
    return updated_user

@router.post("/upgrade-me", response_model=User)
async def upgrade_me(
    tier: str,
    current_user: User = Depends(get_current_user)
):
    """
    DEV-ONLY: Manually upgrade current user to a specific tier.
    """
    from app.core.config import settings
    if settings.ENV != "dev":
        raise HTTPException(status_code=403, detail="Only available in development mode")
    
    valid_tiers = ["free", "pro", "plus"]
    if tier not in valid_tiers:
        raise HTTPException(status_code=400, detail="Invalid tier. Must be one of {}".format(valid_tiers))

    await users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {"$set": {"subscription_tier": tier}}
    )
    
    updated_user = await users_collection.find_one({"_id": ObjectId(current_user.id)})
    
    # Sanitize for Pydantic (copy-paste from deps logic essentially)
    user_data = updated_user.copy()
    user_data["id"] = str(user_data["_id"])
    del user_data["_id"]
    if "hashed_password" in user_data: del user_data["hashed_password"]
    
    return User(**user_data)