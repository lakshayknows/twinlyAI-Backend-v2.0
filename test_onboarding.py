import httpx
import asyncio
import os

# Test credentials loaded from environment variables (never hardcode)
TEST_EMAIL = os.environ.get("TEST_USER_EMAIL", "test4@test.com")
TEST_PASSWORD = os.environ.get("TEST_USER_PASSWORD")

async def test_onboarding():
    if not TEST_PASSWORD:
        print("ERROR: TEST_USER_PASSWORD environment variable is not set.")
        print("Set it before running tests, e.g.: set TEST_USER_PASSWORD=YourSecurePassword")
        return

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as client:
        print("Testing signup...")
        res = await client.post("/api/v1/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "role": "candidate"})
        print("Signup: %s", res.status_code)
        
        print("Testing login...")
        login_res = await client.post("/api/v1/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD})
        print("Login: %s", login_res.status_code)
        if login_res.status_code != 200:
            print("Failed login: %s", login_res.status_code)
            return
            
        token = login_res.json()["access_token"]
        headers = {"Authorization": "Bearer " + token}
        
        print("Testing create bot...")
        bot_res = await client.post("/api/v1/bots/create", json={"name": "Test Bot"}, headers=headers)
        print("Create Bot: %s", bot_res.status_code)
        if bot_res.status_code != 201:
            print("Failed create bot: %s", bot_res.status_code)
            return
            
        bot_id = bot_res.json().get("id", bot_res.json().get("_id"))
        
        print("Testing patch bot (%s)...", bot_id)
        patch_res = await client.patch("/api/v1/bots/" + bot_id, json={"summary": "test"}, headers=headers)
        print("Patch Bot: %s", patch_res.status_code)
        
        print("Testing upload resume...")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write("This is a test resume.\nExperience: 5 years software engineer\nSkills: Python, React")
            temp_path = f.name
            
        try:
            with open(temp_path, "rb") as f:
                files = {"file": ("resume.txt", f, "text/plain")}
                upload_res = await client.post("/api/v1/bots/" + bot_id + "/upload", files=files, headers=headers)
            print("Upload: %s", upload_res.status_code)
            if upload_res.status_code != 200:
                print("Failed upload: %s", upload_res.status_code)
        finally:
            os.remove(temp_path)

asyncio.run(test_onboarding())
