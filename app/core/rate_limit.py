# app/core/rate_limit.py

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.core.config import settings

# Create a limiter that uses the remote IP address as the key
limiter = Limiter(
    key_func=get_remote_address,
    # In dev mode, we might want to disable rate limiting entirely or set very high limits
    enabled=settings.ENV != "dev"
)

def setup_rate_limiting(app):
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
