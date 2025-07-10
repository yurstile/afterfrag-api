from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
import json
from datetime import datetime, timezone, timedelta
from database import get_db
from schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse, SocialLink, OnlineStatusUpdate, RecentActivityResponse, RecentActivityItem
from file_utils import save_profile_picture, delete_profile_picture, get_profile_picture_url
from auth import verify_token
from schemas.posts import PostResponse, CommentResponse
from routes.posts import get_post_response
from routes.comments import get_comment_response
import random
from utils.route_helpers import get_user_profile
from routes.communities import get_community_by_id
from routes.posts import get_comment_count
from file_utils import get_community_group_picture_url

router = APIRouter(prefix="/users", tags=["profiles"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ONLINE_TIMEOUT_SECONDS = 60

def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """Get current user ID from token"""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Get user ID from username
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (payload.get("sub"),))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return row[0]

def get_user_by_id(user_id: int):
    """Get user by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "username": row[1]}
        return None

def get_user_social_links(user_id: int):
    """Get user social links by user ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT platform, url FROM social_links WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        return [{"platform": row[0], "url": row[1]} for row in rows]

def is_user_online(last_online, is_online_flag):
    if not is_online_flag or not last_online:
        return False
    now = datetime.now(timezone.utc)
    if isinstance(last_online, str):
        try:
            last_online = datetime.fromisoformat(last_online)
        except Exception:
            return False
    # Ensure last_online is timezone-aware (UTC)
    if last_online.tzinfo is None:
        last_online = last_online.replace(tzinfo=timezone.utc)
    return (now - last_online) < timedelta(seconds=ONLINE_TIMEOUT_SECONDS)

@router.get("/{user_id}/profile", response_model=ProfileResponse)
def get_profile(user_id: int):
    """Get user profile by user ID"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    profile = get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    social_links = get_user_social_links(user_id)
    
    # Calculate online status
    online = is_user_online(profile["last_online"], profile["is_online"])
    
    return ProfileResponse(
        user_id=user["id"],
        username=user["username"],
        display_name=profile["display_name"],
        bio=profile["bio"],
        profile_picture_url=get_profile_picture_url(profile["profile_picture_uuid"]),
        is_online=online,
        last_online=profile["last_online"],
        social_links=social_links,
        created_at=profile["created_at"],
        updated_at=profile["updated_at"],
        is_admin=user.get("is_admin", False)
    )

@router.post("/{user_id}/profile", response_model=ProfileResponse)
def create_profile(
    user_id: int, 
    profile: ProfileCreate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Create user profile"""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only create your own profile")
    
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    existing_profile = get_user_profile(user_id)
    if existing_profile:
        raise HTTPException(status_code=400, detail="Profile already exists")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_profiles (user_id, display_name, bio)
            VALUES (?, ?, ?)
        """, (user_id, profile.display_name, profile.bio))
        
        # Insert social links
        if profile.social_links:
            for social_link in profile.social_links:
                cursor.execute("""
                    INSERT INTO social_links (user_id, platform, url)
                    VALUES (?, ?, ?)
                """, (user_id, social_link.platform, social_link.url))
        
        conn.commit()
    
    # Return the created profile
    return get_profile(user_id)

@router.put("/{user_id}/profile", response_model=ProfileResponse)
def update_profile(
    user_id: int,
    profile: ProfileUpdate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Update user profile"""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only update your own profile")
    
    existing_profile = get_user_profile(user_id)
    if not existing_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Update profile fields
        update_fields = []
        params = []
        
        if profile.display_name is not None:
            update_fields.append("display_name = ?")
            params.append(profile.display_name)
        
        if profile.bio is not None:
            update_fields.append("bio = ?")
            params.append(profile.bio)
        
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            cursor.execute(f"""
                UPDATE user_profiles 
                SET {', '.join(update_fields)}
                WHERE user_id = ?
            """, params)
        
        # Update social links if provided
        if profile.social_links is not None:
            # Delete existing social links
            cursor.execute("DELETE FROM social_links WHERE user_id = ?", (user_id,))
            
            # Insert new social links
            for social_link in profile.social_links:
                cursor.execute("""
                    INSERT INTO social_links (user_id, platform, url)
                    VALUES (?, ?, ?)
                """, (user_id, social_link.platform, social_link.url))
        
        conn.commit()
    
    return get_profile(user_id)

@router.post("/{user_id}/profile/picture")
def upload_profile_picture(
    user_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """Upload profile picture"""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only upload to your own profile")
    
    existing_profile = get_user_profile(user_id)
    if not existing_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # Read file content
    file_content = file.file.read()
    
    # Save the new picture
    uuid_filename = save_profile_picture(file_content, file.filename)
    if not uuid_filename:
        raise HTTPException(status_code=400, detail="Failed to save image")
    
    # Delete old picture if exists
    if existing_profile["profile_picture_uuid"]:
        delete_profile_picture(existing_profile["profile_picture_uuid"])
    
    # Update database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_profiles 
            SET profile_picture_uuid = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (uuid_filename, user_id))
        conn.commit()
    
    return {
        "message": "Profile picture uploaded successfully",
        "profile_picture_url": get_profile_picture_url(uuid_filename)
    }

@router.delete("/{user_id}/profile/picture")
def delete_profile_picture_route(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Delete profile picture"""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only delete your own profile picture")
    
    existing_profile = get_user_profile(user_id)
    if not existing_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    if not existing_profile["profile_picture_uuid"]:
        raise HTTPException(status_code=404, detail="No profile picture to delete")
    
    # Delete file
    if delete_profile_picture(existing_profile["profile_picture_uuid"]):
        # Update database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_profiles 
                SET profile_picture_uuid = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
        
        return {"message": "Profile picture deleted successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete profile picture")

@router.post("/{user_id}/profile/online-status")
def update_online_status(
    user_id: int,
    status: OnlineStatusUpdate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Update user online status"""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only update your own online status")
    
    existing_profile = get_user_profile(user_id)
    if not existing_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_profiles 
            SET is_online = ?, last_online = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (status.is_online, user_id))
        conn.commit()
    
    return {"message": "Online status updated successfully"}

@router.get("/{user_id}/profile/online-status")
def get_online_status(user_id: int):
    """Get user online status"""
    profile = get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    online = is_user_online(profile["last_online"], profile["is_online"])
    return {
        "is_online": online,
        "last_online": profile["last_online"]
    } 

@router.get("/{user_id}/profile/recent-activity", response_model=RecentActivityResponse)
def get_recent_activity(user_id: int, page: int = 1, page_size: int = 10):
    """
    Get recent activity (posts and comments) for a user, paginated and sorted by creation date descending.
    Now includes group name, group logo, and comment count.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        # Fetch posts
        cursor.execute("SELECT id, community_id, created_at FROM posts WHERE user_id = ?", (user_id,))
        posts = cursor.fetchall()
        # Fetch comments
        cursor.execute("SELECT id, post_id, created_at FROM comments WHERE user_id = ?", (user_id,))
        comments = cursor.fetchall()
        # Combine and sort
        activity = []
        for pid, community_id, created_at in posts:
            activity.append({"type": "post", "id": pid, "community_id": community_id, "created_at": created_at})
        for cid, post_id, created_at in comments:
            # Get community_id for the post
            cursor.execute("SELECT community_id FROM posts WHERE id = ?", (post_id,))
            row = cursor.fetchone()
            community_id = row[0] if row else None
            activity.append({"type": "comment", "id": cid, "community_id": community_id, "post_id": post_id, "created_at": created_at})
        activity.sort(key=lambda x: x["created_at"], reverse=True)
        total = len(activity)
        # Pagination
        start = (page - 1) * page_size
        end = start + page_size
        paginated = activity[start:end]
        items = []
        for entry in paginated:
            group_name = None
            group_logo_url = None
            comment_count = None
            if entry["community_id"]:
                community = get_community_by_id(entry["community_id"])
                if community:
                    group_name = community["name"]
                    group_logo_url = get_community_group_picture_url(community["group_picture_uuid"])
            if entry["type"] == "post":
                post = get_post_response(entry["id"])
                comment_count = get_comment_count(entry["id"])
                items.append(RecentActivityItem(type="post", post=post, created_at=entry["created_at"], group_name=group_name, group_logo_url=group_logo_url, comment_count=comment_count))
            else:
                comment = get_comment_response(entry["id"])
                # For comments, comment_count is the number of comments on the parent post
                if entry.get("post_id"):
                    comment_count = get_comment_count(entry["post_id"])
                items.append(RecentActivityItem(type="comment", comment=comment, created_at=entry["created_at"], group_name=group_name, group_logo_url=group_logo_url, comment_count=comment_count))
        return RecentActivityResponse(items=items, total=total, page=page, page_size=page_size)

@router.get("/{user_id}/home/recommendations", response_model=List[PostResponse])
def get_home_recommendations(user_id: int):
    """
    Recommend up to 20 posts for the user based on overlap between user_topics and post tags, randomized. Fallback to trending/recent posts if no matches.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        # Get user topics
        cursor.execute("SELECT topic FROM user_topics WHERE user_id = ?", (user_id,))
        user_topics = set(row[0] for row in cursor.fetchall())
        # Get posts with overlapping tags, exclude user's own posts
        cursor.execute("SELECT * FROM posts WHERE user_id != ?", (user_id,))
        posts = cursor.fetchall()
        recommended = []
        for row in posts:
            post_id = row[0]
            tags_json = row[5]
            if not tags_json:
                continue
            try:
                post_tags = set(json.loads(tags_json))
            except Exception:
                continue
            if user_topics and (user_topics & post_tags):
                recommended.append(get_post_response(post_id))
        random.shuffle(recommended)
        if recommended:
            return recommended[:20]
        # Fallback: trending/recent posts (excluding user's own)
        cursor.execute("SELECT id FROM posts WHERE user_id != ? ORDER BY like_count DESC, created_at DESC LIMIT 20", (user_id,))
        fallback_rows = cursor.fetchall()
        fallback_posts = [get_post_response(row[0]) for row in fallback_rows]
        return fallback_posts 