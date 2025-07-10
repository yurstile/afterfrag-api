from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from file_utils import PROFILE_PICTURES_FOLDER, COMMUNITY_GROUP_PICTURES_FOLDER, COMMUNITY_BANNERS_FOLDER, POSTS_MEDIA_FOLDER
COMMENT_MEDIA_FOLDER = os.path.join("uploads", "comments")

router = APIRouter(prefix="/cdn", tags=["cdn"])

@router.get("/users/profilepictures/{filename}")
def serve_profile_picture(filename: str):
    """Serve profile picture files"""
    file_path = os.path.join(PROFILE_PICTURES_FOLDER, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path) 

@router.get("/communities/group_pictures/{filename}")
def serve_community_group_picture(filename: str):
    """Serve community group picture files"""
    file_path = os.path.join(COMMUNITY_GROUP_PICTURES_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@router.get("/communities/banners/{filename}")
def serve_community_banner(filename: str):
    """Serve community banner files"""
    file_path = os.path.join(COMMUNITY_BANNERS_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path) 

@router.get("/posts/{filename}")
def serve_post_media(filename: str):
    file_path = os.path.join(POSTS_MEDIA_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path) 

@router.get("/comments/{filename}")
def serve_comment_media(filename: str):
    file_path = os.path.join(COMMENT_MEDIA_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path) 