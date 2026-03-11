import asyncio
import os
import sys
sys.path.append(os.getcwd())
from app.db.session import bots_collection

async def verify_cloud_urls():
    print("📋 Verifying Cloudinary Migration Results...")
    bots = await bots_collection.find({"resume_url": {"$regex": "cloudinary"}}).to_list(length=100)
    print("✅ Found %d bots with Cloudinary URLs." % len(bots))
    
    if bots:
        sample = bots[0]
        print("Sample: %s" % sample['name'])
        print("  - Resume: %s" % sample.get('resume_url'))
        print("  - Thumb : %s" % sample.get('thumbnail_url'))

if __name__ == "__main__":
    asyncio.run(verify_cloud_urls())
