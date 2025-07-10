from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, Query, Form
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from datetime import datetime, timedelta
import json
import os
from database import get_db
from schemas import PostCreate, PostUpdate, PostResponse, PostLikeRequest, PostMedia, CommunityPostTagResponse, PostResponseWithComments, CommentResponse
from auth import verify_token
from file_utils import generate_uuid_filename
from utils.route_helpers import get_user_community_role
from routes.comments import get_comment_tree
from routes.communities import get_community_by_id
from file_utils import get_community_group_picture_url

router = APIRouter(prefix="/posts", tags=["posts"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MEDIA_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.avi', '.webm'}
MEDIA_UPLOAD_FOLDER = os.path.join("uploads", "posts")

# Ensure media upload directory exists
def ensure_media_upload_dir():
    os.makedirs(MEDIA_UPLOAD_FOLDER, exist_ok=True)

# Helper: get current user id from token
def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (payload.get("sub"),))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return row[0]

# Helper: check if user is a member of the community
def is_community_member(community_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM community_members WHERE community_id = ? AND user_id = ?", (community_id, user_id))
        return cursor.fetchone() is not None

# Helper: get post by id
def get_post_by_id(post_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        return row

# Helper: get post media
def get_post_media(post_id: int) -> List[PostMedia]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_uuid, file_type, file_size FROM post_media WHERE post_id = ?", (post_id,))
        rows = cursor.fetchall()
        return [PostMedia(file_uuid=r[0], file_type=r[1], file_size=r[2], url=f"/cdn/posts/{r[0]}") for r in rows]

def get_post_tags(post_id: int) -> List[CommunityPostTagResponse]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.community_id, t.name, t.color
            FROM community_post_tags t
            JOIN post_post_tags ppt ON ppt.tag_id = t.id
            WHERE ppt.post_id = ?
            ORDER BY t.name ASC
        """, (post_id,))
        rows = cursor.fetchall()
        return [CommunityPostTagResponse(id=row[0], community_id=row[1], name=row[2], color=row[3]) for row in rows]

class PostResponseWithComments(PostResponse):
    comment_count: int
    comments: Optional[List['CommentResponse']] = None

def get_comment_count(post_id: int) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (post_id,))
        return cursor.fetchone()[0]

@router.post("/", response_model=PostResponse)
def create_post(
    community_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    post_tag_ids: Optional[str] = Form("[]"),  # JSON string
    media: Optional[List[UploadFile]] = File(None),
    current_user_id: int = Depends(get_current_user_id)
):
    # Parse post_tag_ids
    if post_tag_ids is None:
        tag_ids = []
    else:
        try:
            tag_ids = json.loads(post_tag_ids)
        except Exception:
            tag_ids = []
    # Check membership
    if not is_community_member(community_id, current_user_id):
        raise HTTPException(status_code=403, detail="You must join the community to post.")
    with get_db() as conn:
        cursor = conn.cursor()
        if tag_ids:
            cursor.execute("SELECT id FROM community_post_tags WHERE community_id = ?", (community_id,))
            valid_tag_ids = {row[0] for row in cursor.fetchall()}
            if not set(tag_ids).issubset(valid_tag_ids):
                raise HTTPException(status_code=400, detail="Invalid post tag(s) for this community.")
        # Insert post
        cursor.execute(
            "INSERT INTO posts (community_id, user_id, title, content) VALUES (?, ?, ?, ?)",
            (community_id, current_user_id, title, content)
        )
        post_id = cursor.lastrowid
        # Insert post tags
        if tag_ids:
            for tag_id in tag_ids:
                cursor.execute("INSERT INTO post_post_tags (post_id, tag_id) VALUES (?, ?)", (post_id, tag_id))
        # Insert media if any
        if media:
            from file_utils import generate_uuid_filename, POSTS_MEDIA_FOLDER, ensure_post_media_directory
            import os
            ensure_post_media_directory()
            for file in media:
                ext = os.path.splitext(file.filename)[1].lower()
                file_content = file.file.read()
                uuid_filename = generate_uuid_filename(file.filename)
                file_path = os.path.join(POSTS_MEDIA_FOLDER, uuid_filename)
                with open(file_path, 'wb') as f:
                    f.write(file_content)
                file_type = 'video' if ext in {'.mp4', '.mov', '.avi', '.webm'} else 'image'
                file_size = len(file_content)
                cursor.execute(
                    "INSERT INTO post_media (post_id, file_uuid, file_type, file_size) VALUES (?, ?, ?, ?)",
                    (post_id, uuid_filename, file_type, file_size)
                )
        conn.commit()
    if post_id is None:
        raise HTTPException(status_code=500, detail="Failed to create post.")
    return get_post_response(post_id)

@router.post("/upload-media")
def upload_post_media(file: UploadFile = File(...), current_user_id: int = Depends(get_current_user_id)):
    ensure_media_upload_dir()
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type.")
    content = file.file.read()
    if len(content) > MAX_MEDIA_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")
    uuid_filename = generate_uuid_filename(file.filename)
    file_path = os.path.join(MEDIA_UPLOAD_FOLDER, uuid_filename)
    with open(file_path, 'wb') as f:
        f.write(content)
    return {"file_uuid": uuid_filename, "file_type": "video" if ext in {'.mp4', '.mov', '.avi', '.webm'} else "image", "file_size": len(content), "url": f"/cdn/posts/{uuid_filename}"}

@router.get("/{post_id}", response_model=PostResponseWithComments)
def get_post(post_id: int):
    return get_post_response(post_id)

def get_post_response(post_id: int) -> PostResponseWithComments:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")
        # Get author info
        cursor.execute("SELECT username FROM users WHERE id = ?", (row[2],))
        author_username = cursor.fetchone()[0]
        # Get display name and profile picture
        cursor.execute("SELECT display_name, profile_picture_uuid FROM user_profiles WHERE user_id = ?", (row[2],))
        profile = cursor.fetchone()
        display_name = profile[0] if profile else author_username
        profile_picture_url = None
        if profile and profile[1]:
            profile_picture_url = f"/cdn/users/profilepictures/{profile[1]}"
        # Get media
        media = get_post_media(post_id)
        # Get post tags
        post_tags = get_post_tags(post_id)
        # Get comment count
        comment_count = get_comment_count(post_id)
        # Get comment tree
        comments = get_comment_tree(post_id)
        # Get group info
        community = get_community_by_id(row[1])
        group_name = community["name"] if community else None
        group_logo_url = get_community_group_picture_url(community["group_picture_uuid"]) if community else None
        return PostResponseWithComments(
            id=row[0],
            community_id=row[1],
            user_id=row[2],
            title=row[3],
            content=row[4],
            post_tags=post_tags,
            like_count=row[6],
            view_count=row[7],
            created_at=row[8],
            updated_at=row[9],
            media=media,
            author_username=author_username,
            author_display_name=display_name,
            author_profile_picture_url=profile_picture_url,
            comment_count=comment_count,
            comments=comments,
            group_name=group_name,
            group_logo_url=group_logo_url
        )

@router.post("/{post_id}/like")
def like_post(post_id: int, req: PostLikeRequest, current_user_id: int = Depends(get_current_user_id)):
    if req.value not in (1, -1):
        raise HTTPException(status_code=400, detail="Invalid like value.")
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if post exists
        cursor.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Post not found")
        # Check if user already liked/disliked
        cursor.execute("SELECT value FROM post_likes WHERE post_id = ? AND user_id = ?", (post_id, current_user_id))
        row = cursor.fetchone()
        if row:
            # Update like/dislike
            cursor.execute("UPDATE post_likes SET value = ? WHERE post_id = ? AND user_id = ?", (req.value, post_id, current_user_id))
            # Adjust like_count
            cursor.execute("UPDATE posts SET like_count = like_count + (? - ?) WHERE id = ?", (req.value, row[0], post_id))
        else:
            cursor.execute("INSERT INTO post_likes (post_id, user_id, value) VALUES (?, ?, ?)", (post_id, current_user_id, req.value))
            cursor.execute("UPDATE posts SET like_count = like_count + ? WHERE id = ?", (req.value, post_id))
        conn.commit()
    return {"msg": "Like/dislike updated"}

@router.delete("/{post_id}/like")
def unlike_post(post_id: int, current_user_id: int = Depends(get_current_user_id)):
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if user has liked/disliked
        cursor.execute("SELECT value FROM post_likes WHERE post_id = ? AND user_id = ?", (post_id, current_user_id))
        row = cursor.fetchone()
        if not row:
            return {"msg": "No like/dislike to remove"}
        value = row[0]
        # Remove like/dislike
        cursor.execute("DELETE FROM post_likes WHERE post_id = ? AND user_id = ?", (post_id, current_user_id))
        cursor.execute("UPDATE posts SET like_count = like_count - ? WHERE id = ?", (value, post_id))
        conn.commit()
    return {"msg": "Like/dislike removed"}

@router.get("/{post_id}/like-status")
def get_post_like_status(post_id: int, current_user_id: int = Depends(get_current_user_id)):
    """Get current user's like status for a post"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if post exists
        cursor.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Get user's like status
        cursor.execute("SELECT value FROM post_likes WHERE post_id = ? AND user_id = ?", (post_id, current_user_id))
        row = cursor.fetchone()
        
        return {
            "value": row[0] if row else None
        }

@router.post("/{post_id}/view")
def view_post(post_id: int, request: Request, current_user_id: int = Depends(get_current_user_id)):
    # Anti-spam: only count one view per user/IP per 10 minutes
    ip = request.client.host
    now = datetime.utcnow()
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if post exists
        cursor.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Post not found")
        # Check if view exists in last 10 minutes
        cursor.execute(
            "SELECT viewed_at FROM post_views WHERE post_id = ? AND (user_id = ? OR ip_address = ?) ORDER BY viewed_at DESC LIMIT 1",
            (post_id, current_user_id, ip)
        )
        row = cursor.fetchone()
        if row:
            last_view = datetime.fromisoformat(row[0]) if isinstance(row[0], str) else row[0]
            if (now - last_view) < timedelta(minutes=10):
                return {"msg": "View already counted recently"}
        # Insert new view
        cursor.execute("INSERT OR REPLACE INTO post_views (post_id, user_id, ip_address, viewed_at) VALUES (?, ?, ?, ?)", (post_id, current_user_id, ip, now.isoformat()))
        cursor.execute("UPDATE posts SET view_count = view_count + 1 WHERE id = ?", (post_id,))
        conn.commit()
    return {"msg": "View counted"}

@router.put("/{post_id}", response_model=PostResponse)
def edit_post(post_id: int, post: PostUpdate, current_user_id: int = Depends(get_current_user_id)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, community_id FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")
        author_id, community_id = row
        if author_id != current_user_id:
            raise HTTPException(status_code=403, detail="You can only edit your own post.")
        # Validate post_tag_ids if provided
        if post.post_tag_ids is not None:
            cursor.execute("SELECT id FROM community_post_tags WHERE community_id = ?", (community_id,))
            valid_tag_ids = {row[0] for row in cursor.fetchall()}
            if not set(post.post_tag_ids).issubset(valid_tag_ids):
                raise HTTPException(status_code=400, detail="Invalid post tag(s) for this community.")
        # Build update query
        fields = []
        params = []
        if post.title is not None:
            fields.append("title = ?")
            params.append(post.title)
        if post.content is not None:
            fields.append("content = ?")
            params.append(post.content)
        if post.media is not None:
            # Remove old media
            cursor.execute("DELETE FROM post_media WHERE post_id = ?", (post_id,))
            for media in post.media:
                cursor.execute(
                    "INSERT INTO post_media (post_id, file_uuid, file_type, file_size) VALUES (?, ?, ?, ?)",
                    (post_id, media.file_uuid, media.file_type, media.file_size)
                )
        if post.post_tag_ids is not None:
            cursor.execute("DELETE FROM post_post_tags WHERE post_id = ?", (post_id,))
            for tag_id in post.post_tag_ids:
                cursor.execute("INSERT INTO post_post_tags (post_id, tag_id) VALUES (?, ?)", (post_id, tag_id))
        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(post_id)
            cursor.execute(f"UPDATE posts SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return get_post_response(post_id)

@router.delete("/{post_id}")
def delete_post(post_id: int, current_user_id: int = Depends(get_current_user_id)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, community_id FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")
        author_id, community_id = row
        # Check if user is author or mod/owner
        if author_id != current_user_id:
            role = get_user_community_role(community_id, current_user_id)
            if role not in ("owner", "moderator"):
                raise HTTPException(status_code=403, detail="You do not have permission to delete this post.")
        # Delete post and related media/likes/views
        cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        cursor.execute("DELETE FROM post_media WHERE post_id = ?", (post_id,))
        cursor.execute("DELETE FROM post_likes WHERE post_id = ?", (post_id,))
        cursor.execute("DELETE FROM post_views WHERE post_id = ?", (post_id,))
        conn.commit()
    return {"msg": "Post deleted"}

@router.get("/community/{community_id}", response_model=List[PostResponseWithComments])
def list_community_posts(
    community_id: int,
    sort: str = Query("newest", enum=["newest", "most_liked", "hottest"]),
    tag_id: int = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    # Sorting logic
    order_by = {
        "newest": "created_at DESC",
        "most_liked": "like_count DESC",
        "hottest": "view_count DESC"
    }.get(sort, "created_at DESC")
    with get_db() as conn:
        cursor = conn.cursor()
        if tag_id:
            cursor.execute(f"""
                SELECT p.id FROM posts p
                JOIN post_post_tags ppt ON p.id = ppt.post_id
                WHERE p.community_id = ? AND ppt.tag_id = ?
                ORDER BY {order_by} LIMIT ? OFFSET ?
            """, (community_id, tag_id, limit, skip))
        else:
            cursor.execute(f"SELECT id FROM posts WHERE community_id = ? ORDER BY {order_by} LIMIT ? OFFSET ?", (community_id, limit, skip))
        rows = cursor.fetchall()
        return [get_post_response(row[0]) for row in rows] 