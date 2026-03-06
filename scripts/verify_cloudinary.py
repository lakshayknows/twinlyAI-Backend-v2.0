import asyncio
import os
import sys
sys.path.append(os.getcwd())
from app.db.session import bots_collection

async def verify_cloud_urls():
    print("📋 Verifying Cloudinary Migration Results...")
    bots = await bots_collection.find({"resume_url": {"$regex": "cloudinary"}}).to_list(length=100)
    print(f"✅ Found {len(bots)} bots with Cloudinary URLs.")
    
    if bots:
        sample = bots[0]
        print(f"Sample: {sample['name']}")
        print(f"  - Resume: {sample.get('resume_url')}")
        print(f"  - Thumb : {sample.get('thumbnail_url')}")

if __name__ == "__main__":
    asyncio.run(verify_cloud_urls())
