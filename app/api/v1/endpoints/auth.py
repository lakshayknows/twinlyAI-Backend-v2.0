from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas.user import UserCreate, User
from app.db.session import users_collection
from app.core.security import get_password_hash, verify_password, create_access_token
from pymongo.errors import DuplicateKeyError

router = APIRouter()

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate):
    """
    Create a new user.
    """
    hashed_password = get_password_hash(user_in.password)
    
    # Create the user document with the role
    user_doc = {
        "email": user_in.email,
        "hashed_password": hashed_password,
        "role": user_in.role  # Ensure role is saved to DB
    }
    
    try:
        await users_collection.insert_one(user_doc)
        return {"message": "User created successfully"}
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Signup processing error: {str(e)}")

@router.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return a JWT token.
    """
    try:
        user = await users_collection.find_one({"email": form_data.username})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        if not user.get("hashed_password"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This email was registered via Google/GitHub. Please use the login page and sign in with your provider.",
            )

        if not verify_password(form_data.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Optionally include role in the token claims if needed later
        access_token = create_access_token(data={"sub": user["email"], "role": user.get("role", "candidate")})
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login processing error: {str(e)}")