from fastapi import APIRouter, HTTPException, Request, status, Depends
from fastapi.security import OAuth2PasswordBearer
from schemas.auth import UserCreate, LoginRequest, Token, UserResponse
from database import get_db
from auth import hash_password, verify_password, create_access_token, verify_token
from turnstile import verify_turnstile_token

def has_completed_onboarding(user_id: int) -> bool:
    """Check if user has completed onboarding"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_topics WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        return count >= 3

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_user_by_username(username: str, include_password=False):
    with get_db() as conn:
        cursor = conn.cursor()
        if include_password:
            cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "username": row[1], "password_hash": row[2]}
        else:
            cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "username": row[1]}
        return None

def get_client_ip(request: Request) -> str:
    """Get the client's IP address, handling proxy headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host

@router.post("/register", status_code=201)
def register(user: UserCreate, request: Request):
    # Verify Turnstile token
    client_ip = get_client_ip(request)
    if not verify_turnstile_token(user.turnstile_token, client_ip):
        raise HTTPException(status_code=400, detail="Invalid Turnstile token")
    
    if get_user_by_username(user.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed = hash_password(user.password)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user.username, hashed))
        user_id = cursor.lastrowid
        # Auto-create default profile
        cursor.execute(
            "INSERT INTO user_profiles (user_id, display_name, bio) VALUES (?, ?, ?)",
            (user_id, user.username, "")
        )
        conn.commit()
    return {"msg": "User registered successfully"}

@router.post("/login", response_model=Token)
def login(login_data: LoginRequest, request: Request):
    # Verify Turnstile token
    client_ip = get_client_ip(request)
    if not verify_turnstile_token(login_data.turnstile_token, client_ip):
        raise HTTPException(status_code=400, detail="Invalid Turnstile token")
    
    user = get_user_by_username(login_data.username, include_password=True)
    if not user or not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    # Check ban/termination status
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT banned_until, is_terminated FROM users WHERE id = ?", (user["id"],))
        row = cursor.fetchone()
        banned_until, is_terminated = row if row else (None, 0)
        # Fetch recent moderation actions for this user
        cursor.execute("SELECT content_type, content_id, action, reason, admin_note, created_at FROM moderation_actions WHERE user_id = ? AND action = 'moderated' ORDER BY created_at DESC LIMIT 5", (user["id"],))
        moderation_history = cursor.fetchall()
        moderation_details = [
            {
                "content_type": mh[0],
                "content_id": mh[1],
                "action": mh[2],
                "reason": mh[3],
                "admin_note": mh[4],
                "created_at": mh[5]
            }
            for mh in moderation_history
        ]
    if is_terminated:
        return {
            "not_approved": True,
            "reason": "terminated",
            "message": "Your account has been terminated.",
            "banned_until": None,
            "moderation_details": moderation_details
        }
    if banned_until:
        from datetime import datetime
        now = datetime.utcnow()
        try:
            banned_until_dt = datetime.fromisoformat(banned_until)
        except Exception:
            banned_until_dt = None
        if banned_until_dt and banned_until_dt > now:
            return {
                "not_approved": True,
                "reason": "banned",
                "message": f"You are banned until {banned_until}.",
                "banned_until": banned_until,
                "moderation_details": moderation_details
            }
    # Check onboarding status
    onboarding_completed = has_completed_onboarding(user["id"])
    access_token = create_access_token({"sub": user["username"]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "onboarding_completed": onboarding_completed
    }

@router.get("/me", response_model=UserResponse)
def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current user information from token, and check for ban/termination status."""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user profile information
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT display_name, bio, profile_picture_uuid FROM user_profiles WHERE user_id = ?", (user["id"],))
        profile_row = cursor.fetchone()
        display_name = profile_row[0] if profile_row else user["username"]
        bio = profile_row[1] if profile_row else ""
        profile_picture_uuid = profile_row[2] if profile_row else None
        
        # Check ban/termination status
        cursor.execute("SELECT banned_until, is_terminated, is_admin FROM users WHERE id = ?", (user["id"],))
        row = cursor.fetchone()
        banned_until, is_terminated, is_admin = row if row else (None, 0, 0)
        
        # Fetch recent moderation actions for this user
        cursor.execute("SELECT content_type, content_id, action, reason, admin_note, created_at FROM moderation_actions WHERE user_id = ? AND action = 'moderated' ORDER BY created_at DESC LIMIT 5", (user["id"],))
        moderation_history = cursor.fetchall()
        moderation_details = [
            {
                "content_type": mh[0],
                "content_id": mh[1],
                "action": mh[2],
                "reason": mh[3],
                "admin_note": mh[4],
                "created_at": mh[5]
            }
            for mh in moderation_history
        ]
    
    if is_terminated:
        return {
            "not_approved": True,
            "reason": "terminated",
            "message": "Your account has been terminated.",
            "banned_until": None,
            "moderation_details": moderation_details
        }
    if banned_until:
        from datetime import datetime
        now = datetime.utcnow()
        try:
            banned_until_dt = datetime.fromisoformat(banned_until)
        except Exception:
            banned_until_dt = None
        if banned_until_dt and banned_until_dt > now:
            return {
                "not_approved": True,
                "reason": "banned",
                "message": f"You are banned until {banned_until}.",
                "banned_until": banned_until,
                "moderation_details": moderation_details
            }
    
    # Build profile picture URL
    profile_picture_url = None
    if profile_picture_uuid:
        profile_picture_url = f"/cdn/users/profilepictures/{profile_picture_uuid}"
    
    return UserResponse(
        user_id=user["id"],
        username=user["username"],
        email="",  # Not stored in current schema
        display_name=display_name,
        profile_picture_url=profile_picture_url,
        is_approved=True,  # If they can access this endpoint, they're approved
        role="admin" if is_admin else "user"
    ) 