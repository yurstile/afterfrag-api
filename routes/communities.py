from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
import json
from datetime import datetime
from database import get_db
from schemas.communities import (
    CommunityCreate, 
    CommunityUpdate, 
    CommunityResponse, 
    CommunityDetailResponse,
    CommunityMember,
    CommunityMemberUpdate
)
from auth import verify_token
from file_utils import (
    save_community_banner, delete_community_banner,
    save_community_group_picture, delete_community_group_picture,
    get_community_banner_url, get_community_group_picture_url,
    get_profile_picture_url
)
from utils.route_helpers import get_user_profile, get_user_community_role
from schemas import CommunityPostTagCreate, CommunityPostTagUpdate, CommunityPostTagResponse

router = APIRouter(prefix="/communities", tags=["communities"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

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

def get_user_display_name(user_id: int):
    """Get user display name by user ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT display_name FROM user_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None

def get_community_by_id(community_id: int):
    """Get community by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                   u.username as owner_username, c.banner_picture_uuid, c.group_picture_uuid,
                   c.rules, c.social_links
            FROM communities c
            JOIN users u ON c.owner_id = u.id
            WHERE c.id = ?
        """, (community_id,))
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0], "name": row[1], "description": row[2], 
                "tags": json.loads(row[3]), "owner_id": row[4], 
                "created_at": row[5], "updated_at": row[6], "owner_username": row[7],
                "banner_picture_uuid": row[8], "group_picture_uuid": row[9],
                "rules": json.loads(row[10]) if row[10] else None,
                "social_links": json.loads(row[11]) if row[11] else None
            }
        return None

def get_community_member_count(community_id: int):
    """Get community member count"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM community_members WHERE community_id = ?", (community_id,))
        return cursor.fetchone()[0]

def get_community_online_member_count(community_id: int):
    """Get community online member count"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT cm.user_id)
            FROM community_members cm
            JOIN user_profiles up ON cm.user_id = up.user_id
            WHERE cm.community_id = ? 
            AND up.is_online = 1
            AND up.last_online >= datetime('now', '-60 seconds')
        """, (community_id,))
        return cursor.fetchone()[0]

def get_community_staff_members(community_id: int):
    """Get community owners and moderators only, with profile picture URLs"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cm.user_id, u.username, up.display_name, cm.role, cm.joined_at, up.profile_picture_uuid
            FROM community_members cm
            JOIN users u ON cm.user_id = u.id
            LEFT JOIN user_profiles up ON cm.user_id = up.user_id
            WHERE cm.community_id = ? AND cm.role IN ('owner', 'moderator')
            ORDER BY 
                CASE cm.role 
                    WHEN 'owner' THEN 1 
                    WHEN 'moderator' THEN 2 
                END,
                cm.joined_at
        """, (community_id,))
        rows = cursor.fetchall()
        return [
            {
                "user_id": row[0],
                "username": row[1],
                "display_name": row[2] or row[1],
                "role": row[3],
                "joined_at": row[4],
                "profile_picture_url": get_profile_picture_url(row[5]) if row[5] else None
            }
            for row in rows
        ]

def get_user_topics(user_id: int) -> List[str]:
    """Get user's current topics"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT topic FROM user_topics WHERE user_id = ?", (user_id,))
        return [row[0] for row in cursor.fetchall()]

def add_topics_to_user(user_id: int, topics: List[str]):
    """Add topics to user's preferences (ignore if already exists)"""
    with get_db() as conn:
        cursor = conn.cursor()
        for topic in topics:
            cursor.execute("""
                INSERT OR IGNORE INTO user_topics (user_id, topic)
                VALUES (?, ?)
            """, (user_id, topic))
        conn.commit()

def remove_topics_from_user(user_id: int, topics: List[str]):
    """Remove topics from user's preferences if they're not used by other communities"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get all communities the user is a member of
        cursor.execute("""
            SELECT DISTINCT c.tags
            FROM communities c
            JOIN community_members cm ON c.id = cm.community_id
            WHERE cm.user_id = ?
        """, (user_id,))
        
        # Collect all topics from user's communities
        all_community_topics = set()
        for row in cursor.fetchall():
            community_tags = json.loads(row[0])
            all_community_topics.update(community_tags)
        
        # Remove topics that are not used by any of user's communities
        for topic in topics:
            if topic not in all_community_topics:
                cursor.execute("""
                    DELETE FROM user_topics 
                    WHERE user_id = ? AND topic = ?
                """, (user_id, topic))
        
        conn.commit()

@router.post("/", response_model=CommunityResponse)
def create_community(
    community: CommunityCreate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Create a new community"""
    # Check if community name already exists
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM communities WHERE name = ?", (community.name,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Community name already exists")
        # Create community
        cursor.execute("""
            INSERT INTO communities (name, description, tags, owner_id, rules, social_links)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            community.name,
            community.description,
            json.dumps(community.tags),
            current_user_id,
            json.dumps(community.rules) if community.rules else None,
            json.dumps([link.dict() for link in community.social_links]) if community.social_links else None
        ))
        community_id = cursor.lastrowid
        # Add owner as first member
        cursor.execute("""
            INSERT INTO community_members (community_id, user_id, role)
            VALUES (?, ?, 'owner')
        """, (community_id, current_user_id))
        conn.commit()
    # Return the created community
    return get_community_response(community_id)

@router.get("/", response_model=List[CommunityResponse])
def list_communities(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """List communities with optional filtering"""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                   u.username as owner_username, c.banner_picture_uuid, c.group_picture_uuid,
                   c.rules, c.social_links
            FROM communities c
            JOIN users u ON c.owner_id = u.id
        """
        params = []
        conditions = []
        if tag:
            conditions.append("c.tags LIKE ?")
            params.append(f'%"{tag}"%')
        if search:
            conditions.append("(c.name LIKE ? OR c.description LIKE ?)")
            params.extend([f'%{search}% ', f'%{search}%'])
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY c.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, skip])
        cursor.execute(query, params)
        rows = cursor.fetchall()
        communities = []
        for row in rows:
            member_count = get_community_member_count(row[0])
            online_member_count = get_community_online_member_count(row[0])
            communities.append(CommunityResponse(
                id=row[0], name=row[1], description=row[2], 
                tags=json.loads(row[3]), owner_id=row[4], 
                created_at=row[5], updated_at=row[6], 
                owner_username=row[7], member_count=member_count,
                online_member_count=online_member_count,
                banner_picture_url=get_community_banner_url(row[8]),
                group_picture_url=get_community_group_picture_url(row[9]),
                rules=json.loads(row[10]) if row[10] else None,
                social_links=json.loads(row[11]) if row[11] else None
            ))
        return communities

def get_community_response(community_id: int) -> CommunityResponse:
    """Get community response (without members)"""
    community = get_community_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    member_count = get_community_member_count(community_id)
    online_member_count = get_community_online_member_count(community_id)
    return CommunityResponse(
        id=community["id"], name=community["name"], description=community["description"],
        tags=community["tags"], owner_id=community["owner_id"], 
        owner_username=community["owner_username"], member_count=member_count,
        online_member_count=online_member_count,
        created_at=community["created_at"], updated_at=community["updated_at"],
        banner_picture_url=get_community_banner_url(community["banner_picture_uuid"]),
        group_picture_url=get_community_group_picture_url(community["group_picture_uuid"]),
        rules=community["rules"],
        social_links=community["social_links"]
    )

@router.get("/{community_id}", response_model=CommunityDetailResponse)
def get_community(community_id: int):
    """Get community details with staff members and member count"""
    community = get_community_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    staff_members = get_community_staff_members(community_id)
    member_count = get_community_member_count(community_id)
    online_member_count = get_community_online_member_count(community_id)
    return CommunityDetailResponse(
        id=community["id"], name=community["name"], description=community["description"],
        tags=community["tags"], owner_id=community["owner_id"], 
        owner_username=community["owner_username"], staff_members=staff_members,
        member_count=member_count, online_member_count=online_member_count,
        created_at=community["created_at"], updated_at=community["updated_at"],
        banner_picture_url=get_community_banner_url(community["banner_picture_uuid"]),
        group_picture_url=get_community_group_picture_url(community["group_picture_uuid"]),
        rules=community["rules"],
        social_links=community["social_links"]
    )

@router.put("/{community_id}", response_model=CommunityResponse)
def update_community(
    community_id: int,
    community: CommunityUpdate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Update community (owner only)"""
    existing_community = get_community_by_id(community_id)
    if not existing_community:
        raise HTTPException(status_code=404, detail="Community not found")
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can update community")
    with get_db() as conn:
        cursor = conn.cursor()
        update_fields = []
        params = []
        if community.name is not None:
            # Check if new name already exists
            cursor.execute("SELECT id FROM communities WHERE name = ? AND id != ?", 
                         (community.name, community_id))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Community name already exists")
            update_fields.append("name = ?")
            params.append(community.name)
        if community.description is not None:
            update_fields.append("description = ?")
            params.append(community.description)
        if community.tags is not None:
            update_fields.append("tags = ?")
            params.append(json.dumps(community.tags))
        if community.rules is not None:
            update_fields.append("rules = ?")
            params.append(json.dumps(community.rules))
        if community.social_links is not None:
            update_fields.append("social_links = ?")
            params.append(json.dumps([link.dict() for link in community.social_links]))
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(community_id)
            cursor.execute(f"""
                UPDATE communities 
                SET {', '.join(update_fields)}
                WHERE id = ?
            """, params)
            conn.commit()
    return get_community_response(community_id)

@router.delete("/{community_id}")
def delete_community(
    community_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Delete community (owner only)"""
    existing_community = get_community_by_id(community_id)
    if not existing_community:
        raise HTTPException(status_code=404, detail="Community not found")
    
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can delete community")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM communities WHERE id = ?", (community_id,))
        conn.commit()
    
    return {"message": "Community deleted successfully"}

@router.post("/{community_id}/join")
def join_community(
    community_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Join a community and add its topics to user preferences"""
    community = get_community_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    
    # Check if already a member
    existing_role = get_user_community_role(community_id, current_user_id)
    if existing_role:
        raise HTTPException(status_code=400, detail="Already a member of this community")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO community_members (community_id, user_id, role)
            VALUES (?, ?, 'member')
        """, (community_id, current_user_id))
        conn.commit()
    
    # Add community topics to user's preferences
    community_topics = community["tags"]
    add_topics_to_user(current_user_id, community_topics)
    
    # Get newly added topics (topics user didn't have before)
    user_existing_topics = get_user_topics(current_user_id)
    newly_added_topics = [topic for topic in community_topics if topic not in user_existing_topics]
    
    response_message = "Successfully joined community"
    if newly_added_topics:
        response_message += f" and added topics: {', '.join(newly_added_topics)}"
    
    return {"message": response_message}

@router.post("/{community_id}/leave")
def leave_community(
    community_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Leave a community and remove its topics if not used by other communities"""
    community = get_community_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    
    role = get_user_community_role(community_id, current_user_id)
    if not role:
        raise HTTPException(status_code=400, detail="Not a member of this community")
    
    if role == 'owner':
        raise HTTPException(status_code=400, detail="Owner cannot leave community. Transfer ownership or delete community.")
    
    # Get community topics before leaving
    community_topics = community["tags"]
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM community_members 
            WHERE community_id = ? AND user_id = ?
        """, (community_id, current_user_id))
        conn.commit()
    
    # Remove topics that are no longer used by any of user's communities
    remove_topics_from_user(current_user_id, community_topics)
    
    # Check which topics were actually removed
    user_current_topics = get_user_topics(current_user_id)
    removed_topics = [topic for topic in community_topics if topic not in user_current_topics]
    
    response_message = "Successfully left community"
    if removed_topics:
        response_message += f" and removed topics: {', '.join(removed_topics)}"
    
    return {"message": response_message}

@router.put("/{community_id}/members/{user_id}")
def update_member_role(
    community_id: int,
    user_id: int,
    member_update: CommunityMemberUpdate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Update member role (owner only)"""
    community = get_community_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can update member roles")
    
    if current_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot update your own role")
    
    target_role = get_user_community_role(community_id, user_id)
    if not target_role:
        raise HTTPException(status_code=404, detail="User is not a member of this community")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE community_members 
            SET role = ? 
            WHERE community_id = ? AND user_id = ?
        """, (member_update.role, community_id, user_id))
        conn.commit()
    
    return {"message": f"Member role updated to {member_update.role}"}

@router.delete("/{community_id}/members/{user_id}")
def remove_member(
    community_id: int,
    user_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Remove member from community (owner or moderator) and handle topic removal"""
    community = get_community_by_id(community_id)
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    
    if not get_user_community_role(community_id, current_user_id) in ['owner', 'moderator']:
        raise HTTPException(status_code=403, detail="Only owners and moderators can remove members")
    
    if current_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    
    target_role = get_user_community_role(community_id, user_id)
    if not target_role:
        raise HTTPException(status_code=404, detail="User is not a member of this community")
    
    if target_role == 'owner':
        raise HTTPException(status_code=400, detail="Cannot remove community owner")
    
    # Moderators can only remove members, not other moderators
    current_role = get_user_community_role(community_id, current_user_id)
    if current_role == 'moderator' and target_role == 'moderator':
        raise HTTPException(status_code=403, detail="Moderators can only remove regular members")
    
    # Get community topics before removing member
    community_topics = community["tags"]
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM community_members 
            WHERE community_id = ? AND user_id = ?
        """, (community_id, user_id))
        conn.commit()
    
    # Remove topics that are no longer used by any of user's communities
    remove_topics_from_user(user_id, community_topics)
    
    return {"message": "Member removed from community"}

@router.get("/user/joined", response_model=List[CommunityResponse])
def get_user_communities(current_user_id: int = Depends(get_current_user_id)):
    """Get communities that the current user has joined"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                   u.username as owner_username, c.group_picture_uuid
            FROM communities c
            JOIN users u ON c.owner_id = u.id
            JOIN community_members cm ON c.id = cm.community_id
            WHERE cm.user_id = ?
            ORDER BY cm.joined_at DESC
        """, (current_user_id,))
        rows = cursor.fetchall()
        communities = []
        for row in rows:
            member_count = get_community_member_count(row[0])
            online_member_count = get_community_online_member_count(row[0])
            communities.append(CommunityResponse(
                id=row[0], name=row[1], description=row[2], 
                tags=json.loads(row[3]), owner_id=row[4], 
                created_at=row[5], updated_at=row[6], 
                owner_username=row[7], member_count=member_count,
                online_member_count=online_member_count,
                group_picture_url=get_community_group_picture_url(row[8])
            ))
        return communities

@router.get("/user/topics")
def get_user_topics_with_sources(current_user_id: int = Depends(get_current_user_id)):
    """Get user's current topics and which communities they came from"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get user's current topics
        cursor.execute("SELECT topic FROM user_topics WHERE user_id = ? ORDER BY topic", (current_user_id,))
        user_topics = [row[0] for row in cursor.fetchall()]
        
        # Get communities and their topics for this user
        cursor.execute("""
            SELECT c.id, c.name, c.tags
            FROM communities c
            JOIN community_members cm ON c.id = cm.community_id
            WHERE cm.user_id = ?
            ORDER BY c.name
        """, (current_user_id,))
        
        community_sources = {}
        for row in cursor.fetchall():
            community_id, community_name, tags_json = row
            community_tags = json.loads(tags_json)
            community_sources[community_name] = {
                "community_id": community_id,
                "topics": community_tags
            }
        
        # Calculate topic sources
        topic_sources = {}
        for topic in user_topics:
            topic_sources[topic] = []
            for community_name, community_data in community_sources.items():
                if topic in community_data["topics"]:
                    topic_sources[topic].append({
                        "community_name": community_name,
                        "community_id": community_data["community_id"]
                    })
        
        return {
            "user_topics": user_topics,
            "total_topics": len(user_topics),
            "topic_sources": topic_sources,
            "communities": community_sources
        } 

@router.get("/f/{community_name}", response_model=CommunityDetailResponse)
def get_community_by_name_route(community_name: str):
    """Get community details by name (case-insensitive), for /f/groupname style lookup"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id FROM communities c WHERE LOWER(c.name) = LOWER(?)
            """,
            (community_name,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Community not found")
        community_id = int(row[0])
    return get_community(community_id) 

@router.post("/{community_id}/group-picture")
def upload_community_group_picture(
    community_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """Upload or update the community group picture (only owner)"""
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can upload group picture")
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise HTTPException(status_code=400, detail="Only static images (.png, .jpg, .jpeg, .webp) are allowed")
    file_content = file.file.read()
    uuid_filename = save_community_group_picture(file_content, file.filename)
    if not uuid_filename:
        raise HTTPException(status_code=400, detail="Failed to save image (file too large or invalid)")
    # Update DB and delete old picture if exists
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT group_picture_uuid FROM communities WHERE id = ?", (community_id,))
        row = cursor.fetchone()
        old_uuid = row[0] if row else None
        cursor.execute("UPDATE communities SET group_picture_uuid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (uuid_filename, community_id))
        conn.commit()
    if old_uuid:
        delete_community_group_picture(old_uuid)
    return {"group_picture_url": get_community_group_picture_url(uuid_filename)}

@router.delete("/{community_id}/group-picture")
def delete_community_group_picture_route(
    community_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Delete the community group picture (only owner)"""
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can delete group picture")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT group_picture_uuid FROM communities WHERE id = ?", (community_id,))
        row = cursor.fetchone()
        uuid_filename = row[0] if row else None
        if not uuid_filename:
            raise HTTPException(status_code=404, detail="No group picture to delete")
        cursor.execute("UPDATE communities SET group_picture_uuid = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (community_id,))
        conn.commit()
    delete_community_group_picture(uuid_filename)
    return {"message": "Group picture deleted"}

@router.post("/{community_id}/banner")
def upload_community_banner(
    community_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """Upload or update the community banner (only owner)"""
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can upload banner")
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise HTTPException(status_code=400, detail="Only static images (.png, .jpg, .jpeg, .webp) are allowed")
    file_content = file.file.read()
    uuid_filename = save_community_banner(file_content, file.filename)
    if not uuid_filename:
        raise HTTPException(status_code=400, detail="Failed to save image (file too large or invalid)")
    # Update DB and delete old banner if exists
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT banner_picture_uuid FROM communities WHERE id = ?", (community_id,))
        row = cursor.fetchone()
        old_uuid = row[0] if row else None
        cursor.execute("UPDATE communities SET banner_picture_uuid = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (uuid_filename, community_id))
        conn.commit()
    if old_uuid:
        delete_community_banner(old_uuid)
    return {"banner_picture_url": get_community_banner_url(uuid_filename)}

@router.delete("/{community_id}/banner")
def delete_community_banner_route(
    community_id: int,
    current_user_id: int = Depends(get_current_user_id)
):
    """Delete the community banner (only owner)"""
    if not get_user_community_role(community_id, current_user_id) == 'owner':
        raise HTTPException(status_code=403, detail="Only community owner can delete banner")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT banner_picture_uuid FROM communities WHERE id = ?", (community_id,))
        row = cursor.fetchone()
        uuid_filename = row[0] if row else None
        if not uuid_filename:
            raise HTTPException(status_code=404, detail="No banner to delete")
        cursor.execute("UPDATE communities SET banner_picture_uuid = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (community_id,))
        conn.commit()
    delete_community_banner(uuid_filename)
    return {"message": "Banner deleted"} 

@router.get("/{community_id}/post-tags", response_model=List[CommunityPostTagResponse])
def list_post_tags(community_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, community_id, name, color FROM community_post_tags WHERE community_id = ? ORDER BY name ASC", (community_id,))
        rows = cursor.fetchall()
        return [CommunityPostTagResponse(id=row[0], community_id=row[1], name=row[2], color=row[3]) for row in rows]

@router.post("/{community_id}/post-tags", response_model=CommunityPostTagResponse)
def create_post_tag(community_id: int, tag: CommunityPostTagCreate, current_user_id: int = Depends(get_current_user_id)):
    if not get_user_community_role(community_id, current_user_id) in ['owner', 'moderator']:
        raise HTTPException(status_code=403, detail="Only mods/owners can create post tags")
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO community_post_tags (community_id, name, color) VALUES (?, ?, ?)", (community_id, tag.name, tag.color))
            tag_id = cursor.lastrowid
            conn.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Tag name must be unique and ≤30 chars")
    return CommunityPostTagResponse(id=tag_id, community_id=community_id, name=tag.name, color=tag.color)

@router.put("/{community_id}/post-tags/{tag_id}", response_model=CommunityPostTagResponse)
def update_post_tag(community_id: int, tag_id: int, tag: CommunityPostTagUpdate, current_user_id: int = Depends(get_current_user_id)):
    if not get_user_community_role(community_id, current_user_id) in ['owner', 'moderator']:
        raise HTTPException(status_code=403, detail="Only mods/owners can update post tags")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM community_post_tags WHERE id = ? AND community_id = ?", (tag_id, community_id))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Tag not found")
        update_fields = []
        params = []
        if tag.name is not None:
            update_fields.append("name = ?")
            params.append(tag.name)
        if tag.color is not None:
            update_fields.append("color = ?")
            params.append(tag.color)
        if update_fields:
            params.append(tag_id)
            cursor.execute(f"UPDATE community_post_tags SET {', '.join(update_fields)} WHERE id = ?", params)
            conn.commit()
    # Return updated tag
    cursor.execute("SELECT id, community_id, name, color FROM community_post_tags WHERE id = ?", (tag_id,))
    row = cursor.fetchone()
    return CommunityPostTagResponse(id=row[0], community_id=row[1], name=row[2], color=row[3])

@router.delete("/{community_id}/post-tags/{tag_id}")
def delete_post_tag(community_id: int, tag_id: int, current_user_id: int = Depends(get_current_user_id)):
    if not get_user_community_role(community_id, current_user_id) in ['owner', 'moderator']:
        raise HTTPException(status_code=403, detail="Only mods/owners can delete post tags")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM community_post_tags WHERE id = ? AND community_id = ?", (tag_id, community_id))
        conn.commit()
    return {"msg": "Tag deleted"} 

@router.get("/{community_id}/is-member")
def is_user_member_of_community(community_id: int, current_user_id: int = Depends(get_current_user_id)):
    """Check if the logged-in user is a member of the given community."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM community_members WHERE community_id = ? AND user_id = ?", (community_id, current_user_id))
        is_member = cursor.fetchone() is not None
    return {"is_member": is_member} 