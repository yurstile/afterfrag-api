import uuid
import os
from pathlib import Path
from typing import Optional
import shutil

# Configuration
UPLOAD_FOLDER = "uploads"
PROFILE_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, "users", "profilepictures")
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}  # No .gif for community images
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

COMMUNITY_BANNERS_FOLDER = os.path.join(UPLOAD_FOLDER, "communities", "banners")
COMMUNITY_GROUP_PICTURES_FOLDER = os.path.join(UPLOAD_FOLDER, "communities", "group_pictures")

POSTS_MEDIA_FOLDER = os.path.join(UPLOAD_FOLDER, "posts")

def ensure_upload_directories():
    """Ensure upload directories exist"""
    Path(PROFILE_PICTURES_FOLDER).mkdir(parents=True, exist_ok=True)

def generate_uuid_filename(original_filename: str) -> str:
    """Generate a UUID filename with original extension"""
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = '.png'  # Default to PNG if extension not allowed
    return f"{uuid.uuid4()}{ext}"

def save_profile_picture(file_content: bytes, filename: str) -> Optional[str]:
    """Save profile picture and return the UUID filename"""
    try:
        ensure_upload_directories()
        
        # Check file size
        if len(file_content) > MAX_FILE_SIZE:
            return None
            
        # Generate UUID filename
        uuid_filename = generate_uuid_filename(filename)
        file_path = os.path.join(PROFILE_PICTURES_FOLDER, uuid_filename)
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(file_content)
            
        return uuid_filename
    except Exception:
        return None

def delete_profile_picture(uuid_filename: str) -> bool:
    """Delete a profile picture by UUID filename"""
    try:
        file_path = os.path.join(PROFILE_PICTURES_FOLDER, uuid_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False

def get_profile_picture_url(uuid_filename: str) -> Optional[str]:
    """Generate the CDN URL for a profile picture"""
    if not uuid_filename:
        return None
    return f"https://app.afterfrag.com/cdn/users/profilepictures/{uuid_filename}" 

def ensure_community_upload_directories():
    Path(COMMUNITY_BANNERS_FOLDER).mkdir(parents=True, exist_ok=True)
    Path(COMMUNITY_GROUP_PICTURES_FOLDER).mkdir(parents=True, exist_ok=True)

def save_community_banner(file_content: bytes, filename: str) -> Optional[str]:
    try:
        ensure_community_upload_directories()
        if len(file_content) > MAX_FILE_SIZE:
            return None
        uuid_filename = generate_uuid_filename(filename)
        file_path = os.path.join(COMMUNITY_BANNERS_FOLDER, uuid_filename)
        with open(file_path, 'wb') as f:
            f.write(file_content)
        return uuid_filename
    except Exception:
        return None

def delete_community_banner(uuid_filename: str) -> bool:
    try:
        file_path = os.path.join(COMMUNITY_BANNERS_FOLDER, uuid_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False

def get_community_banner_url(uuid_filename: str) -> Optional[str]:
    if not uuid_filename:
        return None
    return f"https://app.afterfrag.com/cdn/communities/banners/{uuid_filename}"

def save_community_group_picture(file_content: bytes, filename: str) -> Optional[str]:
    try:
        ensure_community_upload_directories()
        if len(file_content) > MAX_FILE_SIZE:
            return None
        uuid_filename = generate_uuid_filename(filename)
        file_path = os.path.join(COMMUNITY_GROUP_PICTURES_FOLDER, uuid_filename)
        with open(file_path, 'wb') as f:
            f.write(file_content)
        return uuid_filename
    except Exception:
        return None

def delete_community_group_picture(uuid_filename: str) -> bool:
    try:
        file_path = os.path.join(COMMUNITY_GROUP_PICTURES_FOLDER, uuid_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False

def get_community_group_picture_url(uuid_filename: str) -> Optional[str]:
    if not uuid_filename:
        return None
    return f"https://app.afterfrag.com/cdn/communities/group_pictures/{uuid_filename}" 

def ensure_post_media_directory():
    Path(POSTS_MEDIA_FOLDER).mkdir(parents=True, exist_ok=True)

def get_post_media_url(uuid_filename: str) -> Optional[str]:
    if not uuid_filename:
        return None
    return f"https://app.afterfrag.com/cdn/posts/{uuid_filename}" 