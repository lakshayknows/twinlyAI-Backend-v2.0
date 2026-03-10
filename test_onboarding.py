import httpx
import asyncio

async def test_onboarding():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as client:
        print("Testing signup...")
        res = await client.post("/api/v1/auth/signup", json={"email": "test4@test.com", "password": "TwinlyDefault123!", "role": "candidate"})
        print(f"Signup: {res.status_code}")
        
        print("Testing login...")
        login_res = await client.post("/api/v1/auth/login", data={"username": "test4@test.com", "password": "TwinlyDefault123!"})
        print(f"Login: {login_res.status_code}")
        if login_res.status_code != 200:
            print(f"Failed login: {login_res.text}")
            return
            
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        print("Testing create bot...")
        bot_res = await client.post("/api/v1/bots/create", json={"name": "Test Bot"}, headers=headers)
        print(f"Create Bot: {bot_res.status_code}")
        if bot_res.status_code != 201:
            print(f"Failed create bot: {bot_res.text}")
            return
            
        bot_id = bot_res.json().get("id", bot_res.json().get("_id"))
        
        print(f"Testing patch bot ({bot_id})...")
        patch_res = await client.patch(f"/api/v1/bots/{bot_id}", json={"summary": "test"}, headers=headers)
        print(f"Patch Bot: {patch_res.status_code}")
        
        print("Testing upload resume...")
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write("This is a test resume.\nExperience: 5 years software engineer\nSkills: Python, React")
            temp_path = f.name
            
        try:
            with open(temp_path, "rb") as f:
                files = {"file": ("resume.txt", f, "text/plain")}
                upload_res = await client.post(f"/api/v1/bots/{bot_id}/upload", files=files, headers=headers)
            print(f"Upload: {upload_res.status_code}")
            if upload_res.status_code != 200:
                print(f"Failed upload: {upload_res.text}")
        finally:
            os.remove(temp_path)

asyncio.run(test_onboarding())
