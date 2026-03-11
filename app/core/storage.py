# app/core/storage.py

import os
import shutil
from pathlib import Path
from typing import Optional, Tuple
import cloudinary
import cloudinary.uploader
from app.core.config import settings

# Configure Cloudinary if credentials are provided
if settings.STORAGE_TYPE == "cloudinary":
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True
    )

class StorageService:
    @staticmethod
    def upload_file(file_path: str, public_id: str, folder: str = "resumes") -> Tuple[str, Optional[str]]:
        """
        Uploads a file to the configured storage backend.
        Returns: (url, thumbnail_url)
        """
        if settings.STORAGE_TYPE == "cloudinary":
            # Upload to Cloudinary as 'raw' to preserve PDF, but also as an image for thumb if needed?
            # Actually, Cloudinary can treat PDFs as images for thumbnails.
            
            # 1. Upload for PDF access
            response = cloudinary.uploader.upload(
                file_path,
                public_id=public_id,
                folder=folder,
                resource_type="auto" # Cloudinary detects PDF
            )
            pdf_url = response.get("secure_url")
            
            # 2. Get thumbnail URL (Cloudinary trick: replace .pdf with .jpg or use format)
            # Example: res.cloudinary.com/demo/image/upload/w_200,h_300,c_fill,pg_1/test.pdf
            thumb_url = None
            if pdf_url.endswith(".pdf"):
                thumb_url = pdf_url.replace(".pdf", ".jpg")
                # Add transformations for a nice card preview
                parts = thumb_url.split("/upload/")
                thumb_url = "{}/upload/w_400,h_600,c_fill,pg_1,q_auto/{}".format(parts[0], parts[1])
            
            return pdf_url, thumb_url

        else:
            # Local Storage
            local_path = Path("data") / folder / "{}.pdf".format(public_id)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy(file_path, local_path)
            # In a real local setup, you'd serve this via static files
            # For now, return the relative path
            return str(local_path), None

    @staticmethod
    def get_resume_url(bot_id: str) -> str:
        """
        In Cloudinary, it's the secure_url. In local, it's the static serve path.
        """
        if settings.STORAGE_TYPE == "cloudinary":
            # This is tricky if we don't store it in DB. 
            # Better to store 'resume_url' in MongoDB 'bots' collection.
            pass
        return "/api/v1/recruiter/resume/{}".format(bot_id)  # Fallback to proxy endpoint
