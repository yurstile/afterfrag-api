from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
import json
from database import get_db
from schemas.communities import CommunityResponse
from auth import verify_token
from file_utils import get_community_group_picture_url
import random

router = APIRouter(prefix="/browse", tags=["browse"])
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

def has_completed_onboarding(user_id: int) -> bool:
    """Check if user has completed onboarding"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_topics WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        return count >= 3

def get_user_topics(user_id: int) -> List[str]:
    """Get user's preferred topics"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT topic FROM user_topics WHERE user_id = ?", (user_id,))
        return [row[0] for row in cursor.fetchall()]

def get_community_member_count(community_id: int) -> int:
    """Get community member count"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM community_members WHERE community_id = ?", (community_id,))
        return cursor.fetchone()[0]

def get_community_online_member_count(community_id: int) -> int:
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

def calculate_relevance_score(community_tags: List[str], user_topics: List[str]) -> float:
    """Calculate relevance score based on matching topics"""
    if not user_topics:
        return 0.0
    
    matching_topics = set(community_tags) & set(user_topics)
    return len(matching_topics) / len(user_topics)

@router.get("/communities", response_model=List[CommunityResponse])
def browse_communities(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id)
):
    """Browse communities based on user's preferred topics, with fallback to trending if no matches."""
    # Check if user has completed onboarding
    if not has_completed_onboarding(current_user_id):
        raise HTTPException(
            status_code=400, 
            detail="You must complete onboarding first. Please select at least 3 topics of interest."
        )
    
    user_topics = get_user_topics(current_user_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get all communities with their tags
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                   u.username as owner_username, c.group_picture_uuid
            FROM communities c
            JOIN users u ON c.owner_id = u.id
        """)
        rows = cursor.fetchall()
        
        # Calculate relevance scores and filter communities
        communities_with_scores = []
        for row in rows:
            community_tags = json.loads(row[3])
            relevance_score = calculate_relevance_score(community_tags, user_topics)
            
            # Only include communities that have at least one matching topic
            if relevance_score > 0:
                member_count = get_community_member_count(row[0])
                online_member_count = get_community_online_member_count(row[0])
                communities_with_scores.append({
                    "community": {
                        "id": row[0], "name": row[1], "description": row[2], 
                        "tags": community_tags, "owner_id": row[4], 
                        "created_at": row[5], "updated_at": row[6], 
                        "owner_username": row[7], "member_count": member_count,
                        "online_member_count": online_member_count,
                        "group_picture_uuid": row[8]
                    },
                    "relevance_score": relevance_score,
                    "matching_topics": list(set(community_tags) & set(user_topics))
                })
        
        # If no matches, fallback to trending (by member count)
        if not communities_with_scores:
            fallback_communities = []
            cursor.execute("""
                SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                       u.username as owner_username, c.group_picture_uuid,
                       COUNT(cm.user_id) as member_count
                FROM communities c
                JOIN users u ON c.owner_id = u.id
                LEFT JOIN community_members cm ON c.id = cm.community_id
                GROUP BY c.id
                ORDER BY member_count DESC, c.updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, skip))
            fallback_rows = cursor.fetchall()
            for row in fallback_rows:
                online_member_count = get_community_online_member_count(row[0])
                fallback_communities.append({
                    "community": {
                        "id": row[0], "name": row[1], "description": row[2],
                        "tags": json.loads(row[3]), "owner_id": row[4],
                        "created_at": row[5], "updated_at": row[6],
                        "owner_username": row[7], "member_count": row[9],
                        "online_member_count": online_member_count,
                        "group_picture_uuid": row[8]
                    },
                    "relevance_score": 0.0,
                    "matching_topics": []
                })
            communities_with_scores = fallback_communities
        else:
            # Sort by relevance score (highest first), then by member count, then by creation date
            communities_with_scores.sort(
                key=lambda x: (x["relevance_score"], x["community"]["member_count"], x["community"]["created_at"]),
                reverse=True
            )
            random.shuffle(communities_with_scores)
            # Apply pagination
            start_idx = skip
            end_idx = start_idx + limit
            communities_with_scores = communities_with_scores[start_idx:end_idx]
        
        # Convert to CommunityResponse objects
        result = []
        for item in communities_with_scores:
            community_data = item["community"]
            result.append(CommunityResponse(
                id=community_data["id"],
                name=community_data["name"],
                description=community_data["description"],
                tags=community_data["tags"],
                owner_id=community_data["owner_id"],
                owner_username=community_data["owner_username"],
                member_count=community_data["member_count"],
                online_member_count=community_data["online_member_count"],
                created_at=community_data["created_at"],
                updated_at=community_data["updated_at"],
                group_picture_url=get_community_group_picture_url(community_data["group_picture_uuid"])
            ))
        
        return result

@router.get("/communities/recommended", response_model=List[CommunityResponse])
def get_recommended_communities(
    limit: int = Query(5, ge=1, le=20),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get top recommended communities for the user, with fallback to trending if no matches."""
    # Check if user has completed onboarding
    if not has_completed_onboarding(current_user_id):
        raise HTTPException(
            status_code=400, 
            detail="You must complete onboarding first. Please select at least 3 topics of interest."
        )
    
    user_topics = get_user_topics(current_user_id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get communities with high relevance scores
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                   u.username as owner_username, c.group_picture_uuid
            FROM communities c
            JOIN users u ON c.owner_id = u.id
        """)
        rows = cursor.fetchall()
        
        # Calculate relevance scores
        communities_with_scores = []
        for row in rows:
            community_tags = json.loads(row[3])
            relevance_score = calculate_relevance_score(community_tags, user_topics)
            
            if relevance_score > 0:
                member_count = get_community_member_count(row[0])
                online_member_count = get_community_online_member_count(row[0])
                communities_with_scores.append({
                    "community": {
                        "id": row[0], "name": row[1], "description": row[2], 
                        "tags": community_tags, "owner_id": row[4], 
                        "created_at": row[5], "updated_at": row[6], 
                        "owner_username": row[7], "member_count": member_count,
                        "online_member_count": online_member_count,
                        "group_picture_uuid": row[8]
                    },
                    "relevance_score": relevance_score
                })
        
        # If no matches, fallback to trending (by member count)
        if not communities_with_scores:
            fallback_communities = []
            cursor.execute("""
                SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                       u.username as owner_username, c.group_picture_uuid,
                       COUNT(cm.user_id) as member_count
                FROM communities c
                JOIN users u ON c.owner_id = u.id
                LEFT JOIN community_members cm ON c.id = cm.community_id
                GROUP BY c.id
                ORDER BY member_count DESC, c.updated_at DESC
                LIMIT ?
            """, (limit,))
            fallback_rows = cursor.fetchall()
            for row in fallback_rows:
                online_member_count = get_community_online_member_count(row[0])
                fallback_communities.append({
                    "community": {
                        "id": row[0], "name": row[1], "description": row[2],
                        "tags": json.loads(row[3]), "owner_id": row[4],
                        "created_at": row[5], "updated_at": row[6],
                        "owner_username": row[7], "member_count": row[9],
                        "online_member_count": online_member_count,
                        "group_picture_uuid": row[8]
                    },
                    "relevance_score": 0.0
                })
            communities_with_scores = fallback_communities
        else:
            # Sort by relevance score and get top recommendations
            communities_with_scores.sort(key=lambda x: x["relevance_score"], reverse=True)
            random.shuffle(communities_with_scores)
            communities_with_scores = communities_with_scores[:limit]
        
        # Convert to CommunityResponse objects
        result = []
        for item in communities_with_scores:
            community_data = item["community"]
            result.append(CommunityResponse(
                id=community_data["id"],
                name=community_data["name"],
                description=community_data["description"],
                tags=community_data["tags"],
                owner_id=community_data["owner_id"],
                owner_username=community_data["owner_username"],
                member_count=community_data["member_count"],
                online_member_count=community_data["online_member_count"],
                created_at=community_data["created_at"],
                updated_at=community_data["updated_at"],
                group_picture_url=get_community_group_picture_url(community_data["group_picture_uuid"])
            ))
        
        return result

@router.get("/communities/trending", response_model=List[CommunityResponse])
def get_trending_communities(
    limit: int = Query(10, ge=1, le=50),
    skip: int = Query(0, ge=0)
):
    """Get trending communities (most members, recent activity)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get communities ordered by member count and recent activity
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.tags, c.owner_id, c.created_at, c.updated_at,
                   u.username as owner_username, c.group_picture_uuid,
                   COUNT(cm.user_id) as member_count
            FROM communities c
            JOIN users u ON c.owner_id = u.id
            LEFT JOIN community_members cm ON c.id = cm.community_id
            GROUP BY c.id
            ORDER BY member_count DESC, c.updated_at DESC
            LIMIT ? OFFSET ?
        """, (limit, skip))
        
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            online_member_count = get_community_online_member_count(row[0])
            result.append(CommunityResponse(
                id=row[0], name=row[1], description=row[2], 
                tags=json.loads(row[3]), owner_id=row[4], 
                created_at=row[5], updated_at=row[6], 
                owner_username=row[7], member_count=row[9],
                online_member_count=online_member_count,
                group_picture_url=get_community_group_picture_url(row[8])
            ))
        
        return result 