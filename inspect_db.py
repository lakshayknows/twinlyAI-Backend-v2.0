import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys

async def main():
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        mongo_uri = os.getenv('MONGO_CONNECTION_STRING')
        if not mongo_uri:
            print("ERROR: MONGO_CONNECTION_STRING environment variable is not set.")
            return
        client = AsyncIOMotorClient(mongo_uri)
        db = client.twinlyai
        users = await db.users.find().to_list(10)
        for user in users:
            print("Email: %s" % user.get('email', 'N/A'))
            print("Role: %s" % user.get('role', 'N/A'))
            print("Has password: %s" % ('Yes' if user.get('hashed_password') else 'No'))
            print("---")
    except Exception:
        print("Error connecting to database.")

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
