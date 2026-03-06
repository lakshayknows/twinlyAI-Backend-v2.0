# app/api/v1/endpoints/oauth.py

from fastapi import APIRouter, Request
from authlib.integrations.starlette_client import OAuth
from starlette.responses import RedirectResponse
from app.core.config import settings
from app.db.session import users_collection
from app.core.security import create_access_token

router = APIRouter()
oauth = OAuth()

oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

oauth.register(
    name='github',
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)

@router.get('/login/{provider}')
async def login_via_provider(request: Request, provider: str):
    # --- FIX: Dynamic Scheme for Localhost vs Prod ---
    host = request.headers['host']
    # If running on localhost, use http. Otherwise force https.
    if "localhost" in host or "127.0.0.1" in host:
        scheme = "http"
    else:
        scheme = "https"
        
    redirect_uri = f"{scheme}://{host}/api/v1/oauth/auth/{provider}"
    
    return await oauth.create_client(provider).authorize_redirect(request, redirect_uri)

@router.get('/auth/{provider}', name="auth_callback")
async def auth_callback(request: Request, provider: str):
    token = await oauth.create_client(provider).authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        resp = await oauth.github.get('user', token=token)
        user_info = resp.json()
        if not user_info.get('email'):
            emails = await oauth.github.get('user/emails', token=token)
            email_info = next((e for e in emails.json() if e['primary']), emails.json()[0])
            user_info['email'] = email_info['email']

    email = user_info['email']
    user = await users_collection.find_one({"email": email})

    if not user:
        # Create new user if not exists
        new_user = {
            "email": email, 
            "hashed_password": "",
            "role": "candidate" # Default role
        }
        await users_collection.insert_one(new_user)

    access_token = create_access_token(data={"sub": email, "role": user.get("role", "candidate") if user else "candidate"})
    
    # --- FIX: Dynamic Redirect to Frontend ---
    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/login?token={access_token}")
    return response