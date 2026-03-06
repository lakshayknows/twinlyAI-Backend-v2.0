# app/core/agora_token.py

import time
from agora_token_builder import RtcTokenBuilder
from app.core.config import settings
from fastapi import HTTPException, status

# Set token expiration time to 1 hour
TOKEN_EXPIRATION_IN_SECONDS = 3600
ROLE_PUBLISHER = 1

def generate_agora_token(channel_name: str, user_uid: int):
    """
    Generates an Agora RTC token for a user.
    """
    app_id = settings.AGORA_APP_ID
    app_certificate = settings.AGORA_APP_CERTIFICATE

    if not app_id or not app_certificate:
        print("ERROR: AGORA_APP_ID or AGORA_APP_CERTIFICATE not found in .env or secrets")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agora credentials are not configured on the server."
        )

    try:
        current_timestamp = int(time.time())
        expire_timestamp = current_timestamp + TOKEN_EXPIRATION_IN_SECONDS

        # --- THIS IS THE FIX ---
        # The function only takes 6 arguments. The 7th (duplicate) argument has been removed.
        token = RtcTokenBuilder.buildTokenWithUid(
            app_id,
            app_certificate,
            channel_name,
            user_uid,
            ROLE_PUBLISHER,
            expire_timestamp  # This is the privilegeExpiredTs
        )
        # --- END OF FIX ---
        
        return token
    except Exception as e:
        print(f"Error generating Agora token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Agora token: {e}"
        )