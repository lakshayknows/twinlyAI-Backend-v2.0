from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ConnectorBase(BaseModel):
    user_id: str
    connector_type: str  # e.g. "github", "notion"
    status: str = "connected"  # connected, syncing, error, disconnected, revoked

class ConnectorCreate(ConnectorBase):
    access_token: str

class ConnectorResponse(ConnectorBase):
    id: str
    created_at: datetime
    updated_at: datetime

# --- Sources ---
class ConnectorSourceBase(BaseModel):
    connector_id: str
    source_name: str # e.g. "KurianJose7586/twinlyAI-Backend-v2.0"
    sync_status: str = "pending" # pending, indexing, completed, failed, retrying

class ConnectorSourceCreate(ConnectorSourceBase):
    pass

class ConnectorSourceResponse(ConnectorSourceBase):
    id: str
    webhook_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: Optional[datetime] = None

# --- Documents Metadata (used in vector db or separate collection) ---
class ConnectorDocument(BaseModel):
    candidate_id: str
    connector_type: str
    source_id: str
    repo_name: Optional[str] = None
    file_path: Optional[str] = None
    language: Optional[str] = None
    chunk_type: Optional[str] = None # function, class, readme
    commit_sha: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
