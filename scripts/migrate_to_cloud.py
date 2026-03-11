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
    print("📄 Found %d candidates in database." % len(bots))
    
    storage_root = Path("data") / "seeded_resumes"
    processed = 0
    errors = 0
    
    for bot in bots:
        bot_id = str(bot["_id"])
        name = bot.get("name", "Unknown")
        
        # Determine local path
        local_pdf = storage_root / "{}.pdf".format(bot_id)
        
        if not local_pdf.exists():
            # Try another common path used in the app
            # (data/userId/botId/resume.pdf) - but seeding used seeded_resumes
            print("  ⚠️ Could not find local PDF for %s (%s) at %s" % (name, bot_id, local_pdf))
            continue
            
        print("  📤 Uploading resume for %s..." % name)
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
            print("  ❌ Error migrating %s" % name)
            errors += 1

    print("\n✅ MIGRATION COMPLETE!")
    print("Total processed: %d" % processed)
    print("Errors: %d" % errors)

if __name__ == "__main__":
    asyncio.run(migrate())
