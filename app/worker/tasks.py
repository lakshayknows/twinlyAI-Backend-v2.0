import asyncio
import httpx
import base64
from datetime import datetime
from bs4 import BeautifulSoup
import re
from celery import shared_task

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.security import decrypt_token
from app.db.session import connectors_collection, connector_sources_collection, connector_documents_collection
from app.core.rag_pipeline import get_embeddings_model
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

# File extension mappings for Langchain chunking
LANGUAGE_MAP = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".java": Language.JAVA,
    ".go": Language.GO,
    ".cpp": Language.CPP,
    ".md": Language.MARKDOWN,
}

VALID_EXTENSIONS = tuple(LANGUAGE_MAP.keys())
EXCLUDED_DIRS = ("node_modules", "dist", "build", "venv", ".git", "coverage", ".venv")

@shared_task(name="app.worker.tasks.ingest_github_repo")
def ingest_github_repo(user_id: str, repo_name: str):
    """
    Celery task to ingest a GitHub repository async.
    """
    # Create event loop for async operations
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(_ingest_github_repo_async(user_id, repo_name))
    return f"Index of {repo_name} completed."

async def _ingest_github_repo_async(user_id: str, repo_name: str):
    # 1. Fetch credentials
    connector = await connectors_collection.find_one({"user_id": user_id, "connector_type": "github"})
    if not connector:
        return
        
    token = decrypt_token(connector["encrypted_access_token"])
    
    # Create or update source record
    source_record = {
        "connector_id": str(connector["_id"]),
        "source_name": repo_name,
        "sync_status": "indexing",
        "updated_at": datetime.utcnow()
    }
    
    await connector_sources_collection.update_one(
        {"connector_id": str(connector["_id"]), "source_name": repo_name},
        {"$set": source_record, "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True
    )
    
    source = await connector_sources_collection.find_one({"connector_id": str(connector["_id"]), "source_name": repo_name})
    source_id = str(source["_id"])
    
    docs = []
    
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TwinlyAI-Worker"
        }
        
        # 2. Get repository default branch
        repo_url = f"https://api.github.com/repos/{repo_name}"
        repo_resp = await client.get(repo_url, headers=headers)
        if repo_resp.status_code != 200:
            await _mark_status(source_id, "error")
            return
            
        repo_data = repo_resp.json()
        default_branch = repo_data.get("default_branch", "main")
        size_kb = repo_data.get("size", 0)
        
        # Soft limit checking: > 50MB
        smart_indexing = size_kb > 50000 
        
        # 3. Get tree recursively
        tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{default_branch}?recursive=1"
        tree_resp = await client.get(tree_url, headers=headers)
        
        if tree_resp.status_code != 200:
            await _mark_status(source_id, "error")
            return
            
        tree = tree_resp.json().get("tree", [])
        
        filtered_files = []
        for item in tree:
            if item["type"] != "blob": continue
            path = item["path"]
            
            # Explicit Exclusions
            if any(path.startswith(d + "/") or f"/{d}/" in path for d in EXCLUDED_DIRS):
                continue
            if path.endswith((".lock", ".min.js", ".png", ".jpg", ".jpeg", ".ico")):
                continue
                
            # Smart Indexing (for very large repos) vs Full Indexing
            if smart_indexing:
                if path.endswith(".md") or path.startswith("src/") or path in ["package.json", "requirements.txt"]:
                    filtered_files.append(item)
            else:
                if path.endswith(VALID_EXTENSIONS):
                    filtered_files.append(item)
                    
        # Truncate if too many files
        if len(filtered_files) > 2000:
            filtered_files = filtered_files[:2000]
            
        # 4. Fetch contents and chunk
        qdrant_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        embeddings = get_embeddings_model()
        collection_name = f"candidate_{user_id}_source_github"
        
        # Create collection if not exists
        if not qdrant_client.collection_exists(collection_name):
            try:
                # Initialize empty vector store to auto-create collection
                QdrantVectorStore.from_documents([], embeddings, url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, collection_name=collection_name)
            except:
                pass
                
        # Batch fetching to adhere to rate limits (simple approach stringing max concurrent)
        for i in range(0, len(filtered_files), 10):
            batch = filtered_files[i:i+10]
            tasks = [fetch_file_content(client, repo_name, default_branch, f["path"]) for f in batch]
            results = await asyncio.gather(*tasks)
            
            for f, content in zip(batch, results):
                if not content: continue
                
                # Create LangChain Document
                path = f["path"]
                ext = "." + path.split(".")[-1] if "." in path else ""
                lang = LANGUAGE_MAP.get(ext)
                
                if lang:
                    splitter = RecursiveCharacterTextSplitter.from_language(
                        language=lang, chunk_size=800, chunk_overlap=100
                    )
                else:
                    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
                    
                chunks = splitter.split_text(content)
                
                # Embed & Insert
                for chunk in chunks:
                    metadata = {
                        "candidate_id": user_id,
                        "connector_type": "github",
                        "source_id": source_id,
                        "repo_name": repo_name,
                        "file_path": path,
                        "language": ext[1:] if ext else "unknown",
                        "chunk_type": "code" if ext != ".md" else "readme"
                    }
                    
                    doc = Document(page_content=chunk, metadata=metadata)
                    QdrantVectorStore.from_documents([doc], embeddings, url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, collection_name=collection_name)
                    
                    metadata["created_at"] = datetime.utcnow()
                    await connector_documents_collection.insert_one(metadata)
        
        # Fetch generic commits if any
        await fetch_commits(client, repo_name, user_id, source_id, collection_name, embeddings)
        
    await _mark_status(source_id, "completed")

async def fetch_file_content(client, repo_name, branch, path):
    url = f"https://raw.githubusercontent.com/{repo_name}/{branch}/{path}"
    resp = await client.get(url)
    if resp.status_code == 200:
        return resp.text
    return None

async def fetch_commits(client, repo_name, user_id, source_id, collection_name, embeddings):
    url = f"https://api.github.com/repos/{repo_name}/commits?per_page=200"
    resp = await client.get(url)
    if resp.status_code != 200: return
    
    commits = resp.json()
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    
    for c in commits:
        msg = c.get("commit", {}).get("message", "")
        sha = c.get("sha", "")
        if not msg: continue
        
        chunks = splitter.split_text(msg)
        for chunk in chunks:
            metadata = {
                "candidate_id": user_id,
                "connector_type": "github",
                "source_id": source_id,
                "repo_name": repo_name,
                "file_path": "commit_log",
                "language": "text",
                "chunk_type": "commit",
                "commit_sha": sha,
                "created_at": datetime.utcnow()
            }
            doc = Document(page_content=f"Commit [{sha}]:\n{chunk}", metadata=metadata)
            QdrantVectorStore.from_documents([doc], embeddings, url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, collection_name=collection_name)
            await connector_documents_collection.insert_one(metadata)

async def _mark_status(source_id: str, status: str):
    from bson import ObjectId
    await connector_sources_collection.update_one(
        {"_id": ObjectId(source_id)},
        {"$set": {"sync_status": status, "updated_at": datetime.utcnow(), "last_synced_at": datetime.utcnow() if status == "completed" else None}}
    )
