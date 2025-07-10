from fastapi import APIRouter, HTTPException, Depends
from database import get_db
from auth import verify_token
from datetime import datetime, timedelta

router = APIRouter(prefix="/admin", tags=["admin"])

from routes.profile import get_current_user_id

def require_admin(current_user_id: int = Depends(get_current_user_id)):
    if current_user_id == 1:
        return current_user_id
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = ?", (current_user_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=403, detail="Admin access required")
        return current_user_id

@router.post("/moderate/{content_type}/{content_id}")
def moderate_content(content_type: str, content_id: int, reason: str = "", admin_note: str = "", current_user_id: int = Depends(require_admin)):
    """Moderate a post, comment, or community. Replaces content with [ moderated ], removes media, and records action."""
    with get_db() as conn:
        cursor = conn.cursor()
        if content_type == "post":
            cursor.execute("UPDATE posts SET content = '[ moderated ]' WHERE id = ?", (content_id,))
            cursor.execute("DELETE FROM post_media WHERE post_id = ?", (content_id,))
            cursor.execute("SELECT user_id FROM posts WHERE id = ?", (content_id,))
            user_id = cursor.fetchone()[0]
        elif content_type == "comment":
            cursor.execute("UPDATE comments SET content = '[ moderated ]' WHERE id = ?", (content_id,))
            cursor.execute("DELETE FROM comment_media WHERE comment_id = ?", (content_id,))
            cursor.execute("SELECT user_id FROM comments WHERE id = ?", (content_id,))
            user_id = cursor.fetchone()[0]
        elif content_type == "community":
            cursor.execute("UPDATE communities SET description = '[ moderated ]' WHERE id = ?", (content_id,))
            cursor.execute("SELECT owner_id FROM communities WHERE id = ?", (content_id,))
            user_id = cursor.fetchone()[0]
        else:
            raise HTTPException(status_code=400, detail="Invalid content type")
        cursor.execute("INSERT INTO moderation_actions (user_id, admin_id, content_type, content_id, action, reason, admin_note) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, current_user_id, content_type, content_id, 'moderated', reason, admin_note))
        conn.commit()
    return {"status": "ok"}

@router.post("/ban/{user_id}")
def ban_user(user_id: int, days: int, reason: str = "", admin_note: str = "", current_user_id: int = Depends(require_admin)):
    """Ban a user for 1, 3, or 7 days. Records action."""
    if days not in [1, 3, 7]:
        raise HTTPException(status_code=400, detail="Ban must be 1, 3, or 7 days")
    banned_until = (datetime.utcnow() + timedelta(days=days)).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET banned_until = ? WHERE id = ?", (banned_until, user_id))
        cursor.execute("INSERT INTO moderation_actions (user_id, admin_id, content_type, content_id, action, reason, admin_note) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, current_user_id, 'user', user_id, f'ban_{days}d', reason, admin_note))
        conn.commit()
    return {"status": "ok", "banned_until": banned_until}

@router.post("/terminate/{user_id}")
def terminate_user(user_id: int, reason: str = "", admin_note: str = "", current_user_id: int = Depends(require_admin)):
    """Terminate a user account. Records action."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_terminated = 1 WHERE id = ?", (user_id,))
        cursor.execute("INSERT INTO moderation_actions (user_id, admin_id, content_type, content_id, action, reason, admin_note) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, current_user_id, 'user', user_id, 'terminate', reason, admin_note))
        conn.commit()
    return {"status": "ok"}

@router.post("/grant-admin/{user_id}")
def grant_admin(user_id: int, reason: str = "", admin_note: str = "", current_user_id: int = Depends(require_admin)):
    """Grant admin status to a user. Records action."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        cursor.execute("INSERT INTO moderation_actions (user_id, admin_id, content_type, content_id, action, reason, admin_note) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, current_user_id, 'user', user_id, 'admin_grant', reason, admin_note))
        conn.commit()
    return {"status": "ok"}

@router.post("/revoke-admin/{user_id}")
def revoke_admin(user_id: int, reason: str = "", admin_note: str = "", current_user_id: int = Depends(require_admin)):
    """Revoke admin status from a user. Records action."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
        cursor.execute("INSERT INTO moderation_actions (user_id, admin_id, content_type, content_id, action, reason, admin_note) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, current_user_id, 'user', user_id, 'admin_revoke', reason, admin_note))
        conn.commit()
    return {"status": "ok"}

@router.get("/moderation-history/{user_id}")
def get_moderation_history(user_id: int, current_user_id: int = Depends(require_admin)):
    """Get moderation history for a user."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM moderation_actions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cursor.fetchall()
    return {"history": rows}

@router.get("/search-users")
def search_users(query: str = "", user_id: int = None, current_user_id: int = Depends(require_admin)):
    """Admin: Search for users by username (partial match) or user ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute("SELECT id, username, is_admin, is_terminated, banned_until FROM users WHERE id = ?", (user_id,))
            users = cursor.fetchall()
        elif query:
            cursor.execute("SELECT id, username, is_admin, is_terminated, banned_until FROM users WHERE username LIKE ? LIMIT 20", (f"%{query}%",))
            users = cursor.fetchall()
        else:
            users = []
    return [
        {
            "id": u[0],
            "username": u[1],
            "is_admin": bool(u[2]),
            "is_terminated": bool(u[3]),
            "banned_until": u[4]
        }
        for u in users
    ]

@router.get("/communities")
def search_communities(search: str = "", current_user_id: int = Depends(require_admin)):
    """Admin: Search for communities by name (partial match)."""
    with get_db() as conn:
        cursor = conn.cursor()
        if search:
            cursor.execute("""
                SELECT c.id, c.name, c.description, c.owner_id, u.username, c.created_at,
                       (SELECT COUNT(*) FROM community_members WHERE community_id = c.id) as member_count
                FROM communities c
                JOIN users u ON c.owner_id = u.id
                WHERE c.name LIKE ?
                ORDER BY c.created_at DESC
                LIMIT 20
            """, (f"%{search}%",))
        else:
            cursor.execute("""
                SELECT c.id, c.name, c.description, c.owner_id, u.username, c.created_at,
                       (SELECT COUNT(*) FROM community_members WHERE community_id = c.id) as member_count
                FROM communities c
                JOIN users u ON c.owner_id = u.id
                ORDER BY c.created_at DESC
                LIMIT 20
            """)
        rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "owner_id": r[3],
            "owner_username": r[4],
            "created_at": r[5],
            "member_count": r[6],
        }
        for r in rows
    ] 