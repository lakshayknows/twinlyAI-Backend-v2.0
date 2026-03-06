import os
import asyncio
from pathlib import Path
from bson import ObjectId
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.config import settings
from app.db.session import bots_collection
from app.core.storage import StorageService

async def migrate():
    print("☁️ Starting Cloudinary Migration...")
    
    if settings.STORAGE_TYPE != "cloudinary":
        print("❌ STORAGE_TYPE is not set to 'cloudinary'. Please update your .env file.")
        return

    # 1. Fetch all bots from MongoDB
    bots = await bots_collection.find({}).to_list(length=1000)
    print(f"📄 Found {len(bots)} candidates in database.")
    
    storage_root = Path("data") / "seeded_resumes"
    processed = 0
    errors = 0
    
    for bot in bots:
        bot_id = str(bot["_id"])
        name = bot.get("name", "Unknown")
        
        # Determine local path
        local_pdf = storage_root / f"{bot_id}.pdf"
        
        if not local_pdf.exists():
            # Try another common path used in the app
            # (data/userId/botId/resume.pdf) - but seeding used seeded_resumes
            print(f"  ⚠️ Could not find local PDF for {name} ({bot_id}) at {local_pdf}")
            continue
            
        print(f"  📤 Uploading resume for {name}...")
        try:
            pdf_url, thumb_url = StorageService.upload_file(
                str(local_pdf), 
                public_id=bot_id, 
                folder="twinly_resumes"
            )
            
            # 2. Update MongoDB with the new URLs
            await bots_collection.update_one(
                {"_id": bot["_id"]},
                {"$set": {
                    "resume_url": pdf_url,
                    "thumbnail_url": thumb_url
                }}
            )
            processed += 1
        except Exception as e:
            print(f"  ❌ Error migrating {name}: {e}")
            errors += 1

    print(f"\n✅ MIGRATION COMPLETE!")
    print(f"Total processed: {processed}")
    print(f"Errors: {errors}")

if __name__ == "__main__":
    asyncio.run(migrate())
