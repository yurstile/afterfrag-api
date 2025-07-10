from database import get_db
from fastapi import HTTPException

def get_user_profile(user_id: int):
    """Get user profile by user ID (moved from routes/profile.py)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, display_name, bio, profile_picture_uuid, 
                   is_online, last_online, created_at, updated_at
            FROM user_profiles WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0], "user_id": row[1], "display_name": row[2], 
                "bio": row[3], "profile_picture_uuid": row[4], "is_online": row[5],
                "last_online": row[6], "created_at": row[7], "updated_at": row[8]
            }
        return None

def get_user_community_role(community_id: int, user_id: int):
    """Get the user's role in a community (moved from routes/communities.py)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM community_members WHERE community_id = ? AND user_id = ?", (community_id, user_id))
        row = cursor.fetchone()
        return row[0] if row else None 