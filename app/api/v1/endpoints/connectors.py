from fastapi import APIRouter, Depends, Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from starlette.responses import RedirectResponse
import httpx
from datetime import datetime
from app.core.config import settings
from app.db.session import connectors_collection, connector_sources_collection
from app.core.security import encrypt_token, decrypt_token
from app.api.v1.deps import get_current_user
from app.schemas.user import User
from app.worker.tasks import ingest_github_repo
import hmac
import hashlib

router = APIRouter()
oauth = OAuth()

oauth.register(
    name='github_connector',
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'read:user repo'},
)

@router.get('/github/authorize')
async def authorize_github_connector(request: Request, current_user: User = Depends(get_current_user)):
    """
    Start the OAuth flow for connecting the candidate's GitHub account.
    We request `read:user` and `repo` scopes.
    """
    host = request.headers['host']
    if "localhost" in host or "127.0.0.1" in host:
        scheme = "http"
    else:
        scheme = "https"
        
    redirect_uri = "{}://{}/api/v1/connectors/github/callback".format(scheme, host)
    
    # Store user_id in session to link the OAuth callback to the correct user securely
    request.session['connector_setup_user_id'] = current_user.id
    
    return await oauth.create_client('github_connector').authorize_redirect(request, redirect_uri)

@router.get('/github/callback')
async def github_connector_callback(request: Request):
    """
    Handle the callback from GitHub OAuth, securely store the access token as an encrypted string,
    and update the user's connector status.
    """
    user_id = request.session.get('connector_setup_user_id')
    if not user_id:
        raise HTTPException(status_code=400, detail="User session not found. Please try again.")

    client = oauth.create_client('github_connector')
    token = await client.authorize_access_token(request)
    
    access_token = token.get('access_token')
    if not access_token:
         raise HTTPException(status_code=400, detail="Failed to get access token from GitHub")
         
    # Encrypt token before storing
    encrypted_token = encrypt_token(access_token)
    
    # Update or insert into connectors collection
    connector_data = {
        "user_id": user_id,
        "connector_type": "github",
        "encrypted_access_token": encrypted_token,
        "status": "connected",
        "updated_at": datetime.utcnow()
    }
    
    await connectors_collection.update_one(
        {"user_id": user_id, "connector_type": "github"},
        {"$set": connector_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True
    )
    
    # Clean up session
    del request.session['connector_setup_user_id']
    
    return RedirectResponse(url="{}/dashboard/connectors?status=success".format(settings.FRONTEND_URL))

@router.get('/')
async def list_connectors(current_user: User = Depends(get_current_user)):
    """
    List all connected integrations for the current candidate logging in.
    """
    cursor = connectors_collection.find({"user_id": current_user.id})
    connectors = await cursor.to_list(length=100)
    
    result = []
    for c in connectors:
        c["id"] = str(c["_id"])
        del c["_id"]
        # Do not return the encrypted token to the frontend
        if "encrypted_access_token" in c:
            del c["encrypted_access_token"]
        result.append(c)
        
    return {"connectors": result}

@router.get('/github/repositories')
async def list_github_repositories(current_user: User = Depends(get_current_user)):
    """
    Fetch the list of repositories available for the connected GitHub account.
    We retrieve the token from the DB, decrypt it, and query the GitHub API.
    """
    connector = await connectors_collection.find_one({"user_id": current_user.id, "connector_type": "github"})
    if not connector or not connector.get("encrypted_access_token"):
        raise HTTPException(status_code=404, detail="GitHub connector not configured.")

    token = decrypt_token(connector["encrypted_access_token"])
    
    # Use httpx to query GitHub API for user repos
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": "Bearer {}".format(token),
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TwinlyAI-Connector"
        }
        
        url = "https://api.github.com/user/repos?per_page=100&sort=updated"
        response = await client.get(url, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch repositories from GitHub.")
            
        repos = response.json()
        
    # Format for the frontend
    repo_list = [
        {
            "id": r["id"],
            "name": r["full_name"],
            "description": r["description"],
            "url": r["html_url"],
            "private": r["private"],
            "size_kb": r["size"]
        } for r in repos
    ]
    
    return {"repositories": repo_list}

@router.post('/github/repositories/{owner}/{repo}/sync')
async def sync_github_repository(owner: str, repo: str, current_user: User = Depends(get_current_user)):
    """
    Trigger a background Celery task to asynchronously ingest the repository.
    """
    connector = await connectors_collection.find_one({"user_id": current_user.id, "connector_type": "github"})
    if not connector:
        raise HTTPException(status_code=404, detail="GitHub connector not configured.")

    repo_name = "{}/{}".format(owner, repo)
    
    # Check if a webhook exists, if not, create one using their token (omitted for brevity, assume manual or standard)
    
    # Fire off Celery Task
    ingest_github_repo.delay(current_user.id, repo_name)
    
    return {"message": "Sync started for {}".format(repo_name), "status": "indexing"}

@router.post('/github/webhooks/callback')
async def github_webhook_callback(request: Request):
    """
    Handles push events from GitHub to keep the twin updated.
    """
    payload = await request.body()
    signature = request.headers.get('x-hub-signature-256')
    event_type = request.headers.get('x-github-event')
    
    if not signature or event_type != "push":
        return {"message": "Ignored"}
        
    # Example logic:
    # 1. Look up the repository from payload JSON
    body_json = await request.json()
    repo_name = body_json.get("repository", {}).get("full_name")
    
    if not repo_name:
        return {"message": "Invalid payload"}

    # Find which users have this repo as a source
    sources = await connector_sources_collection.find({"source_name": repo_name}).to_list(length=100)
    for source in sources:
        # Find associated connector to get user_id
        from bson import ObjectId
        connector = await connectors_collection.find_one({"_id": ObjectId(source["connector_id"])})
        if connector:
            user_id = connector["user_id"]
            # Trigger ingestion task for each user that tracks this repo
            ingest_github_repo.delay(user_id, repo_name)
            
    return {"message": "Webhook processed successfully"}
