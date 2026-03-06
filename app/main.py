# app/main.py

from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.api.v1.endpoints import auth, bots, api_keys, users, oauth, recruiter
from app.api.v1.endpoints import webhooks
from app.core.rate_limit import setup_rate_limiting
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
import logging

app = FastAPI(
    title="TwinlyAI API",
    description="API for the TwinlyAI SaaS application.",
    version="0.1.0"
)

# --- Production Error Masking ---
if settings.ENV != "dev":
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logging.error(f"Unhandled error: {str(exc)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred. Please contact support."}
        )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"Validation error details: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

setup_rate_limiting(app)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY
)

# --- FIX: Updated CORS Middleware ---
if settings.FRONTEND_URL:
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://localhost:8000", # Backend itself (Swagger UI)
        "http://127.0.0.1:8000",
        settings.FRONTEND_URL
    ]
else:
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Include Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(bots.router, prefix="/api/v1/bots", tags=["bots"])
app.include_router(api_keys.router, prefix="/api/v1/api-keys", tags=["api_keys"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(oauth.router, prefix="/api/v1/auth", tags=["oauth"])
app.include_router(recruiter.router, prefix="/api/v1/recruiter", tags=["recruiter"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])

@app.get("/")
async def root():
    return {"message": "Welcome to TwinlyAI API"}