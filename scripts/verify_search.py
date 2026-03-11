import asyncio
import os
import sys
sys.path.append(os.getcwd())
from app.core.rag_pipeline import GlobalRecruiterIndex
from app.db.session import bots_collection

async def verify_search():
    index = GlobalRecruiterIndex()
    
    test_queries = [
        "Python developer from Galgotias",
        "Full-stack engineer with React and Node.js",
        "Highly motivated student from NIET Greater Noida",
        "Expert in distributed chat applications",
        "Candidates from IIT Bombay"
    ]
    
    print("🔍 Testing Global Search Relevance...")
    for query in test_queries:
        print("\nQuery: '%s'" % query)
        bot_ids = index.semantic_search(query, k=5)
        
        if not bot_ids:
            print("  ❌ No results found.")
            continue
            
        print("  ✅ Found %d results." % len(bot_ids))
        # Fetch names from DB
        for b_id in bot_ids:
            try:
                from bson import ObjectId
                bot = await bots_collection.find_one({"_id": ObjectId(b_id)})
                if bot:
                    print("    - %s (%s...)" % (bot['name'], bot.get('skills', [])[:3]))
            except Exception as e:
                print("    - Error fetching bot %s" % b_id)

if __name__ == "__main__":
    asyncio.run(verify_search())
