import os
import asyncio
import random
import json
from pathlib import Path
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# Import actual app logic
import sys
sys.path.append(os.getcwd())

from app.core.config import settings
from app.core.rag_pipeline import RAGPipeline, GlobalRecruiterIndex
from app.db.session import bots_collection, users_collection

# --- CONFIGURATION ---
NUM_DEMO = 50
NUM_POWER = 10
INDIAN_CITIES = ["Bengaluru", "Noida", "Hyderabad", "Pune", "Chennai", "Delhi", "Gurugram", "Mumbai"]
COLLEGES = {
    "Tier 1": ["IIT Bombay", "IIT Delhi", "IIT Madras", "BITS Pilani", "IIIT Hyderabad", "NIT Trichy"],
    "Tier 2": ["VIT Vellore", "Manipal Institute of Technology", "SRM University", "Thapar Institute"],
    "Tier 3": ["Galgotias University", "NIET Greater Noida", "GL Bajaj", "Noida International University (NIU)"]
}
SKILLS_CSE = ["Python", "JavaScript", "React", "Next.js", "FastAPI", "MongoDB", "TypeScript", "Node.js", "AWS", "Docker", "Express", "Tailwind CSS", "C++", "Java"]
SKILLS_MIXED = ["Digital Marketing", "SEO", "Salesforce", "Pipedrive", "AutoCAD", "MATLAB", "HR Management", "Project Management"]

# --- PDF GENERATOR ---
def generate_resume_pdf(candidate_data: dict, output_path: Path):
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter
    
    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, candidate_data["name"])
    
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 65, f"Location: {candidate_data['city']} | Education: {candidate_data['college']}")
    
    # Summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 90, "Professional Summary")
    c.line(50, height - 95, 550, height - 95)
    
    c.setFont("Helvetica", 10)
    text_object = c.beginText(50, height - 110)
    text_object.setLeading(14)
    # Split summary into lines
    words = candidate_data["summary"].split()
    line = ""
    for word in words:
        if len(line + word) < 90:
            line += word + " "
        else:
            text_object.textLine(line)
            line = word + " "
    text_object.textLine(line)
    c.drawText(text_object)
    
    # Skills
    curr_y = text_object.getY() - 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, curr_y, "Technical Skills")
    c.line(50, curr_y - 5, 550, curr_y - 5)
    
    c.setFont("Helvetica", 10)
    c.drawString(50, curr_y - 20, ", ".join(candidate_data["skills"]))
    
    # Projects / Experience
    curr_y -= 50
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, curr_y, "Experience & Projects")
    c.line(50, curr_y - 5, 550, curr_y - 5)
    
    c.setFont("Helvetica", 10)
    text_object = c.beginText(50, curr_y - 20)
    text_object.setLeading(14)
    
    if "projects" in candidate_data:
        for project in candidate_data["projects"]:
            text_object.setFont("Helvetica-Bold", 10)
            text_object.textLine(f"• {project['title']}")
            text_object.setFont("Helvetica", 10)
            text_object.textLine(f"  {project['desc']}")
            text_object.textLine("")
    else:
        text_object.textLine("• Completed various academic projects related to software development and engineering.")
        
    c.drawText(text_object)
    c.save()

# --- MOCK DATA GENERATION ---
INDIAN_MALE_NAMES = ["Arjun", "Aditya", "Rohan", "Siddharth", "Ishaan", "Vihaan", "Aarav", "Kabir", "Aryan", "Vicky"]
INDIAN_FEMALE_NAMES = ["Ananya", "Ishita", "Meera", "Sanya", "Zoya", "Riya", "Diya", "Kavya", "Aavya", "Priya"]
SURNAMES = ["Sharma", "Verma", "Gupta", "Malhotra", "Kapoor", "Singh", "Reddy", "Iyer", "Nair", "Patel"]

def get_random_name():
    first = random.choice(INDIAN_MALE_NAMES + INDIAN_FEMALE_NAMES)
    last = random.choice(SURNAMES)
    return f"{first} {last}"

async def seed():
    print("🚀 Starting Candidate Seeding Process...")
    
    # Create temp directory for PDFs
    storage_root = Path("data") / "seeded_resumes"
    storage_root.mkdir(parents=True, exist_ok=True)
    
    # 0. Get a dummy user to "own" these bots
    dummy_user = await users_collection.find_one({"role": "recruiter"})
    if not dummy_user:
        print("❌ No recruiter user found in DB. Please sign up a recruiter first.")
        return
    user_id = str(dummy_user["_id"])

    # --- TIER 1: GENERATE 50 DEMO PROFILES ---
    print(f"📦 Generating {NUM_DEMO} Demo Profiles...")
    demo_count = 0
    for i in range(NUM_DEMO):
        is_cse = random.random() < 0.95
        city = random.choice(INDIAN_CITIES)
        college_tier = random.choices(["Tier 1", "Tier 2", "Tier 3"], weights=[20, 30, 50])[0]
        college = random.choice(COLLEGES[college_tier])
        skills = random.sample(SKILLS_CSE if is_cse else SKILLS_MIXED, 6)
        
        name = get_random_name()
        summary = f"Highly motivated {college} student specializing in {'Computer Science' if is_cse else 'Engineering'}. Proven track record in {skills[0]} and {skills[1]}. Seeking opportunities in {city}."
        
        candidate_data = {
            "name": name,
            "city": city,
            "college": college,
            "skills": skills,
            "summary": summary,
            "experience_years": round(random.uniform(0, 2), 1)
        }

        # Create Record in Mongo
        bot_doc = {
            "user_id": user_id,
            "name": name,
            "skills": skills,
            "summary": summary,
            "experience_years": candidate_data["experience_years"],
            "bio": f"I am {name}, a student from {college}.",
            "is_active": True,
            "created_at": "2024-03-04T00:00:00Z"
        }
        result = await bots_collection.insert_one(bot_doc)
        bot_id = str(result.inserted_id)

        # Generate PDF
        pdf_path = storage_root / f"{bot_id}.pdf"
        generate_resume_pdf(candidate_data, pdf_path)
        
        # Add to Global Index (Semantic Only)
        profile_text = f"Name: {name}. College: {college}. Skills: {', '.join(skills)}. Summary: {summary}"
        GlobalRecruiterIndex().add_candidate_profile(bot_id, profile_text)
        
        demo_count += 1
        if demo_count % 10 == 0: print(f"  Processed {demo_count}/{NUM_DEMO}...")

    # --- TIER 2: GENERATE 10 POWER PROFILES ---
    print(f"🔥 Generating {NUM_POWER} Power Interaction Profiles...")
    for i in range(NUM_POWER):
        name = get_random_name()
        college = random.choice(COLLEGES["Tier 1"] + COLLEGES["Tier 2"])
        skills = random.sample(SKILLS_CSE, 10)
        city = random.choice(INDIAN_CITIES)
        
        # Deep project history for RAG
        projects = [
            {"title": "Real-time Distributed Chat", "desc": f"Built a high-concurrency chat app using {skills[0]} and {skills[-1]}. Handled 10k+ concurrent connections."},
            {"title": "AI Resume Parser", "desc": "Implemented a RAG-based extraction engine using LangChain and Groq LLM."},
            {"title": "Cloud Native E-commerce", "desc": "Scaled a microservices architecture on AWS using Docker and Kubernetes."}
        ]
        
        summary = f"Full-stack innovator from {college} with extensive experience in {', '.join(skills[:3])}. Passionate about building scalable cloud architectures and AI-driven internal tools."
        
        candidate_data = {
            "name": name,
            "city": city,
            "college": college,
            "skills": skills,
            "summary": summary,
            "projects": projects,
            "experience_years": round(random.uniform(1.5, 4), 1)
        }

        # Create Record in Mongo
        bot_doc = {
            "user_id": user_id,
            "name": name,
            "skills": skills,
            "summary": summary,
            "experience_years": candidate_data["experience_years"],
            "bio": f"I am {name}. I have worked on deep technical projects like {projects[0]['title']}.",
            "is_active": True,
            "created_at": "2024-03-04T00:00:00Z"
        }
        result = await bots_collection.insert_one(bot_doc)
        bot_id = str(result.inserted_id)

        # Generate PDF
        pdf_path = storage_root / f"{bot_id}.pdf"
        generate_resume_pdf(candidate_data, pdf_path)
        
        # --- DEEP RAG PROCESSING ---
        # This triggers the Semantic Chunker and Qdrant population
        pipeline = RAGPipeline(bot_id, user_id, f"{name} AI")
        pipeline.process_file(str(pdf_path))
        
        # Add to Global Index
        profile_text = f"Name: {name}. College: {college}. Skills: {', '.join(skills)}. Projects: {projects[0]['title']}, {projects[1]['title']}. Summary: {summary}"
        GlobalRecruiterIndex().add_candidate_profile(bot_id, profile_text)
        
        print(f"  Power User {i+1}/{NUM_POWER} ('{name}') Ready.")

    print("\n✅ SEEDING COMPLETE!")
    print(f"Total Profiles: {NUM_DEMO + NUM_POWER}")
    print(f"Artifacts saved in: {storage_root}")

if __name__ == "__main__":
    asyncio.run(seed())
