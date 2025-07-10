from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, Form
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from datetime import datetime
import os
from database import get_db
from schemas import CommentCreate, CommentUpdate, CommentResponse, CommentMedia, CommentLikeRequest
from auth import verify_token
from file_utils import generate_uuid_filename
from routes.communities import get_user_community_role

router = APIRouter(prefix="/comments", tags=["comments"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MEDIA_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.mov', '.avi', '.webm'}
COMMENT_MEDIA_UPLOAD_FOLDER = os.path.join("uploads", "comments")

def ensure_comment_media_upload_dir():
    os.makedirs(COMMENT_MEDIA_UPLOAD_FOLDER, exist_ok=True)

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

def get_comment_media(comment_id: int) -> List[CommentMedia]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_uuid, file_type, file_size FROM comment_media WHERE comment_id = ?", (comment_id,))
        rows = cursor.fetchall()
        return [CommentMedia(file_uuid=r[0], file_type=r[1], file_size=r[2], url=f"/cdn/comments/{r[0]}") for r in rows]

def get_comment_response(comment_id: int) -> CommentResponse:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")
        # Get author info
        cursor.execute("SELECT username FROM users WHERE id = ?", (row[2],))
        author_username = cursor.fetchone()[0]
        cursor.execute("SELECT display_name, profile_picture_uuid FROM user_profiles WHERE user_id = ?", (row[2],))
        profile = cursor.fetchone()
        display_name = profile[0] if profile else author_username
        profile_picture_url = None
        if profile and profile[1]:
            profile_picture_url = f"/cdn/users/profilepictures/{profile[1]}"
        media = get_comment_media(comment_id)
        return CommentResponse(
            id=row[0],
            post_id=row[1],
            user_id=row[2],
            content=row[3],
            parent_id=row[4],
            like_count=row[5] if row[5] is not None else 0,
            created_at=row[6],
            updated_at=row[7],
            media=media,
            author_username=author_username,
            author_display_name=display_name,
            author_profile_picture_url=profile_picture_url
        )

def get_comment_tree(post_id: int) -> List[CommentResponse]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM comments WHERE post_id = ? ORDER BY created_at ASC", (post_id,))
        all_ids = [row[0] for row in cursor.fetchall()]
        comments = {}
        for cid in all_ids:
            comments[cid] = get_comment_response(cid)
        # Build tree
        tree = []
        for comment in comments.values():
            if comment.parent_id and comment.parent_id in comments:
                parent = comments[comment.parent_id]
                if parent.children is None:
                    parent.children = []
                parent.children.append(comment)
            else:
                tree.append(comment)
        return tree

@router.post("/post/{post_id}", response_model=CommentResponse)
async def create_comment(
    post_id: int,
    content: str = Form(...),
    parent_id: int = Form(None),
    file: UploadFile = File(None),
    current_user_id: int = Depends(get_current_user_id)
):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO comments (post_id, user_id, content, parent_id) VALUES (?, ?, ?, ?)", (post_id, current_user_id, content, parent_id))
        comment_id = cursor.lastrowid
        # Handle file upload
        if file is not None:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED_MEDIA_EXTENSIONS:
                raise HTTPException(status_code=400, detail="Unsupported file type.")
            content_bytes = await file.read()
            if len(content_bytes) > MAX_MEDIA_SIZE:
                raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")
            uuid_filename = generate_uuid_filename(file.filename)
            file_path = os.path.join(COMMENT_MEDIA_UPLOAD_FOLDER, uuid_filename)
            ensure_comment_media_upload_dir()
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
            cursor.execute(
                "INSERT INTO comment_media (comment_id, file_uuid, file_type, file_size) VALUES (?, ?, ?, ?)",
                (comment_id, uuid_filename, 'video' if ext in {'.mp4', '.mov', '.avi', '.webm'} else 'image', len(content_bytes))
            )
        conn.commit()
    return get_comment_response(comment_id)

@router.put("/{comment_id}", response_model=CommentResponse)
def edit_comment(comment_id: int, comment: CommentUpdate, current_user_id: int = Depends(get_current_user_id)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")
        author_id = row[0]
        if author_id != current_user_id:
            raise HTTPException(status_code=403, detail="You can only edit your own comment.")
        fields = []
        params = []
        if comment.content is not None:
            fields.append("content = ?")
            params.append(comment.content)
        if comment.media is not None:
            cursor.execute("DELETE FROM comment_media WHERE comment_id = ?", (comment_id,))
            for media in comment.media:
                cursor.execute(
                    "INSERT INTO comment_media (comment_id, file_uuid, file_type, file_size) VALUES (?, ?, ?, ?)",
                    (comment_id, media.file_uuid, media.file_type, media.file_size)
                )
        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(comment_id)
            cursor.execute(f"UPDATE comments SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    return get_comment_response(comment_id)

@router.delete("/{comment_id}")
def delete_comment(comment_id: int, current_user_id: int = Depends(get_current_user_id)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, post_id FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")
        author_id, post_id = row
        # Get community_id for mod/owner check
        cursor.execute("SELECT community_id FROM posts WHERE id = ?", (post_id,))
        post_row = cursor.fetchone()
        if not post_row:
            raise HTTPException(status_code=404, detail="Post not found")
        community_id = post_row[0]
        if author_id != current_user_id:
            role = get_user_community_role(community_id, current_user_id)
            if role not in ("owner", "moderator"):
                raise HTTPException(status_code=403, detail="You do not have permission to delete this comment.")
        cursor.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        cursor.execute("DELETE FROM comment_media WHERE comment_id = ?", (comment_id,))
        conn.commit()
    return {"msg": "Comment deleted"}

@router.get("/post/{post_id}", response_model=List[CommentResponse])
def list_comments(post_id: int):
    return get_comment_tree(post_id)

@router.get("/{comment_id}", response_model=CommentResponse)
def get_single_comment(comment_id: int):
    """
    Fetch a single comment and its thread (children) by comment_id.
    Returns the comment with its nested replies (children).
    """
    # Reuse get_comment_response, then build children tree for this comment only
    comment = get_comment_response(comment_id)
    # Fetch all comments with the same post_id
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, parent_id FROM comments WHERE post_id = ? ORDER BY created_at ASC", (comment.post_id,))
        all_rows = cursor.fetchall()
        # Build a map of id -> comment
        comments = {}
        for row in all_rows:
            cid = row[0]
            comments[cid] = get_comment_response(cid)
        # Build tree for this comment only
        for c in comments.values():
            if c.parent_id and c.parent_id in comments:
                parent = comments[c.parent_id]
                if parent.children is None:
                    parent.children = []
                parent.children.append(c)
        # Return the requested comment (with children attached)
        return comments[comment_id]

@router.post("/upload-media")
def upload_comment_media(file: UploadFile = File(...), current_user_id: int = Depends(get_current_user_id)):
    ensure_comment_media_upload_dir()
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type.")
    content = file.file.read()
    if len(content) > MAX_MEDIA_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")
    uuid_filename = generate_uuid_filename(file.filename)
    file_path = os.path.join(COMMENT_MEDIA_UPLOAD_FOLDER, uuid_filename)
    with open(file_path, 'wb') as f:
        f.write(content)
    return {"file_uuid": uuid_filename, "file_type": "video" if ext in {'.mp4', '.mov', '.avi', '.webm'} else "image", "file_size": len(content), "url": f"/cdn/comments/{uuid_filename}"}

@router.post("/{comment_id}/like")
def like_comment(comment_id: int, req: CommentLikeRequest, current_user_id: int = Depends(get_current_user_id)):
    if req.value not in (1, -1):
        raise HTTPException(status_code=400, detail="Invalid like value.")
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if comment exists
        cursor.execute("SELECT id FROM comments WHERE id = ?", (comment_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Comment not found")
        # Check if user already liked/disliked
        cursor.execute("SELECT value FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, current_user_id))
        row = cursor.fetchone()
        if row:
            # Update like/dislike
            cursor.execute("UPDATE comment_likes SET value = ? WHERE comment_id = ? AND user_id = ?", (req.value, comment_id, current_user_id))
            # Adjust like_count
            cursor.execute("UPDATE comments SET like_count = like_count + (? - ?) WHERE id = ?", (req.value, row[0], comment_id))
        else:
            cursor.execute("INSERT INTO comment_likes (comment_id, user_id, value) VALUES (?, ?, ?)", (comment_id, current_user_id, req.value))
            cursor.execute("UPDATE comments SET like_count = like_count + ? WHERE id = ?", (req.value, comment_id))
        conn.commit()
    return {"msg": "Like/dislike updated"}

@router.delete("/{comment_id}/like")
def unlike_comment(comment_id: int, current_user_id: int = Depends(get_current_user_id)):
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if user has liked/disliked
        cursor.execute("SELECT value FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, current_user_id))
        row = cursor.fetchone()
        if not row:
            return {"msg": "No like/dislike to remove"}
        value = row[0]
        # Remove like/dislike
        cursor.execute("DELETE FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, current_user_id))
        cursor.execute("UPDATE comments SET like_count = like_count - ? WHERE id = ?", (value, comment_id))
        conn.commit()
    return {"msg": "Like/dislike removed"}

@router.get("/{comment_id}/like-status")
def get_comment_like_status(comment_id: int, current_user_id: int = Depends(get_current_user_id)):
    """Get current user's like status for a comment"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Check if comment exists
        cursor.execute("SELECT id FROM comments WHERE id = ?", (comment_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Comment not found")
        
        # Get user's like status
        cursor.execute("SELECT value FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, current_user_id))
        row = cursor.fetchone()
        
        return {
            "value": row[0] if row else None
        }

@router.post("/{comment_id}/reply", response_model=CommentResponse)
async def reply_to_comment(
    comment_id: int,
    content: str = Form(...),
    file: UploadFile = File(None),
    current_user_id: int = Depends(get_current_user_id)
):
    # Find the parent comment to get the post_id
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT post_id FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Parent comment not found")
        post_id = row[0]
        # Create the reply with parent_id=comment_id
        cursor.execute("INSERT INTO comments (post_id, user_id, content, parent_id) VALUES (?, ?, ?, ?)", (post_id, current_user_id, content, comment_id))
        reply_id = cursor.lastrowid
        # Handle file upload
        if file is not None:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED_MEDIA_EXTENSIONS:
                raise HTTPException(status_code=400, detail="Unsupported file type.")
            content_bytes = await file.read()
            if len(content_bytes) > MAX_MEDIA_SIZE:
                raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")
            uuid_filename = generate_uuid_filename(file.filename)
            file_path = os.path.join(COMMENT_MEDIA_UPLOAD_FOLDER, uuid_filename)
            ensure_comment_media_upload_dir()
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
            cursor.execute(
                "INSERT INTO comment_media (comment_id, file_uuid, file_type, file_size) VALUES (?, ?, ?, ?)",
                (reply_id, uuid_filename, 'video' if ext in {'.mp4', '.mov', '.avi', '.webm'} else 'image', len(content_bytes))
            )
        conn.commit()
    return get_comment_response(reply_id) 