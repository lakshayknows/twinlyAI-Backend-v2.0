# app/core/voice_agent.py

import asyncio
import time
import edge_tts
import re
from agora_token_builder import RtcTokenBuilder
# --- THIS IS THE FIX: Correct imports from the 'agorartc' module ---
import agorartc
# --- END OF FIX ---
from app.core.config import settings
from app.core.rag_pipeline import RAGPipeline
from groq import Groq
import threading
import os

# --- Configuration ---
AGORA_APP_ID = settings.AGORA_APP_ID
AGORA_APP_CERTIFICATE = settings.AGORA_APP_CERTIFICATE
GROQ_API_KEY = settings.GROQ_API_KEY

TOKEN_EXPIRATION_IN_SECONDS = 3600
ROLE_PUBLISHER = 1

# --- TTS Configuration ---
TTS_VOICE = "en-US-JennyNeural"
TTS_OUTPUT_FILE = "response.mp3"

# --- Groq STT Client ---
stt_client = Groq(api_key=GROQ_API_KEY)


# --- FIX: Subclass the correct event handler base ---
class VoiceAgentEventHandler(agorartc.RtcEngineEventHandlerBase):
    """
    Handles events from the Agora RTC Engine for the AI Bot.
    """
    def __init__(self, agent):
        super().__init__()
        self.agent = agent

    def onJoinChannelSuccess(self, channel, uid, elapsed):
        print(f"AI Agent joined channel '{channel}' with UID {uid}")
        self.agent.is_joined = True

    def onLeaveChannel(self, stats):
        print(f"AI Agent left channel")
        self.agent.is_joined = False

    def onUserJoined(self, uid, elapsed):
        print(f"Recruiter (UID: {uid}) joined the call.")
        self.agent.recruiter_uid = uid
        # The AI will now start listening to this user

    def onUserOffline(self, uid, reason):
        print(f"Recruiter (UID: {uid}) left the call.")
        self.agent.recruiter_uid = None
        # Once the recruiter leaves, the AI should also leave
        asyncio.run(self.agent.leave_call()) # Run async leave
        
    # NOTE: The Python SDK's audio frame handling is complex.
    # We will continue to SIMULATE the STT part for now,
    # as onAudioFrame is not as straightforward as in the JS SDK.

class VoiceAgent:
    """
    Manages the AI Bot's lifecycle in a voice call.
    """
    def __init__(self, bot_id: str, user_id: str, bot_name: str):
        self.bot_id = bot_id
        self.user_id = user_id
        self.bot_name = bot_name
        self.channel_name = bot_id # Use bot_id as the channel
        
        self.is_joined = False
        self.is_processing = False
        self.recruiter_uid = None
        
        # 1. Initialize RAG Pipeline
        self.rag_pipeline = RAGPipeline(bot_id, user_id, bot_name)
        
        # 2. Initialize Agora Engine
        # --- FIX: Use the correct Agora SDK methods ---
        self.rtc_engine = agorartc.createRtcEngineBridge()
        self.event_handler = VoiceAgentEventHandler(self)
        context = agorartc.RtcEngineContext()
        context.appId = AGORA_APP_ID
        context.eventHandler = self.event_handler
        # Disabling audio/video by default for the bot
        context.enableAudioDevice = False 
        context.enableVideo = False

        self.rtc_engine.initialize(context)
        self.rtc_engine.setClientRole(agorartc.CLIENT_ROLE_TYPE.CLIENT_ROLE_BROADCASTER)
        # --- END OF FIX ---
        
        # 3. Start a separate thread to process audio
        self.processing_thread = threading.Thread(target=self.process_audio_buffer, daemon=True)
        self.processing_thread.start()

    def generate_token(self, uid):
        """Generates a token for the AI bot itself."""
        current_timestamp = int(time.time())
        expire_timestamp = current_timestamp + TOKEN_EXPIRATION_IN_SECONDS
        
        return RtcTokenBuilder.buildTokenWithUid(
            AGORA_APP_ID, AGORA_APP_CERTIFICATE, self.channel_name, uid,
            ROLE_PUBLISHER, expire_timestamp
        )

    async def join_call(self):
        """Connects the AI bot to the Agora channel."""
        ai_uid = 0 # AI bot joins as UID 0 by convention
        token = self.generate_token(uid=ai_uid)
        
        # --- FIX: Use the correct Agora SDK methods ---
        options = agorartc.ChannelMediaOptions()
        options.autoSubscribeAudio = True
        options.autoSubscribeVideo = False
        options.publishMicrophoneTrack = False 
        options.publishCustomAudioTrack = True # We will simulate pushing audio
        
        self.rtc_engine.joinChannel(token, self.channel_name, ai_uid, options)
        # --- END OF FIX ---
        print(f"AI Agent '{self.bot_name}' attempting to join channel: {self.channel_name}")
        
    async def leave_call(self):
        """Disconnects the AI bot from the Agora channel."""
        self.rtc_engine.leaveChannel()
        self.is_joined = False

    def process_audio_buffer(self):
        """
        A background thread that checks the audio buffer,
        transcribes it, gets an AI response, and speaks it.
        """
        
        async def run_async_pipeline(transcription):
            # 3. Get RAG Response
            response_text = ""
            async for chunk in self.rag_pipeline.get_response_stream(transcription, []):
                response_text += chunk
            
            clean_response = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
            print(f"AI Bot: {clean_response}")

            # 4. Text-to-Speech (TTS)
            try:
                communicate = edge_tts.Communicate(clean_response, TTS_VOICE)
                await communicate.save(TTS_OUTPUT_FILE)
                return clean_response
            except Exception as e:
                print(f"TTS Error: {e}")
                return None
        
        while True:
            # This loop will now just simulate the conversation
            # since the real audio processing is complex.
            time.sleep(10) # Wait 10 seconds between "responses"
            if not self.is_joined or self.is_processing:
                continue

            self.is_processing = True
            
            # --- 1. SIMULATE STT ---
            simulated_transcription = "What are your key skills?"
            print(f"Recruiter (simulated): {simulated_transcription}")
            
            # --- 2 & 3. Run Async RAG + TTS ---
            try:
                clean_response = asyncio.run(run_async_pipeline(simulated_transcription))
                if not clean_response:
                    self.is_processing = False
                    continue
            except Exception as e:
                print(f"Async pipeline error: {e}")
                self.is_processing = False
                continue
            
            # --- 4. Publish AI Audio to Channel (Simulated) ---
            print(f"AI Bot: (Speaking audio from {TTS_OUTPUT_FILE})")
            
            # This simulates the time it takes to "speak" the response.
            time.sleep(len(clean_response.split()) / 3.0)
            print("AI Bot: (Finished speaking)")
            
            if os.path.exists(TTS_OUTPUT_FILE):
                os.remove(TTS_OUTPUT_FILE)
                
            self.is_processing = False